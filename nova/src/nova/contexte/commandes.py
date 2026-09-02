"""Ce qui, dans une phrase, PILOTE le contexte de travail.

⚠️ RECONNAITRE UN ORDRE EXPLICITE N'EST PAS SIMULER LA COMPREHENSION.

La consigne est nette : pas de regle « si la phrase dit "augmente ca"
alors … », parce que ce serait feindre de comprendre une conversation. Ce
module ne fait rien de tel.

Il reconnait des ORDRES, que l'on prononce pour piloter Nova :

    « ouvre le projet moteur »            ouvrir un projet
    « revenons au projet NOVA »           basculer
    « on va essayer de gagner 15 % »      fixer l'objectif
    « ajoute ca aux prochaines etapes »   noter une tache
    « on a decide d'augmenter le debit »  noter une decision
    « je veux garder ca pour moi »        marquer confidentiel

C'est exactement la meme categorie que « souviens-toi que… » : la personne
DIT ce qu'elle veut. Deduire seule qu'une phrase de conversation contient une
decision serait l'autre chose — celle qu'on ne fait pas, et pour la raison
deja ecrite dans `memory/moteur.py` : au bout d'un an, un contexte devine et
faux vaut moins que pas de contexte du tout.

⚠️ ET « CA » EST RESOLU PAR LE PROPOS PRECEDENT, PAS PAR UNE DEVINETTE.

« ajoute ca aux prochaines etapes » ne porte pas son contenu. Dans une
conversation, « ca » designe ce qu'on vient de dire. On prend donc la phrase
precedente — et Nova ANNONCE ce qu'elle a note, pour qu'on la corrige d'un
mot si elle s'est trompee.

Deviner en silence serait le defaut ; deviner en le disant est une
conversation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from nova.logging_setup import get_logger

log = get_logger(__name__)


def _plat(texte: str) -> str:
    """Minuscules, sans accents, ponctuation en espaces — SANS BOUGER D'UN CRAN.

    ⚠️ CET APLATISSEMENT PRESERVE LES POSITIONS, ET C'EST TOUT SON INTERET.

    Ailleurs dans le projet, aplatir sert a COMPARER : la longueur n'importe
    pas. Ici, on cherche ou commence le contenu — « le projet NOVA », « le
    debit » — pour aller le relire dans le texte D'ORIGINE.

    La premiere version rendait le texte aplati comme contenu. Verifie avant
    d'aller plus loin :

        « ouvre le projet NOVA »        → « C'est ouvert : nova. »
        « on a decide d'augmenter le
          debit »                       → « Decision notee : augmenter le debit »

    Le nom du projet perdait sa casse, et « débit » son accent — dans la base,
    et dans la bouche de Nova, qui le prononce alors de travers.

    Un caractere entre, un caractere sort : « é » devient « e », une virgule
    devient un espace, la longueur ne change jamais. Les positions du motif
    valent donc telles quelles dans l'original.
    """
    sortie = []
    for caractere in texte or "":
        base = unicodedata.normalize("NFD", caractere)[0]
        if not (base.isalnum() or base == "%"):
            base = " "
        sortie.append(base.lower())
    return "".join(sortie)


@dataclass(frozen=True)
class Ordre:
    """Ce que la phrase demande de faire au contexte."""

    genre: str  # ouvrir | basculer | objectif | tache | decision | confidentiel
    contenu: str = ""
    pourquoi: str = ""


#: « ouvre le projet moteur », « on travaille sur le projet NOVA ».
#:
#: ⚠️ LE MOT « PROJET » EST EXIGE, ET C'EST CE QUI REND LA REGLE SURE.
#:
#: Sans lui, « ouvre le dossier » et « ouvre le fichier » tomberaient ici et
#: n'ouvriraient plus rien. Le mot est le signal : on ne devine pas qu'une
#: phrase parle d'un projet, la personne le dit.
#: ⚠️ LE VERBE EST OBLIGATOIRE, ET LA PREMIERE VERSION LE RENDAIT FACULTATIF.
#:
#: Une alternative vide — `…|)` — faisait que TOUTE phrase contenant
#: « projet X » ouvrait le projet. Verifie avant d'aller plus loin :
#:
#:     « c'est quoi le projet moteur ? »   → ouvrait le projet
#:     « le projet moteur avance bien »    → ouvrait « moteur avance bien »
#:     « parle-moi du projet moteur »      → ouvrait le projet
#:
#: Trois questions, trois basculements de contexte. Un assistant qui change de
#: sujet parce qu'on a prononce un nom est pire qu'un assistant qui n'en
#: change jamais : on ne sait plus ou l'on est.
#:
#: Une phrase qui PARLE d'un projet n'ordonne pas de l'ouvrir. Il faut un
#: verbe, et il faut le mot « projet » — deux signaux, comme
#: `demande_de_fichier`, et pour la meme raison.
_OUVRIR = re.compile(
    r"\b(?:ouvre|ouvrir|lance|demarre|commence|"
    r"nouveau|nouvelle|"
    r"on travaille sur|je travaille sur|"
    r"passons? (?:sur|au)|on passe (?:sur|au))\s+"
    r"(?:le |la |mon |ma |un |une |sur le |au )?projets?\s+(?P<nom>.+)$"
)

#: « revenons au projet NOVA », « reviens au projet moteur ».
_BASCULER = re.compile(
    r"\b(?:revenons|revenez|reviens|retour|retourne|on reprend|reprenons)\s+"
    r"(?:a |au |a la |sur |sur le |vers )?(?:le |la |mon |ma )?"
    r"projets?\s+(?P<nom>.+)$"
)

#: « on va essayer de gagner 15 % », « l'objectif c'est de… », « le but est… ».
_OBJECTIF = re.compile(
    r"\b(?:"
    r"l objectif (?:c est|est|sera)|le but (?:c est|est|sera)|"
    # ⚠️ `\s*` ET NON `\s+` APRES CETTE ALTERNATIVE.
    #
    # « essayer de » consomme deja son espace final : exiger un espace de
    # plus faisait echouer « on va essayer de gagner 15 % » — la formulation
    # la plus naturelle des six, et la seule que j'avais ecrite en exemple.
    r"on va (?:essayer de |tenter de )?|on cherche a |"
    r"il faut qu on |je veux qu on |on doit "
    r")\s*(?P<quoi>.+)$"
)

#: « ajoute ca aux prochaines etapes », « ajoute une tache », « il faudra… ».
_TACHE = re.compile(
    r"\b(?:"
    r"ajoute (?:ca |cela |le |la )?(?:a |aux |dans )?(?:nos |les |mes )?"
    r"(?:prochaines etapes|taches|todo|choses a faire)|"
    r"ajoute une tache|note une tache|"
    r"il faudra|il faudrait penser a|pense a"
    r")\s*(?P<quoi>.*)$"
)

#: « on a decide de X parce que Y », « on part sur X ».
_DECISION = re.compile(
    r"\b(?:on a decide (?:de |d )?|on decide (?:de |d )?|on part sur |"
    r"on retient |c est decide[ ,]*)\s*(?P<quoi>.+)$"
)

#: La raison, quand elle est dite dans la meme phrase.
#: ⚠️ « PARCE QU'IL » NE SE TERMINE PAS PAR « QUE ».
#:
#: L'aplatissement rend « parce qu'il n'y a pas de pompe » en « parce qu il n
#: y a pas de pompe » : le motif qui exigeait « parce que » n'attrapait donc
#: aucune des elisions — « qu'il », « qu'on », « qu'elle », « qu'en » — qui
#: sont parmi les plus frequentes du francais parle.
#:
#: La decision etait notee, sa RAISON perdue en silence. C'est-a-dire
#: exactement la colonne pour laquelle `elements.pourquoi` existe.
_PARCE_QUE = re.compile(
    r"\s+(?:parce que|parce qu|car|puisque|vu que)\s+(?P<raison>.+)$"
)

#: « je veux garder ca pour moi », « c'est personnel », « ne partage pas ».
_CONFIDENTIEL = re.compile(
    r"\b(?:"
    r"garde(?:r|s)? (?:ca|cela|le|la) pour (?:moi|nous)|"
    r"c est (?:personnel|confidentiel|prive)|"
    r"(?:ne |n )?(?:le |la )?partage (?:pas|surtout pas)|"
    r"reste entre nous|pas en production"
    r")\b"
)


#: Ouvrir un projet SANS prononcer le mot « projet ».
#:
#: ⚠️ PERSONNE NE DIT « OUVRE LE PROJET FUSEE ». RELEVE EN CONDITIONS REELLES.
#:
#:     « je cherche a creer une fusee »
#:     Nova : rien.
#:
#: `_OUVRIR` exigeait le mot « projet ». Toute la suite en dependait : sans
#: projet actif, l'objectif ne s'enregistre pas, les decisions non plus, et
#: la proposition d'ecrire le dossier ne peut jamais arriver. Une chaine
#: entiere de fonctionnalites restait morte derriere un mot que personne ne
#: prononce.
#:
#: ⚠️ ET CE N'EST PAS UN VERBE SEUL : IL EN FAUT DEUX.
#:
#: Une VOLONTE a la premiere personne — « je cherche a », « j'aimerais » —
#: suivie d'un verbe de FABRICATION. « je cherche mes impots » n'ouvre rien ;
#: « creer un compte » non plus. C'est la conjonction des deux qui dit
#: « j'entreprends quelque chose », et c'est une propriete de la phrase, pas
#: une devinette sur l'intention.
_PROJET_IMPLICITE = re.compile(
    r"\b(?:je (?:cherche a|voudrais|veux|compte|souhaite|pense)|"
    r"j aimerais(?: bien)?|j ai envie de|"
    r"on (?:va|voudrait|aimerait|pense))\s+"
    r"(?:creer|faire|monter|construire|batir|concevoir|developper|fabriquer|"
    r"mettre au point|me lancer dans|nous lancer dans)\s+"
    r"(?P<nom>.+?)\s*$"
)

#: Les articles qu'on retire en tete d'un nom de projet.
#:
#: « une centrale nucleaire » deviendra un DOSSIER sur le Bureau. « une »
#: n'a rien a faire dans un nom de dossier, et on le lit chaque jour.
_ARTICLE = re.compile(r"^(?:un|une|le|la|les|des|du|de la|mon|ma|mes|notre|nos)\s+")

#: Ce qui, derriere un verbe de fabrication, n'est PAS un projet.
#:
#: ⚠️ « J'AIMERAIS CREER UN DOSSIER SUR MON BUREAU » N'OUVRE PAS DE PROJET.
#:
#: C'est une demande de fichier, traitee par `fichiers/creer.py`. Sans cette
#: exclusion, Nova ouvrirait un projet nomme « un dossier sur mon bureau » —
#: et le creerait en base, ou il resterait.
_PAS_UN_PROJET = re.compile(
    r"^(?:un |une |le |la |mon |ma |ce |nouveau |nouvelle )*"
    r"(?:dossier|repertoire|fichier|document|note|compte|rendez vous|rappel)\b"
)


def lire(texte: str, *, propos_precedent: str = "") -> Ordre | None:
    """L'ordre que cette phrase donne au contexte, ou `None`.

    `propos_precedent` sert a resoudre « ca » quand la phrase ne porte pas son
    contenu — « ajoute ca aux prochaines etapes ».
    """
    plat = _plat(texte)
    if not plat.strip():
        return None

    def tel_quel(trouve, groupe: str) -> str:
        """Le contenu du groupe, relu dans le texte D'ORIGINE.

        L'aplatissement preserve les positions : le meme intervalle designe le
        meme morceau, avec ses accents et sa casse.
        """
        return _nettoyer(texte[trouve.start(groupe) : trouve.end(groupe)])

    # ⚠️ LE BASCULEMENT AVANT L'OUVERTURE, ET L'ORDRE EST LE POINT.
    #
    # « revenons au projet NOVA » contient « projet NOVA » et serait attrape
    # par `_OUVRIR` — qui le CREERAIT s'il n'existe pas. Or « revenons »
    # suppose qu'il existe deja : le creer sur un nom mal transcrit
    # fabriquerait un projet fantome qui prendrait la place du vrai.
    if (trouve := _BASCULER.search(plat)) and (nom := tel_quel(trouve, "nom")):
        return Ordre("basculer", nom)

    if (trouve := _OUVRIR.search(plat)) and (nom := tel_quel(trouve, "nom")):
        return Ordre("ouvrir", nom)

    # ⚠️ APRES `_OUVRIR`, ET AVANT TOUT LE RESTE.
    #
    # Apres, parce que « ouvre le projet X » dit deja explicitement ce qu'il
    # veut. Avant `_OBJECTIF`, parce que « on va creer une fusee » porte les
    # deux signaux — « on va » y ouvre un objectif — et qu'un objectif sans
    # projet actif ne s'enregistre nulle part. Ouvrir d'abord, noter ensuite.
    if trouve := _PROJET_IMPLICITE.search(plat):
        brut = plat[trouve.start("nom") : trouve.end("nom")].strip()
        if not _PAS_UN_PROJET.match(brut):
            depart = trouve.start("nom") + len(_article_en_tete(brut))
            if nom := _nettoyer(texte[depart : trouve.end("nom")]):
                return Ordre("ouvrir", nom)

    if _CONFIDENTIEL.search(plat):
        return Ordre("confidentiel")

    if trouve := _DECISION.search(plat):
        quoi = tel_quel(trouve, "quoi")
        pourquoi = ""
        # La raison se cherche dans le contenu ORIGINAL : le motif ne porte
        # que des mots sans accent, il s'y retrouve sans peine.
        if raison := _PARCE_QUE.search(_plat(quoi)):
            pourquoi = _nettoyer(quoi[raison.start("raison") : raison.end("raison")])
            quoi = _nettoyer(quoi[: raison.start()])
        if quoi:
            return Ordre("decision", quoi, pourquoi)

    if trouve := _TACHE.search(plat):
        quoi = tel_quel(trouve, "quoi") or _nettoyer(propos_precedent)
        if quoi:
            return Ordre("tache", quoi)
        # ⚠️ « ajoute ca » SANS RIEN AVANT N'EST PAS UNE TACHE.
        #
        # Noter une chaine vide, ou pire inventer un intitule, ferait une
        # tache que personne n'a demandee et que personne ne reconnaitra.
        log.info("[Contexte] « %s » : rien a noter, aucun propos precedent.", texte[:40])
        return None

    if trouve := _OBJECTIF.search(plat):
        if quoi := tel_quel(trouve, "quoi"):
            return Ordre("objectif", quoi)

    return None


def _nettoyer(brut: str) -> str:
    """Retire la politesse et la ponctuation de bord."""
    texte = re.sub(r"\s+", " ", (brut or "")).strip(" ,.;:!?")
    for queue in (" s il te plait", " stp", " merci", " nova"):
        if texte.endswith(queue):
            texte = texte[: -len(queue)].strip(" ,.;:!?")
    return texte


def _article_en_tete(plat: str) -> str:
    """L'article a retirer devant un nom de projet, ou une chaine vide.

    Rendu comme du TEXTE et non comme une longueur : l'aplatissement preserve
    les positions, donc ce qu'on retire ici se retire du meme nombre de
    caracteres dans l'original — et « l'été » ne devient pas « été » decale
    d'un cran.
    """
    trouve = _ARTICLE.match(plat)
    return trouve.group(0) if trouve else ""
