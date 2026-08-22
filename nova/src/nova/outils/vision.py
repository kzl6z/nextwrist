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


class OuvrirImage:
    """Ouvre une image dans l'application par defaut du systeme.

    ⚠️ POURQUOI CET OUTIL EXISTE SEPAREMENT D'`ouvrir_application`.

    Releve en conditions reelles : « ouvre-moi la derniere image que j'ai
    transferee sur ce PC » produisait

        Je ne trouve pas d'application « derniere image que j'ai
        transferee sur ce PC » sur cette machine.

    Le verbe « ouvre » est capte par la reconnaissance d'intention, qui ne
    connaissait qu'une seule chose a ouvrir : une application. La cible etait
    donc confrontee au catalogue des applications installees, ou elle n'avait
    aucune chance de figurer.

    Le message etait exact et inutile : il decrivait ce que Nova avait
    cherche, pas ce qu'on lui avait demande.

    ⚠️ NIVEAU REVERSIBLE, COMME `ouvrir_application`.

    Une fenetre s'ouvre ; on la ferme et il ne reste rien. Ce n'est pas une
    lecture — quelque chose se passe a l'ecran — mais ca se defait.
    """

    nom = "ouvrir_image"
    description = "Ouvre une image dans l'application par defaut (macOS)"
    capacite = "action"
    niveau = contrats.REVERSIBLE

    def __init__(self, racine: Path | None = None) -> None:
        self.racine = Path(racine) if racine is not None else None

    def _dossiers(self):
        from nova.vision.images import dossiers_surveilles

        return (self.racine,) if self.racine is not None else dossiers_surveilles()

    def executer(self, chemin: str = "") -> str:
        """Ouvre l'image nommee, ou la plus recente si aucune n'est nommee.

        ⚠️ LA BORNE EST LA MEME QUE POUR REGARDER.

        `open` sur un chemin non verifie ouvrirait n'importe quel fichier de
        la machine. Ouvrir n'est pas lire — mais rien ne justifie que le
        chemin soit moins borne ici que dans `decrire_image`, et deux regles
        differentes pour le meme dossier sont une invitation a se tromper.
        """
        import subprocess

        from nova.outils.systeme import DELAI_S, ActionImpossible, _verifier_macos
        from nova.vision.images import la_plus_recente, resoudre

        _verifier_macos(self.nom)
        dossiers = self._dossiers()
        cible = resoudre(chemin, dossiers) if chemin else la_plus_recente(dossiers)

        # Liste d'arguments, jamais une chaine : l'injection devient
        # impossible plutot qu'improbable. Meme regle qu'`ouvrir_application`.
        resultat = subprocess.run(  # noqa: S603
            ["/usr/bin/open", str(cible)],
            capture_output=True, text=True, timeout=DELAI_S,
        )
        if resultat.returncode != 0:
            detail = (resultat.stderr or "").strip()
            raise ActionImpossible(
                f"Impossible d'ouvrir « {cible.name} »." + (f" {detail}" if detail else "")
            )
        log.info("Image ouverte : %s", cible)
        return f"J'ai ouvert {cible.name}."


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
    # `OuvrirImage` sans racine : il consulte les dossiers surveilles, comme
    # le regard. Lui figer une racine ici le limiterait a `data/`, c'est-a-dire
    # a l'endroit ou les images de l'utilisateur ne sont jamais.
    for outil in (DecrireImage(racine), ListerCeQueMontreLImage(racine), OuvrirImage()):
        if outil.nom not in registre:
            registre.enregistrer(outil)
            inscrits.append(outil.nom)
    return tuple(inscrits)
