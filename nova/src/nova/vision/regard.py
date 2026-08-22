"""Regarder une image PENDANT une conversation, sans passer par un plan.

CE QUI MANQUAIT, ET POURQUOI CE FICHIER EXISTE

L'agent de vision, les outils, la circulation des resultats : tout cela
fonctionne — par `/v1/executer`. Or personne ne parle a Nova en `curl`.

    « Nova, analyse l'image que je viens de recevoir. »

Cette phrase part sur le chemin de CONVERSATION, qui ne parcourt aucun plan :
il assemble un prompt, appelle le modele, et rend la reponse. La vision n'y
etait branchee nulle part. Nova repondait donc « je ne peux pas voir les
images » — sincerement, et a cote de la verite, puisqu'elle savait le faire
depuis un autre point d'entree.

⚠️ ON NE FAIT PAS PASSER LA CONVERSATION PAR LE PLANIFICATEUR.

C'etait l'autre solution, et elle aurait coute le travail de cette session :
le chemin conversationnel a ete ramene de 8-11 s a 1,8-3,1 s avant le premier
mot. Le faire passer par plan + gestionnaire + executeur pour les 99 % de
demandes qui ne parlent d'aucune image aurait rendu tout le monde lent pour
servir un cas rare. C'est l'echange que ce projet a deja paye trois fois.

LA FORME RETENUE : UN BLOC DE PROMPT, COMME LES DOCUMENTS

`build_system_prompt` assemble deja des blocs — identite, memoire, instant
present, extraits de documents. L'observation d'une image en devient un de
plus. Consequences, et elles sont toutes souhaitables :

    la reponse est en FRANCAIS, meme si le modele de vision parle anglais
    elle est dans la VOIX de Nova, pas dans celle du modele de vision
    elle passe par le flux normal, donc par la synthese vocale
    elle est melangee a la memoire et aux documents, donc situee

⚠️ LE DECLENCHEMENT EST DETERMINISTE, ET GRATUIT QUAND IL N'A PAS LIEU.

Une detection par modele coûterait une seconde a CHAQUE question pour
decider si elle parle d'une image. Ici, une expression reguliere sur des mots
declencheurs : zero milliseconde quand la reponse est non, ce qui est le cas
de l'ecrasante majorite des questions.
"""

from __future__ import annotations

import re
from pathlib import Path

from nova.core import chrono
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Ce qu'on cherche : un VERBE de regard, et un OBJET qui soit une image.
#:
#: ⚠️ LES DEUX SONT EXIGES, ET C'EST LA TOUTE LA PRECISION DU FILTRE.
#:
#: « analyse » seul attraperait « analyse ce texte » ; « photo » seul
#: attraperait « raconte-moi l'histoire de la photographie ». Exiger les deux
#: dans la meme phrase ecarte les deux cas sans liste d'exceptions.
_VERBES = (
    r"analys\w*|decri\w*|décri\w*|regard\w*|observ\w*|examin\w*|"
    r"vois|voir|montre\w*|lis|lire|reconnais\w*|identifi\w*|"
    # Les tournures interrogatives ordinaires. Elles manquaient, et c'est
    # exactement ce qu'on dit dans la vraie vie : personne ne formule
    # « decris-moi cette image » quand il peut dire « c'est quoi cette
    # photo ». Un declencheur qui n'attrape que la formulation soignee
    # n'attrape que les demonstrations.
    r"c'est quoi|c est quoi|qu'est[- ]ce|qu est[- ]ce|"
    r"ce qu'il y a|ce qu il y a|qu'y a[- ]t[- ]il|que vois[- ]tu|"
    r"dis[- ]moi ce qu|tu peux me dire"
)
_OBJETS = (
    r"image|images|photo|photos|capture|captures|screenshot|"
    r"copie d'ecran|copie d'écran|dessin|schema|schéma|illustration|"
    r"visuel|scan|cliche|cliché"
)

DEMANDE_DE_REGARD = re.compile(
    rf"(?=.*\b(?:{_VERBES}))(?=.*\b(?:{_OBJETS})\b)", re.IGNORECASE
)

#: Un objet visuel precede d'un article INDEFINI.
#:
#: ⚠️ C'EST CE QUI SEPARE UNE QUESTION D'UNE DEMANDE DE REGARD.
#:
#:     « qu'est-ce qu'UNE photo argentique »  → une question de culture
#:     « c'est quoi CETTE photo »             → regarde-la
#:
#: Sans cette distinction, elargir les verbes aux tournures interrogatives
#: faisait charger un modele de 2 Go pour repondre a « qu'est-ce qu'une
#: image vectorielle ». L'article porte toute l'information : indefini, on
#: parle de la categorie ; defini ou demonstratif, on parle d'un fichier.
_INDEFINI = re.compile(
    rf"\b(?:un|une|des|d'|de)\s+(?:{_OBJETS})\b", re.IGNORECASE
)
_OBJET_SEUL = re.compile(rf"\b(?:{_OBJETS})\b", re.IGNORECASE)

#: Un chemin d'image ecrit dans la phrase l'emporte sur toute heuristique.
CHEMIN = re.compile(
    r"(?<![\w/.-])((?:~|\.{1,2})?[\w./\\-]*\.(?:jpe?g|png|webp|gif|bmp|heic|heif|tiff?))",
    re.IGNORECASE,
)


def parle_d_une_image(texte: str) -> bool:
    """Cette phrase demande-t-elle de regarder quelque chose ?

    Un chemin d'image ecrit noir sur blanc suffit : « decris
    ~/Downloads/x.jpg » n'a pas besoin du mot « image ».
    """
    if not texte:
        return False
    if CHEMIN.search(texte):
        return True
    if not DEMANDE_DE_REGARD.search(texte):
        return False

    # Reste a trancher entre « cette photo » et « une photo ». Il suffit
    # qu'UNE occurrence designe un fichier precis : dans « c'est quoi cette
    # photo, c'est une photo de vacances ? », la premiere suffit.
    generiques = {m.end() for m in _INDEFINI.finditer(texte)}
    return any(m.end() not in generiques for m in _OBJET_SEUL.finditer(texte))


def _situer(cible: Path) -> str:
    """« il y a 4 minutes », « il y a 3 jours » — ou rien si c'est illisible."""
    from nova.vision.images import age_en_heures

    heures = age_en_heures(cible)
    if heures < 0:
        return ""
    if heures < 1 / 60:
        return "a l'instant"

    def dire(nombre: int, unite: str) -> str:
        # Nova relit ce bloc a voix haute par la bouche du modele. « il y a 1
        # minutes » se remarque a l'oreille bien plus qu'a l'ecrit.
        return f"il y a {nombre} {unite}{'s' if nombre > 1 else ''}"

    if heures < 1:
        return dire(max(int(heures * 60), 1), "minute")
    if heures < 48:
        return dire(int(heures), "heure")
    return dire(int(heures / 24), "jour")


def bloc(texte: str) -> str:
    """L'observation a injecter dans le prompt, ou `""` s'il n'y a rien a voir.

    ⚠️ CETTE FONCTION NE LEVE JAMAIS.

    Elle est appelee dans l'assemblage du prompt, sur le chemin de toutes les
    reponses. Une vision en panne — modele absent, image illisible, dossier
    vide — doit degrader la reponse, jamais l'empecher. C'est la meme regle
    que la recherche documentaire et la memoire : chaque capacite est
    facultative, et c'est ce qui rend le systeme robuste quand on en ajoute
    dix autres.

    ⚠️ ET ELLE NE MENT PAS NON PLUS.

    Quand la vision echoue, elle rend un bloc qui DIT qu'elle a echoue et
    pourquoi. Rendre `""` laisserait le modele repondre « je ne vois pas
    d'image » de lui-meme — une phrase plausible, jamais la bonne raison, et
    impossible a deboguer.
    """
    if not parle_d_une_image(texte):
        return ""

    from nova.vision.images import (
        ImageIllisible,
        ImageIntrouvable,
        dossiers_surveilles,
        la_plus_recente,
        resoudre,
    )
    from nova.vision.moteur import MoteurOllama, disponible

    utilisable, raison = disponible()
    if not utilisable:
        return _empechement(raison)

    dossiers = dossiers_surveilles()
    try:
        with chrono.mesurer("vision — choix de l'image"):
            if cite := CHEMIN.search(texte):
                cible, devinee = resoudre(cite.group(1), dossiers), False
            else:
                cible, devinee = la_plus_recente(dossiers), True
    except (ImageIntrouvable, ImageIllisible) as absence:
        return _empechement(str(absence))

    try:
        with chrono.mesurer("vision — observation"):
            observation = MoteurOllama(dossiers).decrire(cible)
    # `VisionIndisponible` importe pour etre nomme dans le contrat de ce
    # module, mais on rattrape TOUT : le moteur parle a Ollama par le reseau,
    # et une capacite facultative n'a pas le droit de faire tomber une reponse.
    except Exception as erreur:  # noqa: BLE001
        log.warning("Vision indisponible pendant la conversation : %s", erreur)
        return _empechement(str(erreur))

    quand = _situer(cible)
    provenance = (
        f"Nova ne l'a pas choisie au hasard : c'est la plus recente de ses "
        f"dossiers surveilles, deposee {quand}."
        if devinee
        else "Elle a ete nommee explicitement dans la demande."
    )
    log.info("Regard : %s%s", cible.name, " (la plus recente)" if devinee else "")

    return (
        "## Ce que Nova voit\n\n"
        f"Fichier : {cible.name}"
        + (f" ({quand})" if quand else "")
        + f"\n{provenance}\n\n"
        "Observation du modele de vision :\n"
        f"{observation.description}\n\n"
        "⚠️ Reponds EN FRANCAIS a partir de cette observation, meme si elle "
        "est redigee dans une autre langue. Nomme le fichier que tu as "
        "regarde. N'ajoute rien que l'observation ne dise : si un detail n'y "
        "figure pas, dis que tu ne le distingues pas."
    )


def _empechement(raison: str) -> str:
    """Un bloc qui dit ce qui a empeche de voir, plutot que de se taire."""
    return (
        "## Ce que Nova voit\n\n"
        "Rien : la demande parle d'une image, mais Nova n'a pas pu la "
        f"regarder.\n\nRaison exacte :\n{raison}\n\n"
        "⚠️ Dis-le simplement, en francais, en reprenant cette raison. "
        "N'invente aucune description, et ne pretends pas voir quoi que ce "
        "soit."
    )
