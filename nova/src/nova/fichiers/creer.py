"""Creer un dossier sur la machine, a la voix.

⚠️ C'EST LA PREMIERE FOIS QUE NOVA ECRIT SUR LE DISQUE.

Jusqu'ici elle savait DESIGNER un fichier — `fichiers/trouver.py` rend un
nom, un dossier, une date — et l'OUVRIR : une fenetre s'ouvre, on la ferme,
il ne reste rien. Creer laisse une trace apres coup.

⚠️ ET C'EST POURQUOI LA RACINE D'ECRITURE N'EST PAS CELLE DE LECTURE.

`NOVA_FICHIERS_DOSSIERS` vaut « ~ » par defaut, et `settings.py` dit
exactement pourquoi ce n'est pas dangereux : ce reglage elargit ce que Nova a
le droit de NOMMER, pas de lire. Lui faire porter un troisieme sens — ce
qu'elle a le droit de CREER — permettrait a Nova de fabriquer un dossier
n'importe ou dans le dossier personnel, sur une phrase mal transcrite.

La borne n'est donc pas empruntee, elle est ecrite : le Bureau, et rien
d'autre tant que quelqu'un ne l'elargit pas lui-meme
(`NOVA_FICHIERS_CREATION_DOSSIERS`).

⚠️ LE NIVEAU DE RISQUE ETAIT DEJA DECIDE.

`core/contrats.py` definit REVERSIBLE ainsi : « modifie quelque chose, mais
le geste se defait : ouvrir une application, CREER UN DOSSIER, monter le
son ». Le bareme a ete ecrit avant le premier outil qui agit, precisement
pour que ce choix-la ne se decide pas dans l'urgence. On s'y tient : creer un
dossier ne demande pas de confirmation, l'ecraser en demanderait — et c'est
pour cela que cet outil ne remplace jamais rien.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Longueur maximale d'un nom de dossier dicte.
#:
#: Whisper rend parfois une phrase entiere la ou l'on attendait deux mots.
#: Un dossier nomme « moteur electrique et aussi il faudrait que je pense a
#: verifier la garantie avant lundi » est un degat, meme reversible.
NOM_MAX = 60


def _plat(texte: str) -> str:
    """Minuscules, sans accents, ponctuation en espaces — SANS BOUGER D'UN CRAN.

    Un caractere entre, un caractere sort : les positions du motif valent
    telles quelles dans l'original. C'est ce qui permet de relire le NOM dans
    le texte d'origine, avec ses accents et sa casse — « Moteur electrique »
    plutot que « moteur electrique ».

    Meme fonction que `contexte/commandes.py`, meme raison. Elle est recopiee
    plutot qu'importee : `fichiers/` ne depend pas de `contexte/`, et ces deux
    couches doivent pouvoir vivre l'une sans l'autre.
    """
    sortie = []
    for caractere in texte or "":
        base = unicodedata.normalize("NFD", caractere)[0]
        if not base.isalnum():
            base = " "
        sortie.append(base.lower())
    return "".join(sortie)


# ══════════════════════════════════════════════════════════════════════════
#  RECONNAITRE LA DEMANDE — deux signaux, comme ailleurs
# ══════════════════════════════════════════════════════════════════════════

#: Le verbe : quelque chose doit etre FABRIQUE ou RANGE.
_VERBE = re.compile(
    r"\b(?:cree|creer|crees|creez|"
    r"fais|faire|fabrique|"
    r"range|ranger|classe|classer|classes|regroupe|regrouper|"
    r"mets|mettre|"
    r"j aimerais|je voudrais|je veux|il me faudrait|il faudrait)\b"
)

#: L'objet : et cette chose est un dossier.
#:
#: ⚠️ « FICHIER » EST ACCEPTE, ET C'EST UN CHOIX.
#:
#: « j'aimerais que tout soit classe dans un fichier sur mon bureau » designe
#: un DOSSIER : on ne classe pas plusieurs choses dans un fichier. L'usage
#: courant du francais parle de fichier pour un dossier, et refuser cette
#: phrase reviendrait a exiger le mot juste avant d'obeir.
#:
#: Le risque est de creer un dossier quand on voulait un fichier. Il est
#: reversible, et surtout Nova DIT ce qu'elle a fait — « J'ai cree le dossier
#: … » : l'hypothese se corrige d'un mot. C'est la meme regle que le
#: rapprochement phonetique des fichiers.
_OBJET = re.compile(r"\b(?:dossier|repertoire|fichier)s?\b")

#: Le nom donne explicitement.
_APPELE = re.compile(
    r"\b(?:qui s appelle|qui s appellerait|appele|appelee|nomme|nommee|"
    r"du nom de|intitule|intitulee)\s+(?P<nom>.+?)\s*$"
)

#: Le nom colle derriere le mot « dossier ».
_APRES_L_OBJET = re.compile(
    r"\b(?:dossier|repertoire|fichier)s?\s+(?P<nom>.+?)\s*$"
)

#: Ce qui suit n'est pas un nom mais une destination ou une cheville.
_PAS_UN_NOM = re.compile(
    r"^(?:sur|dans|a|au|aux|pour|avec|qui|que|ou|et|de|des|du|la|le|les|"
    r"mon|ma|mes|ce|cette|ici|la bas|s il te plait|stp|nova)\b"
)

#: Le mot qu'on PRONONCE → les noms que le dossier peut porter sur le disque.
#:
#: ⚠️ CETTE TABLE NE DIT PAS OU SONT LES DOSSIERS, ET C'EST VOULU.
#:
#: La premiere version associait « bureau » a « ~/Desktop » en dur. Deux
#: sources de verite pour la meme question — ou Nova a le droit de creer —
#: dont une seule est reglable. Un Bureau ailleurs, un dossier personnel
#: deplace, une machine en anglais : le reglage disait oui, la table disait
#: non, et personne ne voyait laquelle avait tort.
#:
#: Ici on ne fait que TRADUIRE un mot francais en noms de dossier possibles.
#: Ce qui est autorise reste dit par `NOVA_FICHIERS_CREATION_DOSSIERS`, et
#: par lui seul.
DESTINATIONS: dict[str, tuple[str, ...]] = {
    "bureau": ("desktop", "bureau"),
    "desktop": ("desktop", "bureau"),
    "documents": ("documents",),
    "telechargements": ("downloads", "telechargements"),
    "downloads": ("downloads", "telechargements"),
}

_OU = re.compile(
    r"\b(?:sur|dans|a|au|vers)\s+(?:le |la |les |mon |ma |mes |l )?"
    r"(?P<ou>bureau|desktop|documents|telechargements|downloads)\b"
)


@dataclass(frozen=True)
class Demande:
    """Ce que la phrase demande de creer, et ou."""

    #: Vide quand la phrase n'en donne pas — le projet actif prend le relais.
    nom: str = ""
    #: Le mot prononce (« bureau »), pas le chemin. Vide si rien n'est dit.
    ou: str = ""


def demande_de_dossier(texte: str) -> Demande | None:
    """Cette phrase demande-t-elle de creer un dossier ? Sinon `None`.

    ⚠️ DEUX SIGNAUX, ET LES DEUX SONT EXIGES.

    Un verbe seul attrape la moitie du francais parle — « je voudrais savoir
    l'heure ». Le mot « dossier » seul attrape « dans quel dossier est ce
    fichier ? », qui est une question, pas un ordre. Ensemble, ils ne se
    rencontrent guere que dans une demande de creation.
    """
    plat = _plat(texte)
    if not (_VERBE.search(plat) and _OBJET.search(plat)):
        return None

    ou = ""
    if (place := _OU.search(plat)) is not None:
        ou = place.group("ou")

    # ⚠️ LES DEUX MOTIFS NE LISENT PAS LA MEME PORTION, ET IL LE FAUT.
    #
    # « qui s'appelle X » nomme sans ambiguite, ou qu'il soit dans la phrase :
    # « cree-moi un dossier sur le bureau qui s'appelle Moteur » met la
    # destination AVANT le nom. Le chercher dans la seule tete perdait ce
    # nom-la, et Nova demandait comment appeler un dossier qu'on venait de
    # nommer.
    #
    # « dossier X », lui, se lit sur la tete uniquement : sinon « dossier
    # moteur electrique sur mon bureau » donnerait un dossier appele
    # « moteur electrique sur mon bureau ».
    fin = place.start() if place is not None else len(plat)
    portions = ((_APPELE, plat, texte), (_APRES_L_OBJET, plat[:fin], texte[:fin]))

    for motif, cherche, original in portions:
        if (trouve := motif.search(cherche)) is None:
            continue
        depart, bout = trouve.start("nom"), trouve.end("nom")
        # ⚠️ LA DESTINATION PEUT ARRIVER APRES LE NOM, ET IL FAUT LA COUPER.
        #
        # « fais un dossier nomme Impots dans mes documents » : le motif prend
        # tout jusqu'a la fin. Sans cette coupe, le dossier s'appellerait
        # « Impots dans mes documents ».
        if place is not None and depart < place.start() < bout:
            bout = place.start()
        brut = cherche[depart:bout].strip()
        if not brut or _PAS_UN_NOM.match(brut):
            continue
        return Demande(nom=_nom_propre(original[depart:depart + len(brut)]), ou=ou)

    return Demande(nom="", ou=ou)


#: Ce qui n'a rien a faire dans un nom de dossier PRONONCE.
_STRUCTUREL = re.compile(r"[/\\\x00-\x1f]")


def _nom_propre(brut: str) -> str:
    """Un nom de dossier sur, tire de ce qui a ete dit. Vide s'il ne l'est pas.

    ⚠️ ON REFUSE, ON NE REPARE PAS. LA PREMIERE VERSION REPARAIT.

    Elle remplacait les separateurs par des espaces : « ../evade » devenait
    « evade », « .ssh » devenait « ssh ». Rien ne sortait du Bureau — la borne
    tenait — mais Nova creait un dossier que PERSONNE n'avait demande, sous un
    nom qu'elle avait invente, sans le dire.

    Un nom prononce ne contient jamais de « / » ni de « .. ». S'il en porte,
    c'est que la transcription est mauvaise ou que la phrase n'etait pas une
    demande de dossier. Dans les deux cas Nova demande comment appeler ce
    dossier, plutot que d'en fabriquer un au jugé — « dans le doute, Nova
    PARLE au lieu d'AGIR », comme pour les intentions.

    Le reste est du bruit de dictee : espaces multiples, ponctuation finale.
    Celui-la se nettoie, parce qu'il ne change pas ce qui a ete demande.
    """
    brut = (brut or "").strip()
    if _STRUCTUREL.search(brut) or brut.startswith("."):
        return ""
    nom = re.sub(r"\s+", " ", brut).strip(" .-_")
    return nom[:NOM_MAX].strip()


# ══════════════════════════════════════════════════════════════════════════
#  OU NOVA A LE DROIT DE CREER
# ══════════════════════════════════════════════════════════════════════════


def dossiers_ou_creer() -> tuple[Path, ...]:
    """Les racines d'ECRITURE, declarees a part de celles de lecture."""
    from nova.settings import get_settings
    from nova.vision.images import racines

    declares = [
        d.strip()
        for d in get_settings().fichiers_creation_dossiers.split(",")
        if d.strip()
    ]
    return racines(declares)


def destination(ou: str = "") -> Path | None:
    """Le dossier reel ou creer, ou `None` si Nova n'y a pas droit.

    Sans destination prononcee, on prend la premiere racine declaree — le
    Bureau par defaut. Nova la NOMME dans sa reponse : une destination devinee
    qui ne se dit pas est une destination qu'on retrouve trois jours plus
    tard.
    """
    permis = dossiers_ou_creer()
    if not permis:
        return None
    if not ou:
        return permis[0]

    noms = DESTINATIONS.get(ou)
    if noms is None:
        return None
    for racine in permis:
        if _plat(racine.name).strip() in noms:
            return racine
    return None


#: Comment DIRE un dossier, d'apres son nom sur le disque.
_COMME_ON_LE_DIT: dict[str, str] = {
    "desktop": "ton Bureau",
    "bureau": "ton Bureau",
    "documents": "tes Documents",
    "downloads": "tes Téléchargements",
    "telechargements": "tes Téléchargements",
}


def nom_lisible(dossier: Path) -> str:
    """Comment DIRE un dossier. « ton Bureau », pas « /Users/hugo/Desktop ».

    Un chemin absolu prononce a voix haute est illisible, et c'est la meme
    regle que pour les fichiers : Nova dit « ta carte d'identite », pas
    « CNI BERANGERE RECTO-1.png ».
    """
    return _COMME_ON_LE_DIT.get(_plat(dossier.name).strip(), dossier.name or str(dossier))
