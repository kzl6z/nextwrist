"""Classer les fichiers trouves, et repondre dans la conversation.

LE MOTEUR RAMENE, CE MODULE CHOISIT

Spotlight rend une liste non triee : trois cents fichiers qui contiennent le
mot « compte » quelque part, dans n'importe quel ordre. La question etait
« mon releve de compte de 2024 ». Tout le travail utile est entre les deux.

⚠️ LE SCORE EST UNE PROPORTION, PAS UN COMPTE.

Meme regle que le catalogue d'images, et pour la meme raison : compter les
mots trouves ferait gagner les NOMS LONGS. « rapport-de-stage-compte-rendu-
final-v3-corrige.pdf » attrape des mots au hasard ; « releve-2024-03.pdf »
n'en attrape que deux, et c'est le bon.

⚠️ LE DOSSIER COMPTE AUTANT QUE LE NOM.

« ~/Documents/Banque/2024/mars.pdf » ne contient ni « releve » ni « compte »
dans son nom. Il est pourtant la reponse — c'est le CHEMIN qui le dit. Un
classement qui ne lit que le nom rate exactement les fichiers de ceux qui
rangent bien.
"""

from __future__ import annotations

import re
from pathlib import Path

from nova.core import chrono
from nova.fichiers import Trouvaille
from nova.fichiers.requete import Recherche, lire, sans_accents
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: En dessous, on ne propose pas : mieux vaut dire qu'on n'a pas trouve.
SEUIL = 0.42

#: Ecart minimal avec le suivant pour ouvrir sans demander.
#: Meme garde-fou que pour les images et les applications : deux fichiers a
#: egalite n'en designent aucun.
MARGE_OUVERTURE = 0.18

#: Ce qu'on montre. Au-dela, on ne repond plus a une question, on recite un
#: dossier — et un petit modele qui lit dix lignes en resume trois au hasard.
COMBIEN = 4


def _mots_du_chemin(chemin: Path) -> str:
    """Le nom et les dossiers parents, en mots comparables."""
    return re.sub(r"[^a-z0-9]+", " ", sans_accents(str(chemin)).lower())


def score(trouve: Trouvaille, recherche: Recherche) -> float:
    """A quel point ce fichier repond a la question, entre 0 et 1.

    ⚠️ CE QU'ON MESURE EST LA COUVERTURE DES IDEES, PAS DES MOTS.

    Premiere version : la part des mots CHERCHES presents dans le chemin, et
    un petit bonus forfaitaire si un synonyme apparaissait. Consequence, vue
    par un banc et pas par la relecture : `passeport-2023.pdf` ne portait
    aucun des mots de « carte d'identite », touchait donc le plancher, et
    tombait sous le seuil. La table de synonymes faisait remonter le bon
    fichier — et le classement le jetait juste apres.

    On compte donc les GROUPES DE SENS couverts. « carte d'identite » et
    « passeport » sont le meme groupe : le fichier couvre la recherche en
    entier.
    """
    from nova.fichiers.requete import groupes

    texte = _mots_du_chemin(trouve.chemin)
    presents = {mot for mot in recherche.mots if mot in texte}

    # ⚠️ LE PLANCHER DIT CE QUE LE MOTEUR A DEJA ETABLI.
    #
    # Un fichier revenu de la passe PRECISE porte tous les mots cherches —
    # dans son nom ou dans son texte. S'ils ne sont pas dans le chemin, c'est
    # qu'ils sont dans la page : c'est une trouvaille, pas un hasard. Le
    # reduire a zero parce que le nom est muet reviendrait a ignorer la seule
    # chose que Spotlight sait faire et que nous ne savons pas.
    #
    # ⚠️ ET LE BAREME LAISSE DE LA PLACE AU-DESSUS DE LUI.
    #
    # Plancher + precision + couverture + mot exact faisaient 1,00 a eux
    # seuls. Deux fichiers egalement bien nommes, l'un portant l'annee
    # demandee et l'autre pas, plafonnaient donc tous les deux a 1,00 : le
    # bonus d'annee ne departageait plus rien, et la marge d'ouverture ne se
    # declenchait jamais. Un score sature ne classe plus.
    note = 0.20 + (0.12 if trouve.precis else 0.0)

    cherches = groupes(recherche.mots)
    if cherches:
        couverts = sum(
            1 for groupe in cherches if any(mot in texte for mot in groupe)
        )
        note += 0.42 * (couverts / len(cherches))
    # Le mot EXACT vaut un peu mieux que son synonyme : entre `passeport.pdf`
    # et `carte-identite.pdf`, on prefere celui qui emploie les mots dits.
    if presents:
        note += 0.06

    if recherche.annee:
        annee = str(recherche.annee)
        if annee in texte:
            # L'annee dans le nom ou le dossier est le signal le plus fort
            # qui existe pour un papier administratif.
            note += 0.28
        elif trouve.annee == recherche.annee:
            note += 0.12
        else:
            # ⚠️ ON PENALISE, ON N'EXCLUT PAS.
            #
            # Un releve de 2024 peut avoir ete recopie en 2025 : sa date de
            # modification ment. L'exclure ferait disparaitre la bonne
            # reponse sans que personne puisse le savoir.
            note -= 0.20

    if recherche.extensions and trouve.chemin.suffix.lower() in recherche.extensions:
        note += 0.10
    elif recherche.extensions:
        note -= 0.15

    return max(0.0, min(1.0, note))


def classer(
    trouves: list[Trouvaille], recherche: Recherche, limite: int = COMBIEN
) -> list[tuple[Trouvaille, float]]:
    """Les meilleurs fichiers, du plus au moins pertinent."""
    notes = [(t, score(t, recherche)) for t in trouves]
    retenus = [(t, n) for t, n in notes if n >= SEUIL]
    # A score egal, le plus recent : entre deux releves de mars et d'avril, on
    # parle presque toujours du dernier.
    retenus.sort(key=lambda couple: (-couple[1], -couple[0].modifie))
    return retenus[:limite]


def dossiers_cherches() -> tuple[Path, ...]:
    """Ou Nova a le droit de chercher un fichier."""
    from nova.settings import get_settings
    from nova.vision.images import racines

    reglages = get_settings()
    declares = [d.strip() for d in reglages.fichiers_dossiers.split(",") if d.strip()]
    return racines(declares)


def chercher(texte: str, *, limite: int = COMBIEN) -> tuple[Recherche, list]:
    """Traduit la phrase, interroge le moteur, classe. Ne leve jamais."""
    from nova.fichiers.moteurs import moteur

    recherche = lire(texte)
    if not recherche:
        return recherche, []
    racines = dossiers_cherches()
    if not racines:
        log.warning("Aucun dossier de recherche configure (NOVA_FICHIERS_DOSSIERS).")
        return recherche, []
    try:
        with chrono.mesurer("fichiers — interrogation de l'index"):
            trouves = moteur(racines).chercher(recherche)
    except Exception as erreur:  # noqa: BLE001
        log.warning("Recherche de fichiers en echec : %s", erreur)
        return recherche, []
    classes = classer(trouves, recherche, limite)
    log.info(
        "Fichiers : %d candidat(s), %d retenu(s)%s",
        len(trouves), len(classes),
        f", meilleur {classes[0][0].nom}" if classes else "",
    )
    return recherche, classes


# ══════════════════════════════════════════════════════════════════════════
#  LE DECLENCHEMENT
# ══════════════════════════════════════════════════════════════════════════
#: Les verbes qui demandent de retrouver quelque chose.
_CHERCHER = re.compile(
    r"\b(?:retrouv\w*|cherch\w*|trouv\w*|localis\w*|ou est|ou sont|"
    r"ou se trouve|ou j'?ai (?:mis|range)|as[- ]tu|aurais[- ]tu|"
    r"acces a|besoin de|il me faut|montre|donne[- ]moi)\b",
    re.IGNORECASE,
)

#: Ce qui prouve qu'on parle d'un FICHIER, et pas d'une idee.
#:
#: ⚠️ SANS CE SECOND SIGNAL, « cherche-moi une recette de crepes » PARTIRAIT
#:    FOUILLER LE DISQUE.
#:
#: Le verbe seul ne dit rien : « trouve-moi une idee de cadeau » l'emploie
#: aussi. Il faut le mot qui designe un objet range quelque part — un type de
#: fichier, un genre de papier, ou le mot « fichier » lui-meme.
#: Ce qui nomme le CONTENANT : « dans mes fichiers », « sur mon disque ».
_CONTENANTS = (
    "fichiers?", "documents?", "dossiers?", "papiers?", "pdf", "tableur",
    "excel", "word", "telechargements?", "bureau", "disque", "ordinateur",
    "mon pc", "sur mon mac", "cv", "rapports?", "presentations?",
)


def _signal_fichier() -> re.Pattern[str]:
    """Le motif du second signal, bati sur la liste des papiers.

    ⚠️ IL EST DEDUIT DE `requete.PAPIERS`, PAS RECOPIE A COTE.

    Deux listes de vocabulaire administratif dans deux modules auraient
    diverge a la premiere correction — l'une saurait reconnaitre « carte
    d'identite », l'autre saurait l'elargir a « passeport », et personne ne
    verrait laquelle manque. Le declencheur et l'elargissement lisent donc la
    meme source.
    """
    from nova.fichiers.requete import PAPIERS

    mots = "|".join(sorted(_CONTENANTS) + sorted(PAPIERS))
    return re.compile(rf"\b(?:{mots})\b", re.IGNORECASE)


_SIGNAL_FICHIER = _signal_fichier()


def fichier_en_tete_pour(cible: str):
    """Le fichier retenu, si « cible » le designe. Rend un `Path` ou `None`.

    ⚠️ MEME DEFAUT QUE « OUVRE LA PHOTO », MEME ETAGE, MEME REMEDE.

    Le verbe « ouvre » est capte par la reconnaissance d'intention, qui ne
    connait qu'une chose a ouvrir : une application. Releve en conditions
    reelles, juste apres une recherche :

        « ouvre cet avis d'imposition de 2024 »
        → Je ne trouve pas d'application « cette envie d'imposition de
          2024 » sur cette machine.

    Exact, et inutile : le message decrit ce que Nova a cherche, pas ce qu'on
    lui a demande.

    ⚠️ ON EXIGE UN RECOUVREMENT AVEC LE FICHIER RETENU.

    Rendre le fichier des qu'il y en a un en memoire detournerait « ouvre
    Chrome » pendant dix minutes. Il faut qu'un mot de la cible se retrouve
    dans le nom ou le dossier du fichier — c'est ce qui distingue « ouvre-le »
    de « ouvre autre chose ».

    Le pronom seul suffit : « ouvre-le » n'a aucun mot a recouper, et ne peut
    designer que ce dont on vient de parler.
    """
    from nova.vision import focus

    retenue = focus.derniere("fichier")
    if retenue is None or not cible:
        return None

    plat = sans_accents(cible).lower()
    if _PRONOM_SEUL.fullmatch(plat.strip()):
        return retenue.chemin

    cherches = lire(cible).mots
    if not cherches:
        return None
    texte = _mots_du_chemin(retenue.chemin)
    if any(mot in texte for mot in cherches):
        return retenue.chemin
    # Les synonymes comptent aussi : on a demande « mes impots », le fichier
    # s'appelle « avis-imposition-2024.pdf ».
    from nova.fichiers.requete import groupes

    return (
        retenue.chemin
        if any(
            any(mot in texte for mot in groupe) for groupe in groupes(cherches)
        )
        else None
    )


#: « ouvre-LE », « ouvre-LA » : rien a recouper, et rien d'autre a designer.
_PRONOM_SEUL = re.compile(r"(?:le|la|les|ca|cela|celui|celle)", re.IGNORECASE)


def demande_de_fichier(texte: str) -> bool:
    """Cette phrase demande-t-elle de retrouver un fichier sur la machine ?

    ⚠️ DEUX SIGNAUX EXIGES, ET C'EST TOUTE LA PRECISION DU FILTRE.

    Un verbe de recherche ET un mot qui designe un fichier. La meme forme que
    `DEMANDE_DE_REGARD` pour les images, pour la meme raison : chacun des
    deux, seul, attrape des phrases qui n'ont rien a voir.
    """
    if not texte:
        return False
    plat = sans_accents(texte)
    return bool(_CHERCHER.search(plat) and _SIGNAL_FICHIER.search(plat))


# ══════════════════════════════════════════════════════════════════════════
#  LE BLOC DE CONVERSATION
# ══════════════════════════════════════════════════════════════════════════
def _ouvrir_si_evident(classes) -> Trouvaille | None:
    """Ouvre le fichier quand un seul se detache. Rend celui qui l'a ete.

    ⚠️ MEME PORTILLON QUE POUR LES IMAGES.

    L'ouverture passe par `executer_outil`, donc par le bareme de risque.
    Court-circuiter parce que « ce n'est qu'une ouverture » rendrait le
    bareme decoratif — et c'est exactement ce que la vision a deja refuse de
    faire.
    """
    meilleur, note = classes[0]
    second = classes[1][1] if len(classes) > 1 else 0.0
    if note - second < MARGE_OUVERTURE:
        log.info(
            "Ouverture non declenchee : %s a %.0f %% contre %.0f %% pour le suivant.",
            meilleur.nom, note * 100, second * 100,
        )
        return None
    try:
        from nova.outils import executer_outil

        executer_outil("ouvrir_fichier", chemin=str(meilleur.chemin))
    except Exception as erreur:  # noqa: BLE001
        log.warning("Fichier trouve mais non ouvert : %s", erreur)
        return None
    return meilleur


def _rien_trouve(recherche: Recherche) -> str:
    """⚠️ « RIEN TROUVE » A DEUX CAUSES OPPOSEES, ET IL FAUT LES SEPARER.

    Le fichier n'existe pas — ou il existe et rien dedans ne se cherche. Un
    releve SCANNE est une image : aucun texte a l'intérieur, donc seul son
    nom est indexe, et « IMG_4021.pdf » ne dira jamais « releve ».

    Confondre les deux laisserait quelqu'un reformuler dix fois une question
    qui ne pouvait pas aboutir. On dit donc la vraie limite et le remede.
    """
    quoi = " ".join(recherche.mots) or "ce que tu decris"
    quand = f" de {recherche.annee}" if recherche.annee else ""
    return (
        "## Recherche de fichier\n\n"
        f"Recherche demandee : « {quoi}{quand} »\n"
        "Resultat : AUCUN fichier ne correspond.\n\n"
        "Reponds EXACTEMENT ceci, et rien d'autre :\n\n"
        f"« Je n'ai trouve aucun fichier correspondant a {quoi}{quand}. "
        "La recherche porte sur le nom des fichiers et sur le texte qu'ils "
        "contiennent : un document scanne n'a pas de texte a l'interieur, "
        "donc seul son nom peut le retrouver. Si tu te rappelles un mot de "
        "son nom, dis-le-moi. »"
    )


def bloc(texte: str) -> str:
    """Le bloc a injecter dans le prompt, ou `""` s'il n'y a rien a chercher."""
    return bloc_et_resultat(texte)[0]


def bloc_et_resultat(texte: str) -> tuple[str, bool]:
    """Le bloc, ET si un fichier a reellement ete trouve.

    ⚠️ CETTE FONCTION NE LEVE JAMAIS, ET NE COUTE RIEN QUAND ELLE NE SERT PAS.

    Comme `regard.bloc`, elle commence par deux expressions regulieres. Elles
    rendent `""` en zero milliseconde pour l'ecrasante majorite des
    questions — la condition pour qu'un branchement de plus sur le chemin de
    la conversation ne ralentisse personne.

    ⚠️ POURQUOI L'APPELANT A BESOIN DU BOOLEEN.

    Un bloc « aucun fichier ne correspond » est du texte comme un autre : rien
    ne le distingue d'une reponse. L'orchestrateur doit pourtant savoir la
    difference, parce qu'un echec ici ne doit JAMAIS empecher le catalogue
    d'images d'essayer. Releve en conditions reelles, et c'etait une
    regression :

        « peux-tu me retrouver une photo dans mon PC ou je tiens une
          casquette blanche »

    « dans mon PC » a suffi a declencher la recherche de fichiers ; aucun
    fichier ne s'appelle « casquette » ; et comme le bloc n'etait pas vide, le
    catalogue d'images — qui connaissait cette photo par sa DESCRIPTION — n'a
    jamais ete consulte. Nova a repondu « aucune photo ne correspond » sur une
    photo qu'elle avait deja regardee.
    """
    if not demande_de_fichier(texte):
        return "", False

    from nova.settings import get_settings

    if not get_settings().fichiers_actifs:
        return "", False

    recherche, classes = chercher(texte)
    if not recherche:
        return "", False
    if not classes:
        return _rien_trouve(recherche), False

    meilleur, meilleure_note = classes[0]

    # ⚠️ ON RETIENT TOUJOURS, ON N'OUVRE QUE SI C'EST NET.
    #
    # Retenir permet a « ouvre-le » de designer CE fichier. Ouvrir est une
    # action : elle attend qu'un candidat se detache, sans quoi Nova ouvrirait
    # l'un des quatre au hasard.
    from nova.vision import focus

    focus.retenir(
        meilleur.chemin,
        description=f"{meilleur.nom} ({meilleur.date_lisible()})",
        origine="recherche de fichier",
        genre="fichier",
    )
    ouvert = _ouvrir_si_evident(classes)

    lignes = "\n".join(
        f"- {t.nom} ({int(n * 100)} % de correspondance) — "
        f"dans {t.dossier}, modifie le {t.date_lisible()}"
        for t, n in classes
    )
    quoi = " ".join(recherche.mots) or "ce que tu decris"
    log.info(
        "Recherche « %s » : %d resultat(s), meilleur %s a %.0f %%.",
        quoi, len(classes), meilleur.nom, meilleure_note * 100,
    )

    bloc_trouve = (
        "## Recherche de fichier\n\n"
        f"Recherche demandee : « {quoi} »\n"
        "Fichiers trouves sur la machine, le meilleur en premier — c'est la "
        "SEULE chose que Nova sait d'eux :\n"
        f"<<<\n{lignes}\n>>>\n\n"
        "Ta reponse : dis en francais, en une ou deux phrases, quel fichier "
        f"correspond — en le nommant : {meilleur.nom}, et en disant dans quel "
        "dossier il se trouve et de quand il date.\n"
        + (
            "Dis aussi que tu viens de l'ouvrir.\n\n"
            if ouvert is not None
            else "Propose de l'ouvrir si c'est le bon.\n\n"
        )
        # ⚠️ ON ENUMERE CE QUI S'INVENTE, PLUTOT QUE D'INTERDIRE D'INVENTER.
        #
        # La lecon du bloc de vision, mot pour mot : une consigne negative
        # demande a un modele de deux milliards de parametres de reconnaitre
        # ce qu'il ne doit pas faire. Ici le risque est precis — il va
        # RACONTER ce que le document contient, alors que Nova ne l'a pas
        # ouvert.
        + "Tu n'as pas lu ces fichiers. Leur contenu, les montants, les noms "
        "qui y figurent, le nombre de pages : rien de tout cela ne figure "
        "entre <<< >>>, donc rien de tout cela ne doit figurer dans ta "
        "reponse."
    )
    return bloc_trouve, True
