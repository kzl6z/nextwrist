"""L'inventaire des applications REELLEMENT installees sur la machine.

LE TROU QUE CE FICHIER BOUCHE

`ouvrir_application` recevait un texte que personne ne confrontait a la
realite. « ouvre Ecoledirecte » lancait `open -a "Ecoledirecte"`, macOS ne
trouvait rien, et Nova annoncait un echec sans pouvoir dire mieux. Elle ne
pouvait pas proposer le bon nom : elle ne savait pas lesquels existent.

Un assistant qui agit sur une machine doit connaitre cette machine. C'est la
difference entre « je n'ai pas reussi » et « tu veux dire EcoleDirecte ? ».

CE QUE CE MODULE NE FAIT PAS, ET POURQUOI C'EST DELIBERE

Il ne compare pas les SONS. La ressemblance phonetique est le travail de
`voice/lexique.py`, et le raccord est celui de l'orchestrateur — seul module
autorise a connaitre les deux. Ici on lit un disque, rien d'autre.

LA TENTATION QU'IL FALLAIT REFUSER

Verser ces deux cents noms dans le lexique general de correction aurait
paru malin : Nova entendrait mieux les noms d'applications. Elle entendrait
SURTOUT moins bien le reste. « Notes », « Pages », « Livres », « Musique »,
« Contacts », « Plans » sont des mots francais ordinaires avant d'etre des
applications ; les y mettre ferait corriger des phrases qui n'avaient rien
demande. Le catalogue ne sert donc qu'a UN endroit — la ou une cible est
forcement une application, c'est-a-dire apres « ouvre ». Le contexte y leve
l'ambiguite, et nulle part ailleurs.
"""

from __future__ import annotations

import os
import threading
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from nova.logging_setup import get_logger

log = get_logger(__name__)

SUFFIXE = ".app"

#: Ou macOS range les applications. L'ordre n'a pas d'importance : les noms
#: sont dedupliques et tries a la fin.
DOSSIERS: tuple[Path, ...] = (
    Path("/Applications"),
    Path("/System/Applications"),
    Path.home() / "Applications",
)

#: Un niveau de sous-dossiers suffit : « /Applications/Utilities/Terminal.app »
#: ou « /Applications/Adobe/Photoshop.app ». Descendre plus bas ne trouverait
#: que des composants internes.
PROFONDEUR_MAX = 2

_cache: tuple[tuple, tuple[str, ...]] | None = None
_verrou = threading.Lock()


def _parcourir(racine: Path, profondeur: int) -> Iterator[str]:
    """Les noms d'applications sous `racine`, sans jamais entrer dans un bundle.

    ⚠️ LE `continue` APRES UN `.app` EST LA REGLE, PAS UN DETAIL.

    Un bundle `.app` est un DOSSIER, et il en contient souvent d'autres :
    Xcode.app abrite une douzaine d'applications internes que personne ne
    lance par la voix. Y descendre remplirait le catalogue de noms parasites
    qui feraient ensuite concurrence aux vrais lors de la comparaison
    phonetique — un catalogue bruite est pire qu'un catalogue court.
    """
    try:
        entrees = list(os.scandir(racine))
    except OSError:
        # Dossier absent ou illisible : ce n'est pas une panne, c'est une
        # machine qui n'a pas ce dossier-la.
        return

    for entree in entrees:
        if entree.name.startswith("."):
            continue
        if entree.name.endswith(SUFFIXE):
            yield entree.name[: -len(SUFFIXE)]
            continue
        if profondeur > 1:
            try:
                dossier = entree.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if dossier:
                yield from _parcourir(Path(entree.path), profondeur - 1)


def _signature() -> tuple:
    """De quoi savoir si le catalogue a change, sans le relire.

    La date de modification d'un dossier change des qu'on y installe ou
    supprime quelque chose. Cinq `stat` coutent quelques microsecondes,
    contre plusieurs millisecondes pour un parcours complet — et surtout,
    une application installee est prise en compte IMMEDIATEMENT, sans delai
    d'expiration a regler.
    """
    marques = []
    for dossier in DOSSIERS:
        try:
            marques.append((str(dossier), os.stat(dossier).st_mtime_ns))
        except OSError:
            marques.append((str(dossier), -1))
    return tuple(marques)


def installees(*, force: bool = False) -> tuple[str, ...]:
    """Les applications installees, triees. Ne leve jamais.

    Un tuple VIDE veut dire « je ne sais pas », pas « il n'y en a aucune » :
    sur une machine qui n'est pas un Mac, ou si les dossiers sont illisibles,
    l'appelant doit continuer comme avant plutot que de tout refuser.
    """
    global _cache

    signature = _signature()
    with _verrou:
        if not force and _cache is not None and _cache[0] == signature:
            return _cache[1]

        noms = sorted(
            {nom for dossier in DOSSIERS for nom in _parcourir(dossier, PROFONDEUR_MAX)},
            key=str.lower,
        )
        if _cache is None or _cache[1] != tuple(noms):
            log.info("Catalogue des applications : %d installee(s).", len(noms))
        _cache = (signature, tuple(noms))
        return _cache[1]


def oublier() -> None:
    """Vide le cache. Pour les tests, et pour un rechargement force."""
    global _cache
    _cache = None


def _clef(nom: str) -> str:
    """Ce qui reste d'un nom quand on retire tout ce qui ne s'entend pas.

    Casse, accents, espaces et ponctuation : « Écoledirecte », « ecole
    directe » et « EcoleDirecte » se ramenent tous a « ecoledirecte ». C'est
    la correspondance exacte au sens de l'oreille, avant toute phonetique.
    """
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", nom) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sans_accents.lower() if c.isalnum())


def resoudre(nom: str) -> str | None:
    """Le nom EXACT de l'application installee qui correspond, ou `None`.

    On rend le nom tel qu'il est ecrit sur le disque, pas tel qu'il a ete
    prononce : c'est celui-la que `open -a` attend.
    """
    cherche = _clef(nom or "")
    if not cherche:
        return None

    catalogue = installees()
    for reel in catalogue:
        if reel == nom:
            return reel
    for reel in catalogue:
        if _clef(reel) == cherche:
            return reel
    return None
