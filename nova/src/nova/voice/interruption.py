"""Couper Nova pendant qu'elle parle.

LE DEFAUT

Une reponse partie est une reponse qu'on subit jusqu'au bout. Nova lit sa
phrase, on voit des la premiere seconde qu'elle a mal compris, et il ne reste
qu'a attendre — puis a tout reformuler par-dessus.

    « quelle est la carte la plus rare, Pokemon ? »
    « Je ne trouve pas de CARTE BLANCHE correspondant a un SKATE… »
    « attends — »
    « …les cartes de skate se collectionnent depuis les annees 1990, et… »

C'est le detail qui separe un assistant d'un repondeur : on interrompt un
assistant.

⚠️ CE MODULE NE COUPE PAS LE SON. IL NE PEUT PAS.

C'est l'application de bureau qui joue l'audio, phrase par phrase, en
demandant chaque synthese a `/v1/audio/speech` pendant que le modele ecrit
les suivantes. Nova Core ne tient donc pas le haut-parleur.

Ce qu'elle tient, c'est la SOURCE : le flux de jetons, et la synthese de la
phrase suivante. Une interruption arrete donc Nova a la fin de la phrase en
cours, pas au milieu du mot — et c'est la limite honnete de ce qui se fait
sans toucher a l'application.

    la generation s'arrete           → la machine est rendue immediatement
    la synthese suivante est muette  → Nova se tait a la phrase d'apres

Sur une machine de 8 Go, le premier point compte autant que le second : une
reponse de trois cents mots qu'on n'ecoutera pas occupe le modele pendant que
la question suivante attend.

⚠️ ET CE N'EST PAS UN CONGE.

« attends » ne referme pas la conversation, au contraire : on interrompt
precisement parce qu'on a quelque chose a dire. La fenetre d'ecoute est
prolongee. « c'est bon » et « laisse tomber », eux, coupent ET raccrochent —
c'est `session.demande_de_veille` qui s'en charge, et il passe avant.
"""

from __future__ import annotations

import re
import threading
import unicodedata

from nova.logging_setup import get_logger

log = get_logger(__name__)

_coupee: bool = False
_pourquoi: str = ""
_verrou = threading.Lock()


def _plat(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", sans_accents.lower())).strip()


# ══════════════════════════════════════════════════════════════════════════
#  RECONNAITRE
# ══════════════════════════════════════════════════════════════════════════

#: Ce qui coupe et qui doit etre TOUTE la phrase.
#:
#: ⚠️ « ARRETE » NE PEUT PAS ETRE UN PREFIXE, ET C'EST LE PIEGE.
#:
#: « arrete la musique » est un ordre adresse a autre chose que la parole de
#: Nova. Le traiter comme une interruption suivie d'une commande en ferait
#: « la musique » — une phrase qui ne veut plus rien dire, et qui partirait
#: quand meme au modele.
#:
#: Ces verbes-la prennent un complement. Ils ne coupent donc que seuls.
_COUPE_SEULE = re.compile(
    r"^(?:nova[, ]+)?(?:"
    r"arrete|arretes|arretez|arrete toi|arretez vous|"
    r"arrete de parler|arretez de parler|arrete toi de parler|"
    r"tais toi|taisez vous|chut|silence|"
    r"stop|stoppe|ca suffit"
    r")(?:[, ]+(?:nova|s il te plait|stp|deux secondes|une seconde))*$"
)

#: Ce qui coupe et qui peut etre suivi de la vraie demande.
#:
#: « attends » ne prend pas de complement ici : personne ne dit « attends le
#: bus » a son assistant. Ce qui suit est donc ce qu'on voulait dire — et
#: c'est exactement pour ca qu'on a coupe.
_COUPE_PREFIXE = re.compile(
    r"^(?:nova[, ]+)?(?:"
    r"attends|attend|attendez|"
    r"une seconde|deux secondes|une minute|"
    r"non attends|mais attends"
    r")\b[, ]*"
)

#: Ce qui peut trainer derriere une interruption sans etre une demande.
_QUEUE = frozenset(
    "attends attend attendez stop chut nova la deux une seconde secondes "
    "minute s'il te plait stp euh hein".split()
)


def demande_d_interruption(texte: str) -> bool:
    """Cette phrase demande-t-elle a Nova de se taire ?"""
    plat = _plat(texte)
    if not plat:
        return False
    return bool(_COUPE_SEULE.match(plat) or _COUPE_PREFIXE.match(plat))


def reste_apres(texte: str) -> str:
    """Ce qui suit l'interruption, quand c'est une vraie demande.

    ⚠️ « ATTENDS, OUVRE PLUTOT LE DEUXIEME » EST UNE SEULE PHRASE.

    On coupe parce qu'on a quelque chose a dire. Jeter la suite obligerait a
    la repeter, ce qui rend l'interruption plus couteuse que d'attendre la fin
    — et personne ne s'en servirait.

    Rend une chaine vide quand il ne reste que de l'hesitation ou une autre
    facon de dire « tais-toi ».
    """
    plat = _plat(texte)
    trouve = _COUPE_PREFIXE.match(plat)
    if trouve is None:
        return ""
    suite = plat[trouve.end():].strip()
    if not suite or all(mot in _QUEUE for mot in suite.split()):
        return ""
    return suite


# ══════════════════════════════════════════════════════════════════════════
#  L'ETAT — « tais-toi jusqu'a nouvel ordre »
# ══════════════════════════════════════════════════════════════════════════


def interrompre(pourquoi: str = "") -> None:
    """Coupe la parole en cours. Vaut jusqu'a ce que Nova ait du neuf a dire."""
    global _coupee, _pourquoi
    with _verrou:
        _coupee, _pourquoi = True, pourquoi
    log.info("Interruption : Nova se tait%s.", f" ({pourquoi})" if pourquoi else "")


def interrompue() -> bool:
    """Nova doit-elle se taire ?"""
    with _verrou:
        return _coupee


def raison() -> str:
    """La phrase qui a coupe. Pour le journal et les bancs."""
    with _verrou:
        return _pourquoi


def reprendre() -> None:
    """Nova a du neuf a dire : l'interruption ne vaut plus.

    ⚠️ APPELE QUAND LA NOUVELLE PAROLE SORT, PAS QUAND LA QUESTION ARRIVE.

    Entre l'interruption et la reponse suivante, l'application peut encore
    demander la synthese des phrases qu'elle avait en attente. Lever le
    silence des l'arrivee de la question les laisserait passer : on
    entendrait la fin de la reponse qu'on venait de couper, apres avoir
    parle.

    En le levant au premier mot REELLEMENT produit, la file d'attente de
    l'application se vide en silence pendant que le modele reflechit.
    """
    global _coupee, _pourquoi
    with _verrou:
        etait = _coupee
        _coupee, _pourquoi = False, ""
    if etait:
        log.info("Interruption levee : Nova reprend la parole.")


def oublier() -> None:
    """Remet l'etat a zero. Pour les bancs."""
    global _coupee, _pourquoi
    with _verrou:
        _coupee, _pourquoi = False, ""
