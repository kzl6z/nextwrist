"""Vision : les contrats. La mise en oeuvre est dans `moteur.py`.

CE FICHIER A ETE ECRIT AVANT QUE LA VISION EXISTE, ET C'EST SA VALEUR

Il ne decrivait que des CONTRATS — `Observation`, `Region`, les capacites,
la place dans le registre — et levait `PasEncoreImplemente` partout, avec ce
qui manquait exactement. Quand la vision est arrivee, elle s'est branchee
sans rien renegocier : aucun format n'a bouge. C'est ce qui evite qu'un
chantier commence par trois semaines de discussion sur les structures.

CE QUI VOIT AUJOURD'HUI, ET CE QUI NE VOIT TOUJOURS PAS

    decrire une image           ✅  vision/moteur.py
    lister ce qu'elle contient  ✅  vision/moteur.py
    localiser dans l'image      ❌  demande des coordonnees fiables
    analyser une video          ❌  demande un decoupage en images-cles
    trouver une documentation   ❌  demande un acces reseau et une politique
    reconstruire en 3D          ❌  un projet, pas une fonction

`MoteurVision` ci-dessous reste le contrat de reference : toutes ses methodes
levent. `MoteurOllama` en implemente deux. Garder les deux separes permet de
voir d'un coup d'oeil ce qui manque encore — une classe unique melangerait
le fait et la promesse.

⚠️ CE QUE LA VISION COUTE SUR CETTE MACHINE

    nova-leger (modele de langue)   1,9 Go resident
    un multimodal utilisable         1,7 a 3 Go

Sur 8 Go partages avec macOS et l'interface, les deux ne tiennent pas
ensemble : Ollama en decharge un pour charger l'autre, et le rechargement
coute un forfait mesure de 21 secondes qui frappe la reponse SUIVANTE. La
vision est donc desactivee par defaut, et `moteur.disponible()` dit pourquoi
plutot que de rendre « non ».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PasEncoreImplemente(NotImplementedError):
    """Fonction dont le contrat existe mais pas encore la mise en oeuvre."""


@dataclass(frozen=True)
class Region:
    """Une zone d'interet dans une image, en coordonnees relatives.

    Relatives (0 a 1) et non en pixels : une annotation reste valable apres
    redimensionnement, et l'interface n'a pas a connaitre la resolution
    d'origine.
    """

    x: float
    y: float
    largeur: float
    hauteur: float
    etiquette: str = ""
    confiance: float = 0.0


@dataclass(frozen=True)
class Observation:
    """Ce que la vision a compris d'une image ou d'une video.

    `description` est toujours renseignee ; `regions` et `composants` peuvent
    rester vides selon la finesse du modele employe. Une structure unique
    pour tous les niveaux d'analyse evite de multiplier les formats — et donc
    les conversions, qui sont ou se perd l'information.
    """

    source: Path
    description: str
    regions: tuple[Region, ...] = ()
    composants: tuple[str, ...] = ()
    #: Tout ce que le modele a produit et qu'on ne sait pas encore ranger.
    #: Preferable a une perte : on saura quoi en faire plus tard.
    brut: dict[str, Any] = field(default_factory=dict)


class MoteurVision:
    """Le contrat de la vision. Aucune methode n'est implementee.

    Le jour ou un modele multimodal sera disponible, il suffira d'ecrire une
    classe avec ces methodes et de l'enregistrer : aucun appelant ne changera.
    """

    nom = "vision"
    description = "Analyse d'images, de videos et de flux camera"
    capacites = frozenset({"vision", "extraction"})

    def decrire(self, image: Path) -> Observation:
        raise PasEncoreImplemente(
            "La description d'image demande un modele multimodal resident "
            "(~4 Go). Sur 8 Go partages avec le modele de langue, ce n'est pas "
            "realiste : voir docs/nova/12-profil-mac-m1-8go.md."
        )

    def detecter(self, image: Path) -> tuple[Region, ...]:
        raise PasEncoreImplemente(
            "La detection d'objets demande un modele de detection dedie, ou un "
            "multimodal capable de localiser."
        )

    def analyser_video(
        self, video: Path, images_par_seconde: float = 1.0
    ) -> tuple[Observation, ...]:
        raise PasEncoreImplemente(
            "L'analyse video demande le decoupage en images-cles, puis une "
            "description par image. Le cout est celui de `decrire`, multiplie."
        )

    def identifier_composants(self, image: Path) -> tuple[str, ...]:
        raise PasEncoreImplemente(
            "L'identification de composants demande un modele specialise ou un "
            "acces a une base de references."
        )

    def documenter(self, composant: str) -> dict[str, Any]:
        raise PasEncoreImplemente(
            "La recherche de documentation demande un acces reseau et une "
            "politique de sortie de donnees : c'est une decision, pas un detail."
        )

    def preparer_reconstruction(self, vues: tuple[Path, ...]) -> dict[str, Any]:
        raise PasEncoreImplemente(
            "La reconstruction 3D par photogrammetrie est un projet a part "
            "entiere, pas une fonction. Le contrat existe pour que le jour "
            "venu, elle n'ait pas a etre renegociee."
        )


def disponible() -> bool:
    """La vision est-elle utilisable ?

    ⚠️ CETTE FONCTION RENDAIT `False` EN DUR, ET C'EST DEVENU FAUX.

    C'etait exact tant que rien ne voyait. Depuis `vision/moteur.py`, la
    reponse depend des reglages — et une fonction qui repond « non » alors
    que oui est exactement le genre de mensonge que ce fichier s'engageait a
    ne pas faire. Elle delegue donc a l'endroit qui sait.

    `moteur.disponible()` rend en plus la RAISON, ce qu'un booleen ne peut
    pas faire : « pas active » et « pas de modele » demandent deux gestes
    differents. Les appelants qui ont besoin du remede l'utilisent
    directement ; celui-ci reste pour qui n'a besoin que du oui ou du non.
    """
    from nova.vision.moteur import disponible as _detail

    utilisable, _ = _detail()
    return utilisable
