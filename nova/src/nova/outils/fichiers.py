"""Les outils de fichiers : retrouver, et ouvrir.

⚠️ CES DEUX OUTILS N'ONT PAS LE MEME NIVEAU, ET C'EST LE SUJET.

`rechercher_fichier` est une LECTURE : il rend des noms, des dossiers et des
dates. Il n'ouvre rien, ne lit aucun contenu, et ne sort pas de la machine.

`ouvrir_fichier` est REVERSIBLE : quelque chose se passe a l'ecran. C'est le
meme niveau qu'`ouvrir_application` et `ouvrir_image`, pour la meme raison —
une fenetre s'ouvre, on la ferme, il ne reste rien.

⚠️ OUVRIR EST BORNE, ET LA BORNE N'EST PAS LA MEME QUE POUR LIRE.

`open` sur un chemin non verifie ouvrirait n'importe quoi : une application,
un script, un fichier de clef. La borne ici est double, et les deux
conditions sont exigees :

    le fichier est SOUS un dossier de recherche declare
    le fichier est ACCEPTABLE au sens de `fichiers/moteurs.py`

La seconde fait le vrai travail : elle ecarte les clefs, les jetons, les
dossiers caches et `~/Library`. Comparer des chaines ne suffirait pas —
`~/Documents/../.ssh/id_rsa` commence bien par `~/Documents`. On resout donc
reellement le chemin avant de comparer, comme `LireFichier` et
`vision/images.py:resoudre`.
"""

from __future__ import annotations

from pathlib import Path

from nova.core import contrats
from nova.logging_setup import get_logger

log = get_logger(__name__)


class FichierRefuse(PermissionError):
    """Le chemin sort de ce que Nova a le droit de toucher."""


def borner(chemin: str, racines: tuple[Path, ...]) -> Path:
    """Le chemin reel, s'il est dans une racine autorisee. Sinon, on refuse."""
    from nova.fichiers.moteurs import acceptable

    if not racines:
        raise FichierRefuse("Aucun dossier de recherche configure pour Nova.")
    if not chemin:
        raise FichierRefuse("Aucun fichier a ouvrir.")

    cible = Path(chemin).expanduser()
    try:
        cible = cible.resolve()
    except OSError as erreur:
        raise FichierRefuse(f"Chemin illisible : {erreur}") from erreur

    dedans = any(
        cible == racine or racine in cible.parents for racine in racines
    )
    if not dedans:
        raise FichierRefuse(
            f"« {cible.name} » sort des dossiers que Nova peut atteindre."
        )
    # Les racines sont deja connues ici : ce qui MENE a un dossier declare
    # n'a pas a etre juge une seconde fois.
    if not acceptable(cible, racines=racines):
        raise FichierRefuse(
            f"Nova ne touche pas a « {cible.name} » : ce genre de fichier est "
            "hors de sa portee."
        )
    if not cible.is_file():
        raise FichierRefuse(f"« {cible.name} » n'existe pas ou n'est pas un fichier.")
    return cible


class RechercherFichier:
    """Retrouve un fichier sur la machine, par son nom, son type et sa date."""

    nom = "rechercher_fichier"
    description = "Retrouve un fichier sur la machine d'apres sa description"
    capacite = "recherche"
    #: Rend des noms et des dates. N'ouvre rien, ne lit aucun contenu.
    niveau = contrats.LECTURE

    def executer(self, description: str, limite: int = 4) -> dict:
        from nova.fichiers.trouver import chercher

        recherche, classes = chercher(description, limite=int(limite))
        return {
            "cherche": " ".join(recherche.mots),
            "annee": recherche.annee,
            "trouves": [
                {
                    "nom": trouve.nom,
                    "chemin": str(trouve.chemin),
                    "dossier": trouve.dossier,
                    "date": trouve.date_lisible(),
                    "octets": trouve.octets,
                    "correspondance": round(note, 2),
                }
                for trouve, note in classes
            ],
        }


class OuvrirFichier:
    """Ouvre un fichier dans l'application par defaut du systeme."""

    nom = "ouvrir_fichier"
    description = "Ouvre un fichier de la machine dans l'application par defaut"
    capacite = "action"
    niveau = contrats.REVERSIBLE

    def executer(self, chemin: str = "") -> str:
        import subprocess

        from nova.fichiers.trouver import dossiers_cherches
        from nova.outils.systeme import DELAI_S, ActionImpossible, _verifier_macos

        _verifier_macos(self.nom)
        cible = borner(chemin, dossiers_cherches())

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
        log.info("Fichier ouvert : %s", cible)
        return f"J'ai ouvert {cible.name}."


def enregistrer_outils_fichiers(registre) -> tuple[str, ...]:
    """Inscrit les outils de fichiers. Rend leurs noms.

    ⚠️ ENREGISTRES MEME QUAND LA RECHERCHE EST DESACTIVEE.

    Meme regle que les outils de vision : un outil qui apparait et disparait
    selon un reglage rend le catalogue different d'une machine a l'autre, et
    tout ce qui en depend — la deduction d'arguments, le routage, les bancs —
    devient impossible a raisonner. Le reglage decide de ce qui SE DECLENCHE
    dans la conversation, pas de ce qui EXISTE.
    """
    inscrits: list[str] = []
    for outil in (RechercherFichier(), OuvrirFichier()):
        if outil.nom not in registre:
            registre.enregistrer(outil)
            inscrits.append(outil.nom)
    return tuple(inscrits)
