"""Les outils de vision : regarder une image, et lister ce qu'elle contient.

POURQUOI DES OUTILS EN PLUS DE L'AGENT

    Un OUTIL execute.  On lui donne un chemin, il rend une description.
    Un AGENT conduit.  Il trouve QUELLE image, puis appelle l'outil.

La regle du projet : si ca se teste sans modele, c'est un outil. Ici la
frontiere passe exactement entre les deux — « decris data/piece.jpg » est un
appel, « decris cette image » est un jugement.

Cette separation a une consequence concrete depuis la deduction d'arguments :
un outil qui declare `chemin: str` obtient sa valeur par `core.arguments`, ou
un refus qui NOMME le parametre manquant. L'agent, lui, a le droit de deviner
l'image la plus recente — et de le dire.

⚠️ NIVEAU LECTURE, ET C'EST DISCUTABLE

Regarder une image ne modifie rien : LECTURE est le bon niveau au sens du
bareme. Mais la vision RACONTE le contenu d'un fichier, ce qui en fait un
excellent moyen d'exfiltration si le chemin n'est pas borne. La borne est
donc dans `vision/images.py:resoudre`, au meme endroit et avec la meme regle
que `LireFichier` — pas ici.
"""

from __future__ import annotations

from pathlib import Path

from nova.core import contrats
from nova.logging_setup import get_logger

log = get_logger(__name__)


class DecrireImage:
    """Decrit une image du dossier de travail."""

    nom = "decrire_image"
    description = "Decrit ce qu'on voit sur une image du dossier de travail"
    capacite = "vision"
    #: Lit un fichier image et le donne a regarder. Ne modifie rien.
    niveau = contrats.LECTURE

    def __init__(self, racine: Path) -> None:
        self.racine = Path(racine)

    def executer(self, chemin: str) -> dict:
        from nova.vision.moteur import moteur

        observation = moteur(self.racine).decrire(chemin)
        return {
            "image": observation.source.name,
            "description": observation.description,
            **observation.brut,
        }


class ListerCeQueMontreLImage:
    """Enumere les objets visibles sur une image.

    Separe de `decrire_image` parce que l'etape « Identifier l'objet et ses
    composants » du plan de diagnostic a besoin d'une LISTE, pas d'un
    paragraphe : la suite du plan cherche des pannes connues par nom de piece.
    Un paragraphe l'obligerait a redecouper du texte, donc a se tromper.
    """

    nom = "lister_composants"
    description = "Enumere les objets et pieces visibles sur une image"
    capacite = "extraction"
    niveau = contrats.LECTURE

    def __init__(self, racine: Path) -> None:
        self.racine = Path(racine)

    def executer(self, chemin: str) -> dict:
        from nova.vision.moteur import moteur

        composants = moteur(self.racine).identifier_composants(chemin)
        return {"image": Path(chemin).name, "composants": list(composants)}


def enregistrer_outils_vision(registre, racine: Path) -> tuple[str, ...]:
    """Inscrit les outils de vision. Rend leurs noms.

    ⚠️ ILS SONT ENREGISTRES MEME QUAND LA VISION EST DESACTIVEE.

    C'est deliberé, et c'est l'inverse de ce que j'ai failli faire. Un outil
    absent produit « aucun executant pour la capacite vision » — un message
    qui decrit le systeme comme incomplet. Un outil present qui leve
    `VisionIndisponible` produit « la vision est desactivee, voici comment
    l'activer » : le premier se cherche, le second se corrige.

    C'est la meme lecon que les agents jamais inscrits : ce qui existe doit
    etre visible, y compris quand il ne peut pas encore servir.
    """
    inscrits: list[str] = []
    for outil in (DecrireImage(racine), ListerCeQueMontreLImage(racine)):
        if outil.nom not in registre:
            registre.enregistrer(outil)
            inscrits.append(outil.nom)
    return tuple(inscrits)
