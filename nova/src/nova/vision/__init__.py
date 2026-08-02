"""Vision : l'architecture, pas encore les fonctions.

⚠️ CE MODULE NE VOIT RIEN AUJOURD'HUI. C'EST VOLONTAIRE ET C'EST ECRIT.

Un module qui pretend faire quelque chose et ne le fait pas est pire que son
absence : on l'appelle, il rend une valeur vide, et on cherche le bug
ailleurs. Chaque fonction ci-dessous leve donc `PasEncoreImplemente` avec ce
qui manque exactement pour qu'elle marche.

CE QUE CE FICHIER APPORTE MALGRE TOUT

Les CONTRATS. Quand la vision arrivera, elle se branchera sans rien renegocier :
les structures de donnees qui circulent, les capacites declarees, la place
dans le registre. C'est ce qui evite qu'un chantier de six mois commence par
trois semaines de discussion sur les formats.

CE QUE LA VISION DEMANDERA, HONNETEMENT

    analyser une image        un modele multimodal resident (~4 Go)
    analyser une video        le meme, plus un decoupage en images-cles
    utiliser la camera        un flux, cote application, pas ici
    reconnaitre un objet      un modele de detection, ou le multimodal
    identifier ses composants un modele specialise, ou une recherche web
    trouver sa documentation  un acces reseau et une politique de sortie
    annoter                   un rendu, donc l'interface
    reconstruire en 3D        plusieurs vues + photogrammetrie : un projet
                              a part entiere, pas une fonction

Sur un Mac de 8 Go, un modele multimodal resident A COTE du modele de langue
n'est pas realiste. La mesure de la session le dit sans ambiguite : chaque
megaoctet resident se paie deux fois, en memoire puis en lenteur de tout le
reste. La vision viendra avec plus de memoire vive, ou en deportant l'analyse.

Le dire maintenant evite d'y revenir dans trois mois en se demandant pourquoi
« c'est lent ».
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
    """La vision est-elle utilisable ? Non, et il faut pouvoir le demander.

    Toute capacite du projet expose cette question. C'est ce qui permet a
    l'interface de griser un bouton plutot que de l'offrir puis d'echouer.
    """
    return False
