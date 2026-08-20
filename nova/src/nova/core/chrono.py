"""Ou passent les millisecondes de Nova.

POURQUOI CE MODULE EXISTE

Ce projet a deja paye trois fois le meme prix pour avoir optimise sans
mesurer, et les trois fois sont ecrites dans le code :

    orchestrator.py   « Le filtre de pertinence a divise le prompt par deux
                      (3376 -> 1812) sans changer le temps avant le premier
                      mot (5,1 -> 5,2 s). » Deux tours perdus a raccourcir
                      un prompt qui n'etait pas le goulot.

    api/app.py        « Un cout FIXE de 21 secondes, identique pour un prompt
                      de 880 et de 6573 caracteres. C'est cette independance
                      a la taille de l'entree qui trahit un chargement. »

    settings.py       Un aller-retour complet entre `base` et `small`, dans
                      les deux sens, parce que la precision se mesurait a
                      l'oreille et la vitesse pas du tout.

Le point commun n'est pas la difficulte du probleme : c'est qu'a chaque fois
le chiffre qui aurait tranche n'existait pas. Les journaux disaient « c'est
lent » ; ils ne disaient pas OU.

CE QUE CE MODULE EST, ET CE QU'IL N'EST PAS

Il n'est pas un profileur. Un profileur repond a « quelle fonction consomme
le CPU », question qu'on se pose une fois par an. Celle qu'on se pose ici,
apres chaque phrase, est « quelle ETAPE a pris ce temps » — et les etapes
sont connues d'avance : entendre, comprendre, chercher, penser, parler.

Il tient donc un releve par etape nommee, sur une fenetre glissante. Pas de
trace, pas d'arbre d'appels, pas d'echantillonnage : un dictionnaire de files
bornees. C'est ce qui lui permet de tourner EN PERMANENCE, y compris sur une
machine de 8 Go qui pagine — un outil de mesure qu'on doit penser a activer
n'est jamais actif le jour ou ca rate.

⚠️ POURQUOI DES CENTILES ET PAS UNE MOYENNE

Une moyenne cache exactement ce qu'on cherche. Neuf transcriptions a 200 ms
et une a 8 secondes donnent une moyenne de 980 ms : ni le cas normal, ni le
cas qui fait dire « c'est lent ». Le p95 montre le second, la mediane le
premier, et l'ecart entre les deux est le diagnostic.

    from nova.core import chrono

    with chrono.mesurer("transcription"):
        ...

    chrono.releve()   # {'transcription': {'n': 12, 'median': 210.4, ...}}
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager

#: Nombre de mesures gardees par etape.
#:
#: ⚠️ CETTE BORNE N'EST PAS UNE PRECAUTION DE STYLE.
#:
#: Nova tourne des heures. Une liste non bornee croitrait a chaque phrase
#: prononcee, et l'outil charge de diagnostiquer la pression memoire en
#: deviendrait une cause — sur 8 Go, c'est exactement le genre de fuite lente
#: qu'on met des semaines a soupconner.
#:
#: 200 couvre une longue session de travail tout en tenant dans quelques
#: kilo-octets par etape.
FENETRE = 200


class _Registre:
    """Les mesures, protegees par un verrou.

    Le verrou est necessaire et il est bon marche : Nova sert plusieurs
    requetes en parallele (la synthese d'une phrase pendant que le modele
    ecrit la suivante), et `deque.append` sur une deque bornee est deja
    atomique — le verrou ne protege que la creation de la file.
    """

    def __init__(self) -> None:
        self._verrou = threading.Lock()
        self._files: dict[str, deque[float]] = {}
        self._depart = time.time()

    def enregistrer(self, nom: str, ms: float) -> None:
        file = self._files.get(nom)
        if file is None:
            with self._verrou:
                file = self._files.setdefault(nom, deque(maxlen=FENETRE))
        file.append(ms)

    def releve(self) -> dict[str, dict[str, float]]:
        with self._verrou:
            instantane = {nom: list(file) for nom, file in self._files.items()}
        return {nom: _statistiques(valeurs) for nom, valeurs in instantane.items() if valeurs}

    def vider(self) -> None:
        with self._verrou:
            self._files.clear()
            self._depart = time.time()

    @property
    def depuis(self) -> float:
        return time.time() - self._depart


_registre = _Registre()


def _centile(triees: list[float], part: float) -> float:
    """Centile par interpolation lineaire, sans numpy.

    numpy ferait la meme chose, mais ce module doit pouvoir tourner dans
    n'importe quelle installation de Nova — y compris celles ou la brique
    vocale, qui traine numpy, n'est pas installee. Une mesure qui exige une
    dependance optionnelle n'est pas disponible le jour ou l'on en a besoin.
    """
    if not triees:
        return 0.0
    if len(triees) == 1:
        return triees[0]
    position = part * (len(triees) - 1)
    bas = int(position)
    haut = min(bas + 1, len(triees) - 1)
    reste = position - bas
    return triees[bas] * (1 - reste) + triees[haut] * reste


def _statistiques(valeurs: list[float]) -> dict[str, float]:
    triees = sorted(valeurs)
    return {
        "n": len(triees),
        "median": round(_centile(triees, 0.50), 1),
        "p95": round(_centile(triees, 0.95), 1),
        "min": round(triees[0], 1),
        "max": round(triees[-1], 1),
        "total": round(sum(triees), 1),
    }


@contextmanager
def mesurer(nom: str) -> Iterator[None]:
    """Chronometre un bloc, meme s'il leve.

    ⚠️ LE `finally` N'EST PAS UNE POLITESSE.

    Une etape qui echoue est precisement celle qu'on veut mesurer : une
    transcription qui part en erreur au bout de huit secondes a coute ces
    huit secondes a l'utilisateur, exactement comme si elle avait reussi. Ne
    mesurer que les succes rendrait les pannes invisibles au chronometre.
    """
    debut = time.perf_counter()
    try:
        yield
    finally:
        _registre.enregistrer(nom, (time.perf_counter() - debut) * 1000)


def enregistrer(nom: str, ms: float) -> None:
    """Note une duree deja mesuree ailleurs.

    Sert aux etapes chronometrees par un autre etage — le temps avant le
    premier jeton, par exemple, se mesure a l'interieur d'une boucle de flux
    et pas autour d'elle.
    """
    _registre.enregistrer(nom, ms)


def releve() -> dict[str, dict[str, float]]:
    """Les statistiques par etape, dans l'ordre alphabetique des noms."""
    return dict(sorted(_registre.releve().items()))


def depuis_secondes() -> float:
    """Depuis combien de temps ces mesures s'accumulent."""
    return _registre.depuis


def vider() -> None:
    """Repart de zero. Sert a comparer AVANT et APRES un changement."""
    _registre.vider()
