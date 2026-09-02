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
    #: « image » ou « fichier ».
    #:
    #: ⚠️ CE CHAMP EMPECHE UN PDF D'ARRIVER DANS LE MOTEUR DE VISION.
    #:
    #: La recherche de fichiers retient ce qu'elle vient de trouver ici meme —
    #: « l'objet dont on parle » est le meme concept, et deux memoires
    #: paralleles auraient diverge. Mais « decris-moi la photo » apres une
    #: recherche de releve bancaire ne doit pas envoyer un PDF a moondream :
    #: le genre est ce qui permet a chaque cote de ne reprendre que ce qui le
    #: concerne.
    genre: str = "image"
    #: Les autres candidats presentes en meme temps, DANS L'ORDRE ANNONCE.
    #:
    #: ⚠️ CE QUI PERMET « OUVRE LE DEUXIEME ».
    #:
    #: Nova annonce parfois plusieurs fichiers — trois avis d'imposition qui
    #: se valent, qu'elle refuse d'ouvrir au hasard. « Le deuxieme » ne
    #: designe alors rien si l'on n'a garde que le meilleur.
    #:
    #: ⚠️ ET C'EST ICI, PAS DANS UNE SECONDE MEMOIRE.
    #:
    #: Une liste rangee ailleurs aurait son propre delai d'expiration, et les
    #: deux finiraient par se contredire : « la » designant un fichier et
    #: « le deuxieme » un autre, tires de deux instants differents. La liste
    #: qu'on a annoncee et le fichier dont on parle sont la meme chose vue de
    #: deux facons ; ils vivent et meurent ensemble.
    liste: tuple[Path, ...] = ()
    #: Les mots de la DEMANDE qui a mene ici — « une casquette blanche ».
    #:
    #: ⚠️ CE QU'ON REDIT N'EST JAMAIS LE NOM DU FICHIER.
    #:
    #: Releve en conditions reelles : « ouvre la photo ou je tiens une
    #: casquette » ne partage aucun mot avec « IMG_8156.JPG », et ne peut pas
    #: en partager. Le resolveur comparait au nom, ne trouvait rien, et la
    #: cible partait au catalogue des applications.
    #:
    #: Ce que la personne repete, c'est SA PROPRE DEMANDE. On la garde.
    demande: str = ""


_retenue: Retenue | None = None
_verrou = threading.Lock()


def retenir(
    chemin: Path,
    *,
    description: str = "",
    origine: str = "regard",
    genre: str = "image",
    liste: tuple[Path, ...] = (),
    demande: str = "",
) -> None:
    """Note le fichier dont on vient de parler, et ceux annonces avec lui."""
    global _retenue
    with _verrou:
        _retenue = Retenue(
            Path(chemin),
            description,
            origine,
            time.monotonic(),
            genre,
            tuple(Path(c) for c in liste),
            demande,
        )
    log.info("%s retenu (%s) : %s", genre.capitalize(), origine, Path(chemin).name)


def derniere(genre: str | None = None) -> Retenue | None:
    """Ce dont on vient de parler, si c'est encore d'actualite.

    `genre` filtre : « image » ne rend rien quand la derniere chose retenue
    etait un PDF, et inversement. Sans lui, on rend ce qu'il y a.

    Rend `None` passe le delai : une reprise vers une image oubliee vaut
    mieux qu'une reponse assuree sur la mauvaise.
    """
    with _verrou:
        retenue = _retenue
    if retenue is None:
        return None
    if genre is not None and retenue.genre != genre:
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
