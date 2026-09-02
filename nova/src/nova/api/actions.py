"""Executer une intention : POST /v1/action.

LE CONTRAT, EN DEUX TEMPS

L'application envoie ce que Nova a compris. Nova Core repond l'une de quatre
choses :

    executee     c'est fait, voici le message a prononcer
    a_confirmer  voici la QUESTION a poser ; rappelle-moi avec confirme=true
    ignoree      reconnu, mais pas assez sur — ou pas encore implemente
    echouee      tente, et raté ; voici pourquoi

⚠️ `confirme` VIENT DE L'UTILISATEUR, JAMAIS DU MODELE.

C'est toute la difference entre un garde-fou et un decor. Si un modele
pouvait remplir ce champ, il reviendrait a demander au renard s'il a le droit
d'entrer dans le poulailler — et un modele local de trois milliards de
parametres repondrait oui.

L'application doit donc avoir REELLEMENT pose la question et REELLEMENT
entendu la reponse avant de rappeler avec `confirme=true`.

POURQUOI DEUX APPELS PLUTOT QU'UN

Un seul appel devrait porter la reponse a une question pas encore posee. En
deux temps, l'etat vit la ou il doit vivre — chez celui qui parle a
l'utilisateur — et Nova Core reste sans memoire d'un appel a l'autre.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from nova import orchestrator
from nova.logging_setup import get_logger
from nova.voice import comprehension as voice_comprehension
from nova.voice import intentions as voice_intentions

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["actions"])


class DemandeAction(BaseModel):
    """Ce que l'application a compris, et ce qu'elle demande d'en faire."""

    texte: str = Field(description="La phrase, apres comprehension")
    #: Confiance de la PAROLE (0 a 1). L'application la recoit de
    #: /v1/audio/wake ou /v1/audio/transcriptions et la retransmet telle
    #: quelle. Par defaut 1.0 : une demande TAPEE n'a pas de doute
    #: acoustique.
    confiance: float = 1.0
    #: L'utilisateur a-t-il repondu oui a une question deja posee ?
    confirme: bool = False


class ReponseAction(BaseModel):
    etat: str
    message: str
    outil: str | None = None
    niveau: int | None = None
    intention: str | None = None
    cible: str | None = None


@router.post("/action", response_model=ReponseAction)
def executer(demande: DemandeAction) -> ReponseAction:
    """Reconnait l'intention de la phrase et l'execute, si tout concorde.

    ⚠️ CE POINT D'ENTREE REND TOUJOURS QUELQUE CHOSE A DIRE.

    Il est donc le pendant du premier jeton de `answer_stream` : c'est ici
    qu'une interruption cesse de valoir. « attends, ouvre plutot le
    deuxieme » coupe la parole PUIS demande une action — sans cette levee,
    la confirmation de l'action serait prononcee en silence, et Nova
    paraitrait n'avoir rien fait.

    On la leve APRES coup, une fois le message construit : d'ici la,
    l'application peut encore vider en silence les phrases qu'elle avait en
    attente de la reponse coupee.
    """
    reponse = _executer(demande)
    if reponse.message:
        from nova.voice import interruption

        interruption.reprendre()
    return reponse


def _executer(demande: DemandeAction) -> ReponseAction:
    # ⚠️ UN « OUI » NU REPOND A LA PROPOSITION, PAS AU MODELE.
    #
    # Nova vient de dire « je te l'ouvre ? ». La reponse tient en un mot, et
    # ce mot ne porte aucune intention reconnaissable : envoye au modele, il
    # produirait une phrase polie et rien d'autre.
    #
    # Il ne vaut que parce qu'une proposition attend. Hors de ce cas, « oui »
    # repart vers le modele comme n'importe quelle phrase — c'est ce qui rend
    # cette liste de mots aussi courte sans danger.
    from nova.voice import session

    if (acceptee := session.accord(demande.texte)) is not None:
        outil, arguments = acceptee
        comme = session.libelle()
        fait = orchestrator.executer_outil_propose(outil, arguments, comme=comme)
        log.info("Proposition acceptee « %s » → %s", demande.texte, fait.etat)
        return ReponseAction(
            etat=fait.etat, message=fait.message, outil=fait.outil,
            niveau=fait.niveau, intention="proposition_acceptee", cible=None,
        )

    # ⚠️ LE CONTEXTE DE TRAVAIL SE PILOTE A LA VOIX, ET AVANT TOUT LE RESTE.
    #
    # « ouvre le projet moteur » etait capte par `ouvrir_application` : la
    # cible « projet moteur » partait au catalogue des applications. Les cinq
    # autres ordres — objectif, tache, decision, confidentialite,
    # basculement — ne declenchaient RIEN.
    #
    # ⚠️ ET « CA » SE RESOUT PAR LA PHRASE D'AVANT.
    #
    # « ajoute ca aux prochaines etapes » ne porte pas son contenu. On lit et
    # on ecrit le propos precedent d'un seul geste : l'ordre des appels entre
    # l'application et Nova Core n'est pas garanti, et deux temps
    # introduiraient une course.
    precedent = session.noter_le_propos(demande.texte)

    from nova.contexte import actif as contexte_actif
    from nova.contexte import commandes as contexte_commandes

    ordre = contexte_commandes.lire(demande.texte, propos_precedent=precedent)
    if ordre is not None:
        try:
            message = contexte_actif.appliquer(ordre, source=demande.texte)
        except Exception as erreur:  # noqa: BLE001
            log.warning("[Contexte] Ordre « %s » en echec : %s", ordre.genre, erreur)
            return ReponseAction(
                etat="echouee", message="Je n'ai pas réussi à noter ça.",
                outil=None, niveau=None, intention="contexte", cible=None,
            )
        if message:
            log.info("[Contexte] « %s » → %s", demande.texte, ordre.genre)
            return ReponseAction(
                etat="executee",
                message=message + _proposer_le_dossier(),
                outil=None, niveau=None,
                intention=f"contexte_{ordre.genre}", cible=None,
            )

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ METTRE A JOUR SE LIT AVANT CREER, ET L'ORDRE FAIT TOUT.
    #
    #  « mets le dossier a jour » porte un verbe de creation et le mot
    #  « dossier » : `creer.demande_de_dossier` le prendrait pour lui, et Nova
    #  repondrait poliment que le dossier est deja la — sans rien faire.
    #
    #  ⚠️ ET C'EST LA PREMIERE ACTION QUI PASSE PAR LE PORTILLON.
    #
    #  Reecrire un document existant est CONSEQUENT : le bareme le nomme mot
    #  pour mot. `executer_outil` refuse donc tant que `confirme` ne vient pas
    #  de l'UTILISATEUR — jamais du modele. C'est le contrat en deux temps
    #  decrit en tete de ce fichier, et c'est son premier usage reel.
    # ══════════════════════════════════════════════════════════════════════
    if _mise_a_jour_demandee(demande.texte):
        return _mettre_a_jour(demande)

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ RANGER SE LIT AVANT CREER, POUR LA MEME RAISON QUE METTRE A JOUR.
    #
    #  « mets-les dans le dossier » porte un verbe et le mot « dossier » :
    #  `creer.demande_de_dossier` le prendrait pour lui. Ce qui les separe est
    #  l'ARTICLE — « dans UN dossier Photos » cree, « dans LE dossier » range —
    #  et l'ordre garantit que le defini n'est jamais lu comme un indefini.
    # ══════════════════════════════════════════════════════════════════════
    from nova.fichiers import ranger

    if ranger.demande_d_annuler(demande.texte):
        return _agir_sur_les_fichiers(
            demande, "remettre_ou_ils_etaient", _question_de_retour
        )

    if ranger.demande_de_ranger(demande.texte):
        return _agir_sur_les_fichiers(
            demande, "ranger_dans_le_projet", _question_de_rangement
        )

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ CREER UN DOSSIER — LA PREMIERE FOIS QUE NOVA ECRIT SUR LE DISQUE.
    #
    #      « Nova, je cherche a creer un moteur electrique. »
    #      « J'aimerais que tout soit classe dans un dossier sur mon bureau. »
    #
    #  La seconde phrase ne porte pas de nom : il vient du projet actif, que
    #  la premiere vient d'ouvrir. C'est exactement ce que le contexte de
    #  travail existe pour rendre possible — et c'est pourquoi ce branchement
    #  passe APRES lui, jamais avant.
    #
    #  ⚠️ ET NOVA DIT LE NOM QU'ELLE A DEDUIT.
    #
    #  « J'ai cree le dossier moteur electrique sur ton Bureau » : le nom
    #  vient d'une deduction, la destination d'un defaut. Dire « c'est fait »
    #  laisserait un dossier mal nomme s'installer quelque part, et on le
    #  retrouverait trois jours plus tard sans savoir d'ou il sort.
    # ══════════════════════════════════════════════════════════════════════
    from nova.fichiers import creer

    if (voulu := creer.demande_de_dossier(demande.texte)) is not None:
        nom = voulu.nom or _nom_du_projet_actif()
        if not nom:
            # ⚠️ `ignoree` ETAIT LE MAUVAIS ETAT, ET LA QUESTION SE PERDAIT.
            #
            # Le contrat le dit : `ignoree` signifie « reconnu, mais pas assez
            # sur — ou pas encore implemente ». L'application enchaine alors
            # sur le modele de langue, qui repond toujours quelque chose.
            # Releve en conditions reelles :
            #
            #     « Créer un dossier sur mon bureau… »
            #     « …est possible via le menu 'Fichier' > 'Nouveau dossier'. »
            #
            # Nova avait la bonne question a poser ; personne ne l'a entendue.
            # `echouee` — « tente, et rate ; voici pourquoi » — decrit
            # exactement la situation, et l'application le PRONONCE.
            return ReponseAction(
                etat="echouee",
                message="Comment veux-tu appeler ce dossier ?",
                outil=None, niveau=None, intention="creer_dossier", cible=None,
            )
        fait = orchestrator.executer_outil_propose(
            "creer_dossier", {"dossier": nom, "ou": voulu.ou}
        )
        log.info("« %s » → creer_dossier « %s » (%s)", demande.texte, nom, fait.etat)
        return ReponseAction(
            etat=fait.etat, message=fait.message, outil=fait.outil,
            niveau=fait.niveau, intention="creer_dossier", cible=nom,
        )

    # ⚠️ « OUVRE LES 3 » N'EST PAS UN NOM D'APPLICATION.
    #
    # Nova vient d'annoncer trois fichiers : « les trois » est la suite
    # naturelle de sa propre phrase. Sans ce branchement, la cible « trois »
    # partait au catalogue des applications — « Je ne trouve pas
    # d'application "trois" sur cette machine ».
    #
    # ⚠️ AVANT LA RECONNAISSANCE D'INTENTION, ET C'EST LE CORRECTIF.
    #
    # Ce branchement etait a l'interieur du cas `ouvrir_application`, donc
    # apres `reconnaitre`. Il ne pouvait par construction rien faire quand
    # l'intention n'etait PAS reconnue — or c'est exactement ce qui arrivait :
    #
    #     « peux-tu tous les ouvrir »  →  cible « », intention non reconnue
    #
    # La cible est ce qui SUIT le verbe ; le verbe etant en dernier, il ne
    # suivait rien. La phrase partait au modele de langue, qui repondait
    # poliment sans rien ouvrir.
    #
    # La demande ne depend d'aucune intention : elle se lit sur la phrase, et
    # elle exige une liste deja annoncee. Elle passe donc avant.
    from nova.fichiers import trouver

    # ⚠️ ET « LES TROIS » PEUVENT ETRE DES PHOTOS.
    #
    # Ce branchement lisait `liste_en_tete()`, qui ne rend QUE des fichiers.
    # Releve en conditions reelles, juste apres une recherche d'images :
    #
    #     « J'ai trouve 3 photos d'une carte Pokemon. Laquelle veux-tu ? »
    #     « Ouvre-les toutes. »
    #     « Je ne trouve pas d'application "toutes" sur cette machine. »
    #
    # La liste etait vide — les photos sont retenues sous un autre genre — le
    # branchement ne prenait pas, et « toutes » repartait au catalogue des
    # applications. Le correctif de « peux-tu tous les ouvrir » ne couvrait
    # qu'une moitie du probleme, et personne ne pouvait le voir : les deux
    # cotes ont chacun leur banc, aucun n'avait celui-la.
    if trouver.demande_tout_ouvrir(demande.texte):
        liste, outil, mot = _liste_annoncee()
        if liste:
            fait = orchestrator.ouvrir_toute_la_liste(liste, outil=outil, mot=mot)
            log.info("« %s » → %d %s ouvert(s)", demande.texte, len(liste), mot)
            return ReponseAction(
                etat=fait.etat, message=fait.message, outil=fait.outil,
                niveau=fait.niveau, intention="ouvrir_tout", cible=None,
            )

    # ⚠️ « FERME LES QUATRE FICHIERS » CHERCHAIT UNE APPLICATION.
    #
    # Releve en conditions reelles, juste apres que Nova ait ouvert quatre
    # fichiers a la demande :
    #
    #     « Ferme les quatre fichiers. »
    #     → « Je ne trouve pas d'application "quatre fichiers" sur cette
    #        machine. »
    #
    # Exact du point de vue du catalogue, absurde du point de vue de la
    # conversation : elle venait de les ouvrir.
    #
    # ⚠️ ET NOVA NE SAIT PAS FERMER UN FICHIER. ELLE LE DIT.
    #
    # `open` confie le fichier au systeme, qui choisit l'application. Nova ne
    # sait donc pas laquelle l'affiche, et fermer « celle qui doit etre la »
    # serait un pari — sur une action qui peut detruire du travail non
    # enregistre.
    #
    # Deviner ici serait exactement le genre de reussite apparente que ce
    # projet refuse partout ailleurs. On repond ce qui est vrai, et on donne
    # la phrase qui marche.
    if trouver.demande_tout_fermer(demande.texte) and trouver.liste_en_tete():
        log.info("« %s » → fermeture de fichiers, non implementee", demande.texte)
        return ReponseAction(
            etat="ignoree",
            message=(
                "Je ne sais pas fermer un fichier déjà ouvert : c'est le système "
                "qui a choisi l'application. Dis-moi laquelle fermer, par exemple "
                "« ferme Aperçu »."
            ),
            outil=None, niveau=None, intention="fermer_fichiers", cible=None,
        )

    # ⚠️ « SOUVIENS-TOI QUE… » N'ECRIVAIT RIEN. C'ETAIT UN TROU, PAS UN MANQUE.
    #
    # L'intention « memoire » etait reconnue depuis longtemps — « souviens-toi »,
    # « retiens », « note que » — et aucune action ne se trouvait derriere.
    # Verifie sur une base reelle : la phrase etait comprise, zero ligne
    # ecrite, et Nova repondait poliment sans avoir rien retenu.
    #
    # ⚠️ AVANT LA RECONNAISSANCE D'INTENTION, POUR LA MEME RAISON QUE
    #    « PEUX-TU TOUS LES OUVRIR ».
    #
    # La demande se lit sur la PHRASE ENTIERE : ce qu'il faut retenir est ce
    # qui SUIT le verbe, et le mecanisme de cible ne transporte qu'un mot. La
    # reconnaissance d'intention n'a rien a apporter ici.
    from nova.memory import moteur as memoire

    if memoire.demande_d_oubli(demande.texte):
        fait = orchestrator.oublier_de_la_memoire(demande.texte)
        log.info("« %s » → %s", demande.texte, fait.etat)
        return ReponseAction(
            etat=fait.etat, message=fait.message, outil=fait.outil,
            niveau=fait.niveau, intention="oublier_memoire", cible=None,
        )

    if memoire.demande_de_retenir(demande.texte):
        fait = orchestrator.memoriser(demande.texte)
        log.info("« %s » → %s", demande.texte, fait.etat)
        return ReponseAction(
            etat=fait.etat, message=fait.message, outil=fait.outil,
            niveau=fait.niveau, intention="retenir_memoire", cible=None,
        )

    intention = voice_intentions.reconnaitre(demande.texte)

    # On reconstruit une `Comprehension` minimale : ce point d'entree accepte
    # du TEXTE, pas de l'audio. La confiance acoustique vient de l'appelant,
    # qui l'a obtenue au moment de la transcription — la recalculer ici
    # n'aurait aucun sens, on n'a plus le son.
    comprise = voice_comprehension.Comprehension(
        texte=demande.texte,
        origine=demande.texte,
        confiance=max(0.0, min(1.0, demande.confiance)),
        intention=intention,
    )

    resultat = orchestrator.executer_intention(comprise, confirme=demande.confirme)

    log.info(
        "Action demandee « %s » → %s%s",
        demande.texte, resultat.etat,
        " (confirmee par l'utilisateur)" if demande.confirme else "",
    )
    return ReponseAction(
        etat=resultat.etat,
        message=resultat.message,
        outil=resultat.outil,
        niveau=resultat.niveau,
        intention=intention.nom if intention.reconnue else None,
        cible=intention.cible or None,
    )


@router.get("/actions")
def catalogue() -> dict:
    """Ce que Nova sait faire, et ce qu'il en coute.

    Destine autant a l'humain qui debogue qu'a l'interface, qui peut ainsi
    afficher la liste sans la coder en dur.
    """
    from nova.core import actions, contrats
    from nova.outils import applications, registre_outils

    connues = []
    for nom_intention, action in actions.ACTIONS.items():
        outil = registre_outils.get(action.outil)
        niveau = getattr(outil, "niveau", None) if outil else None
        connues.append(
            {
                "intention": nom_intention,
                "outil": action.outil,
                "disponible": outil is not None,
                "niveau": niveau,
                "niveau_nom": contrats.nom_du_niveau(niveau) if niveau is not None else None,
                "confirmation": contrats.exige_confirmation(niveau) if niveau is not None else True,
                "catalogue": action.catalogue,
            }
        )
    # Le nombre d'applications connues est la premiere chose a regarder quand
    # « ouvre X » repond « je ne trouve pas » : zero veut dire que le
    # catalogue n'a pas ete lu, pas que l'application manque.
    installees = applications.installees()
    return {
        "actions": connues,
        "seuil_intention": actions.SEUIL_INTENTION,
        "intentions_reconnues": list(voice_intentions.intentions_connues()),
        "applications": len(installees),
    }


def _nom_du_projet_actif() -> str:
    """Le nom du projet en cours, quand il y en a un. Jamais une panne.

    ⚠️ C'EST CE QUI PERMET A LA PHRASE DE NE PAS PORTER SON NOM.

    « j'aimerais que tout soit classe dans un dossier sur mon bureau » ne dit
    pas quel dossier. Dans une conversation, il n'y en a qu'un possible :
    celui du projet dont on parle. Sans ce relais, la phrase la plus
    naturelle des deux serait la seule a ne pas marcher.
    """
    try:
        from nova.contexte import actif

        projet = actif.projet_actif()
        return projet.nom if projet else ""
    except Exception as exc:  # noqa: BLE001
        log.debug("Projet actif indisponible : %s", exc)
        return ""


def _proposer_le_dossier() -> str:
    """« Veux-tu que je mette ce projet sur ton Bureau ? », le moment venu.

    ⚠️ ELLE PROPOSE DERRIERE UNE PHRASE QU'ELLE PRONONCE DEJA.

    Nova vient de dire « Décision notée : … ». C'est le seul moment ou une
    proposition n'interrompt personne : elle a la parole, et la phrase qui
    suit porte sur ce dont on vient de parler. Une proposition spontanee, au
    milieu du silence, serait exactement ce que « penser a voix haute » vient
    d'apprendre a Nova a ne pas faire.

    ⚠️ ET UNE SEULE FOIS PAR PROJET.

    `merite_un_dossier` verifie que la question n'a pas deja ete posee, et
    `marquer_propose` l'enregistre A LA QUESTION, pas a la reponse. Un refus
    suivi de la meme question trente secondes plus tard n'est plus une
    proposition — et l'on finirait par ne plus rien dicter.

    Rend une chaine vide dans tous les autres cas : ce n'est pas une panne de
    ne rien proposer.
    """
    try:
        from nova.contexte import actif, document
        from nova.voice import session

        projet = actif.projet_actif()
        if not document.merite_un_dossier(projet):
            return ""
        session.proposer("ecrire_projet", {"projet": projet.nom})
        actif.marquer_propose(projet.id)
        log.info("[Contexte] Dossier propose pour « %s »", projet.nom)
        return " " + document.question(projet)
    except Exception as exc:  # noqa: BLE001
        # Une proposition qui echoue ne doit pas emporter la reponse qu'elle
        # accompagne : « Décision notée » a de la valeur toute seule.
        log.warning("Proposition de dossier impossible : %s", exc)
        return ""


def _mise_a_jour_demandee(texte: str) -> bool:
    """Sans le contexte disponible, on ne reconnait rien — on ne casse rien."""
    try:
        from nova.contexte import document

        return document.demande_de_mise_a_jour(texte)
    except Exception as exc:  # noqa: BLE001
        log.warning("Contexte indisponible : %s", exc)
        return False


def _mettre_a_jour(demande: DemandeAction) -> ReponseAction:
    """Reecrit le document du projet — apres confirmation, jamais avant.

    ⚠️ SANS DOCUMENT, CE N'EST PAS UNE MISE A JOUR : C'EST UNE ECRITURE.

    Et une ecriture qui n'ecrase rien est REVERSIBLE. Demander une
    confirmation pour creer un fichier absent habituerait a dire oui sans
    lire — ce qui use exactement le garde-fou qu'on essaie de poser. Le
    niveau suit le risque REEL, pas le nom de la phrase prononcee.
    """
    from nova.contexte import actif, document
    from nova.outils import ConfirmationRequise, executer_outil

    projet = actif.projet_actif()
    if projet is None:
        return ReponseAction(
            etat="ignoree", message="Aucun projet ouvert.",
            outil=None, niveau=None, intention="mettre_a_jour_projet", cible=None,
        )

    if not projet.dossier:
        fait = orchestrator.executer_outil_propose("ecrire_projet", {"projet": projet.nom})
        log.info("Mise a jour demandee, aucun document : ecriture (%s)", fait.etat)
        return ReponseAction(
            etat=fait.etat, message=fait.message, outil=fait.outil,
            niveau=fait.niveau, intention="ecrire_projet", cible=projet.nom,
        )

    try:
        message = executer_outil(
            "mettre_a_jour_projet", confirme=demande.confirme, projet=projet.nom
        )
    except ConfirmationRequise:
        # ⚠️ ON POSE NOTRE QUESTION, PAS CELLE DU PORTILLON.
        #
        # `ConfirmationRequise.question()` rend « Je m'apprete a
        # mettre_a_jour_projet (projet = centrale nucleaire). Je confirme ? » —
        # un nom d'outil et une liste d'arguments, lus a voix haute. Une
        # confirmation qu'on ne comprend pas se donne au hasard, et le
        # portillon ne protege plus rien.
        question = document.question_de_remplacement(
            projet, repris_a_la_main=not _document_intact(projet)
        )
        log.info("[Contexte] Mise a jour de « %s » : confirmation attendue", projet.nom)
        return ReponseAction(
            etat="a_confirmer", message=question, outil="mettre_a_jour_projet",
            niveau=None, intention="mettre_a_jour_projet", cible=projet.nom,
        )
    except Exception as erreur:  # noqa: BLE001
        log.warning("Mise a jour impossible : %s", erreur)
        return ReponseAction(
            etat="echouee", message=str(erreur), outil="mettre_a_jour_projet",
            niveau=None, intention="mettre_a_jour_projet", cible=projet.nom,
        )

    return ReponseAction(
        etat="executee", message=str(message), outil="mettre_a_jour_projet",
        niveau=None, intention="mettre_a_jour_projet", cible=projet.nom,
    )


def _document_intact(projet) -> bool:
    """Le document porte-t-il encore la signature de Nova ?

    C'est la seule reponse bon marche a « ce fichier a-t-il ete repris a la
    main ? ». Dans le doute — fichier illisible, dossier deplace — on repond
    VRAI : on ne va pas alarmer sur une modification qu'on n'a pas constatee.
    """
    from pathlib import Path

    from nova.contexte import document

    try:
        fichier = Path(projet.dossier) / document.nom_du_fichier(projet)
        return document.porte_la_signature(fichier.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return True


#: De quoi Nova vient de parler → avec quel outil l'ouvrir, et comment le DIRE.
#:
#: Les deux cotes existaient deja et s'ignoraient : `focus` retient le genre
#: depuis le debut, `ouvrir_image` et `ouvrir_fichier` ont chacun leur borne.
#: Il ne manquait que cette table de trois lignes pour que « ouvre-les
#: toutes » fonctionne des deux cotes.
_COMMENT_OUVRIR: dict[str, tuple[str, str]] = {
    "image": ("ouvrir_image", "photos"),
    "fichier": ("ouvrir_fichier", "fichiers"),
}


def _liste_annoncee() -> tuple[tuple, str, str]:
    """La derniere liste annoncee — photos OU documents — et comment l'ouvrir.

    Rend une liste vide quand il n'y a rien de recent : « ouvre-les toutes »
    sans rien avant ne designe rien, et il vaut mieux ne rien faire que
    d'ouvrir ce qui trainait.
    """
    try:
        from nova.vision import focus

        retenue = focus.derniere()
        if retenue is None or not retenue.liste:
            return (), "ouvrir_fichier", "fichiers"
        outil, mot = _COMMENT_OUVRIR.get(retenue.genre, ("ouvrir_fichier", "fichiers"))
        return retenue.liste, outil, mot
    except Exception as exc:  # noqa: BLE001
        log.warning("Liste annoncee indisponible : %s", exc)
        return (), "ouvrir_fichier", "fichiers"


def _agir_sur_les_fichiers(demande: DemandeAction, outil: str, question) -> ReponseAction:
    """Execute un outil de rangement — apres confirmation, jamais avant.

    ⚠️ DEPLACER EST LA SEULE ACTION OU L'ON PEUT PERDRE SANS SAVOIR QUOI.

    Le fichier n'est pas detruit, il est ailleurs. En pratique on ne retrouve
    pas ce qu'on ne sait pas nommer, et trois photos rangees au mauvais
    endroit sont perdues. D'ou le portillon, et d'ou la question qui DIT
    combien de fichiers vont bouger et vers ou : accepter sans savoir ce qui
    va se passer, c'est accepter au hasard.
    """
    from nova.outils import ConfirmationRequise, executer_outil

    try:
        message = executer_outil(outil, confirme=demande.confirme)
    except ConfirmationRequise:
        dite = question()
        if not dite:
            return ReponseAction(
                etat="echouee", message="Je n'ai rien à ranger pour l'instant.",
                outil=outil, niveau=None, intention=outil, cible=None,
            )
        log.info("« %s » → %s : confirmation attendue", demande.texte, outil)
        return ReponseAction(
            etat="a_confirmer", message=dite, outil=outil,
            niveau=None, intention=outil, cible=None,
        )
    except Exception as erreur:  # noqa: BLE001
        log.warning("%s impossible : %s", outil, erreur)
        return ReponseAction(
            etat="echouee", message=str(erreur), outil=outil,
            niveau=None, intention=outil, cible=None,
        )

    return ReponseAction(
        etat="executee", message=str(message), outil=outil,
        niveau=None, intention=outil, cible=None,
    )


def _question_de_rangement() -> str:
    """« Je déplace les 3 photos dans le dossier X ? » — jamais un nom d'outil.

    Le compte et la destination, tous les deux. Sans le compte, on ne peut pas
    contester ; sans la destination, on ne sait pas ou chercher apres.
    """
    try:
        from nova.contexte import actif
        from nova.outils.fichiers import _liste_a_ranger

        chemins = _liste_a_ranger()
        projet = actif.projet_actif()
        if not chemins or projet is None:
            return ""
        combien = len(chemins)
        quoi = "fichier" if combien == 1 else "fichiers"
        return f"Je déplace {combien} {quoi} dans le dossier {projet.nom} ?"
    except Exception as exc:  # noqa: BLE001
        log.warning("Question de rangement indisponible : %s", exc)
        return ""


def _question_de_retour() -> str:
    """« Je remets les 3 fichiers d'où ils venaient ? »"""
    try:
        from nova.contexte import actif
        from nova.fichiers import ranger

        projet = actif.projet_actif()
        faits = ranger.a_defaire(projet.id if projet else None)
        if not faits:
            return ""
        quoi = "fichier" if len(faits) == 1 else "fichiers"
        return f"Je remets {len(faits)} {quoi} d'où ils venaient ?"
    except Exception as exc:  # noqa: BLE001
        log.warning("Question de retour indisponible : %s", exc)
        return ""
