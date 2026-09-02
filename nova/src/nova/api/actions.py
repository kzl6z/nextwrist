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
    """Reconnait l'intention de la phrase et l'execute, si tout concorde."""
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
                etat="executee", message=message, outil=None, niveau=None,
                intention=f"contexte_{ordre.genre}", cible=None,
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

    if trouver.demande_tout_ouvrir(demande.texte) and (
        liste := trouver.liste_en_tete()
    ):
        fait = orchestrator.ouvrir_toute_la_liste(liste)
        log.info("« %s » → %d fichier(s) ouvert(s)", demande.texte, len(liste))
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
