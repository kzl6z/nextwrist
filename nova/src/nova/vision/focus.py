"""L'image dont on vient de parler.

CE QUI MANQUAIT POUR QUE LA CONVERSATION TIENNE

    — « trouve-moi l'image ou je code l'interface »
      « Je l'ai trouvee : capture-2026-08-19.png, et je l'ai ouverte. »
    — « analyse-la »
      ← quelle image ?

Sans memoire de ce qui vient d'etre designe, « la » ne renvoie a rien : Nova
retombait sur la plus recente du dossier, c'est-a-dire presque toujours une
autre. La reponse etait alors juste sur une image que personne n'avait
demandee — la pire forme d'erreur, puisqu'elle a l'air de marcher.

⚠️ UNE MEMOIRE COURTE, EN MEMOIRE VIVE, ET C'EST DELIBERE.

Elle ne va pas en base : « l'image dont on parle » n'a aucun sens le
lendemain, et la faire survivre a un redemarrage ferait ressurgir un
contexte que plus personne n'a en tete.

Elle EXPIRE, pour la meme raison. Au bout de dix minutes, « analyse-la »
designe autre chose dans la tete de celui qui parle — et se tromper en
silence coute plus cher que redemander.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Au-dela, « la » ne designe plus la meme chose pour personne.
DUREE_S = 600.0


@dataclass(frozen=True)
class Retenue:
    """L'image dont on vient de parler, et depuis quand."""

    chemin: Path
    description: str
    #: Comment on est arrive dessus : « recherche », « regard », « ouverture ».
    #: Sert au journal — une reprise surprenante se diagnostique par la.
    origine: str
    instant: float


_retenue: Retenue | None = None
_verrou = threading.Lock()


def retenir(chemin: Path, *, description: str = "", origine: str = "regard") -> None:
    """Note l'image dont on vient de parler."""
    global _retenue
    with _verrou:
        _retenue = Retenue(Path(chemin), description, origine, time.monotonic())
    log.info("Image retenue (%s) : %s", origine, Path(chemin).name)


def derniere() -> Retenue | None:
    """L'image dont on vient de parler, si elle est encore d'actualite.

    Rend `None` passe le delai : une reprise vers une image oubliee vaut
    mieux qu'une reponse assuree sur la mauvaise.
    """
    with _verrou:
        retenue = _retenue
    if retenue is None:
        return None
    if time.monotonic() - retenue.instant > DUREE_S:
        return None
    # Le fichier a pu etre deplace ou supprime entre-temps. Le verifier ici
    # evite un echec plus loin, sur un chemin qui semblera sorti de nulle part.
    if not retenue.chemin.is_file():
        log.info("Image retenue disparue : %s", retenue.chemin.name)
        return None
    return retenue


def oublier() -> None:
    """Efface la retenue. Pour les bancs, et pour un changement de sujet."""
    global _retenue
    with _verrou:
        _retenue = None
