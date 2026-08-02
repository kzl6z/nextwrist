"""Nettoyage de la transcription : enlever ce que personne n'a voulu dire.

CE QU'ON RETIRE, ET POURQUOI C'EST UN ETAGE A PART

Whisper transcrit fidelement — y compris les « euh », les mots repetes et les
phrases abandonnees en cours de route. Fidele n'est pas utile : le modele de
langue recoit alors du bruit qu'il prend pour du sens.

    « euh ouvre ouvre Discord »          -> « ouvre Discord »
    « quelle heure, non, quel jour »     -> « quel jour »
    « c'estquoiça »                      -> « c'est quoi ca »

Cet etage est SEPARE de la correction pour une raison de fond : nettoyer est
sur, corriger est un pari. Retirer un « euh » ne peut pas changer le sens
d'une phrase. Remplacer un mot par un autre, si. Les melanger obligerait a
appliquer au nettoyage la prudence que merite la correction, et on perdrait
les deux.

CE QU'ON NE FAIT PAS

On ne corrige pas la grammaire, on ne devine aucun mot, on ne complete pas
une phrase. Tout ce qui demande de savoir CE QUE la personne voulait dire
appartient a l'etage suivant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Marques d'hesitation. Retirees seulement quand elles sont isolees : « euh »
#: colle a un mot est probablement une syllabe, pas une hesitation.
HESITATIONS: frozenset[str] = frozenset(
    {
        "euh", "euhh", "heu", "hum", "hmm", "hein", "ben", "bah", "bon",
        "alors", "donc", "voila", "quoi", "genre", "enfin", "disons",
    }
)

#: Hesitations qu'on ne retire QU'EN TETE de phrase : ailleurs, ce sont des
#: mots pleins. « Bon, ouvre Discord » n'a pas le meme statut que « c'est
#: bon ».
HESITATIONS_TETE_SEULEMENT: frozenset[str] = frozenset(
    {"alors", "donc", "voila", "bon", "ben", "bah", "quoi", "enfin", "genre", "disons"}
)

#: Marqueurs de changement d'avis. Ce qui les precede est abandonne.
#: « Quelle heure, NON, quel jour » : seul « quel jour » compte.
FAUX_DEPARTS: tuple[str, ...] = (
    "non pardon", "non plutot", "non attends", "pardon", "plutot", "enfin non", "non",
)

#: Mots qui peuvent legitimement se repeter. Les retirer casserait le sens.
REPETITIONS_LEGITIMES: frozenset[str] = frozenset({"tres", "tout", "bien", "plus", "non", "oui"})


@dataclass(frozen=True)
class Nettoyage:
    """Le texte nettoye, et la trace de ce qui a ete retire.

    La trace n'est pas decorative : sans elle, un nettoyage trop zele est
    indebogable. On veut pouvoir dire « j'ai retire trois hesitations » plutot
    que constater un texte different.
    """

    texte: str
    origine: str
    retires: tuple[str, ...] = ()
    #: Le nettoyage a-t-il change quelque chose ?
    modifie: bool = field(default=False)


def _mots(texte: str) -> list[str]:
    """Decoupe en gardant la ponctuation attachee au mot qui precede."""
    return texte.split()


def _nu(mot: str) -> str:
    """Le mot sans sa ponctuation, en minuscules — pour comparer."""
    return mot.strip(" ,.!?;:…«»\"'()").lower()


def retirer_hesitations(mots: list[str]) -> tuple[list[str], list[str]]:
    """Enleve les hesitations isolees. Retourne les mots gardes et les retires.

    La tete est traitee EN BOUCLE, et c'est necessaire : dans « alors donc euh
    lance Spotify », « donc » n'est en tete qu'apres le retrait de « alors ».
    Un seul passage laissait passer la deuxieme hesitation — defaut trouve a
    l'essai, pas en relisant.
    """
    if len(mots) <= 1:
        # Une hesitation seule n'en est pas une : « bon » tout court est une
        # reponse, « non » aussi.
        return mots, []

    retires: list[str] = []
    restants = list(mots)

    # 1. La tete, tant qu'elle est une hesitation.
    while len(restants) > 1 and _nu(restants[0]) in HESITATIONS:
        retires.append(_nu(restants[0]))
        restants.pop(0)

    # 2. Le corps : seules les hesitations pures, jamais les mots qui ne le
    #    sont qu'en tete. « c'est bon » doit rester « c'est bon ».
    gardes: list[str] = []
    for mot in restants:
        nu = _nu(mot)
        if nu in HESITATIONS and nu not in HESITATIONS_TETE_SEULEMENT:
            retires.append(nu)
            continue
        gardes.append(mot)
    return (gardes or restants), retires


def retirer_repetitions(mots: list[str]) -> tuple[list[str], list[str]]:
    """Enleve un mot repete immediatement. « ouvre ouvre » -> « ouvre ».

    Uniquement les repetitions IMMEDIATES : « je veux que tu veux » n'est pas
    une repetition, c'est une phrase. Et certains mots se repetent
    legitimement — « tres tres bien ».
    """
    gardes: list[str] = []
    retires: list[str] = []
    for mot in mots:
        nu = _nu(mot)
        if gardes and nu and nu == _nu(gardes[-1]) and nu not in REPETITIONS_LEGITIMES:
            retires.append(nu)
            continue
        gardes.append(mot)
    return gardes, retires


def couper_au_faux_depart(texte: str) -> tuple[str, str | None]:
    """Garde ce qui suit le dernier changement d'avis.

    « quelle heure, non, quel jour » -> « quel jour »

    On prend le DERNIER marqueur : si la personne se reprend deux fois, c'est
    la derniere version qui vaut. Et on ne coupe que s'il reste quelque chose
    apres — « non » en fin de phrase est une reponse, pas une reprise.
    """
    minuscule = texte.lower()
    meilleure: tuple[int, str] | None = None
    for marqueur in FAUX_DEPARTS:
        # On cherche le marqueur entoure de frontieres de mot, pour ne pas
        # couper sur le « non » de « nonobstant ».
        for trouve in re.finditer(rf"\b{re.escape(marqueur)}\b", minuscule):
            if meilleure is None or trouve.start() > meilleure[0]:
                meilleure = (trouve.start(), marqueur)
    if meilleure is None:
        return texte, None

    debut, marqueur = meilleure
    reste = texte[debut + len(marqueur) :].strip(" ,.…")
    # Il faut qu'il reste une vraie phrase apres, et que ce qui precede en
    # soit une aussi : sinon on n'a pas affaire a une reprise.
    if len(reste.split()) < 2 or len(texte[:debut].split()) < 2:
        return texte, None
    return reste, marqueur


def separer_mots_colles(texte: str) -> str:
    """Reintroduit les espaces apres une apostrophe ou avant une majuscule.

    Whisper colle parfois les mots : « c'estquoi », « ouvreDiscord ». Deux
    cas surs, et seulement ceux-la — separer sur autre chose demanderait un
    dictionnaire et produirait des faux positifs sur les noms propres.
    """
    # Majuscule au milieu d'un mot en minuscules : « ouvreDiscord ».
    texte = re.sub(r"(?<=[a-zàâäéèêëîïôöùûüç])(?=[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ])", " ", texte)
    return re.sub(r"\s{2,}", " ", texte).strip()


#: Le francais met une espace AVANT les signes doubles, pas avant les simples.
#: Confondre les deux collait « Discord ? » en « Discord? », ce qui suffisait
#: a le rendre meconnaissable pour le lexique — et produisait une fausse
#: correction « Discord? » -> « Discord ». Un detail typographique devenu un
#: bug fonctionnel.
_SIGNES_SIMPLES = ",."
_SIGNES_DOUBLES = ";:!?"


def normaliser_ponctuation(texte: str) -> str:
    """Ponctuation francaise : espaces avant les signes doubles, pas les simples.

    Sert autant a l'affichage qu'a la comparaison : un mot suivi d'un signe
    colle n'est plus le meme mot pour qui le cherche dans un lexique.
    """
    texte = texte.replace("…", "...").replace("’", "'")

    # Signes simples : rien avant, une espace apres.
    texte = re.sub(rf"\s+([{re.escape(_SIGNES_SIMPLES)}])", r"\1", texte)
    texte = re.sub(rf"([{re.escape(_SIGNES_SIMPLES)}])(?=[^\s\d])", r"\1 ", texte)

    # Signes doubles : une espace avant ET apres.
    texte = re.sub(rf"\s*([{re.escape(_SIGNES_DOUBLES)}])", r" \1", texte)
    texte = re.sub(rf"([{re.escape(_SIGNES_DOUBLES)}])(?=\S)", r"\1 ", texte)

    texte = re.sub(r"\.{4,}", "...", texte)
    return re.sub(r"\s{2,}", " ", texte).strip()


def nettoyer(texte: str) -> Nettoyage:
    """Le nettoyage complet, dans l'ordre qui compte.

    L'ordre n'est pas arbitraire : on separe les mots colles AVANT de chercher
    les hesitations (sinon « euhouvre » passe au travers), et on coupe au faux
    depart AVANT de retirer les repetitions (sinon on nettoie un fragment
    qu'on va jeter).
    """
    origine = texte
    if not texte or not texte.strip():
        return Nettoyage(texte="", origine=origine)

    travail = separer_mots_colles(texte)
    travail, marqueur = couper_au_faux_depart(travail)

    mots = _mots(travail)
    mots, hesitations = retirer_hesitations(mots)
    mots, repetitions = retirer_repetitions(mots)

    propre = normaliser_ponctuation(" ".join(mots))

    reprise = [f"reprise après « {marqueur} »"] if marqueur else []
    retires = tuple(hesitations + repetitions + reprise)
    return Nettoyage(
        texte=propre,
        origine=origine,
        retires=retires,
        modifie=propre != origine,
    )
