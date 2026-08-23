"""Retrouver un fichier par son nom, son type et sa date — partout sur le PC.

CE QUI EST DEMANDE

    « Nova, retrouve-moi dans mes fichiers mon releve de compte de 2024 »

C'est la meme forme que la recherche d'images, et ce n'est pas le meme
probleme. Le catalogue d'images repond a « celle ou il y a une casquette » :
il cherche dans un CONTENU que Nova a regarde elle-meme. Ici on cherche un
fichier dont on ne se rappelle ni le nom ni l'endroit — seulement ce que
c'est et de quand ca date.

⚠️ ON NE CONSTRUIT PAS UN INDEX. macOS EN TIENT DEJA UN.

C'etait la decision structurante, et l'autre option coutait le projet.
Indexer le disque nous-memes voudrait dire : parcourir des centaines de
milliers de fichiers, en extraire le texte, le vectoriser. Mesure disponible
sur cette machine — 42 IMAGES ont demande entre 6,7 et 14,7 minutes. Un
disque entier se compte en heures de calcul et en gigaoctets de stockage,
sur une machine a 8 Go qui fait deja tourner Whisper et deux modeles.

Spotlight fait exactement ce travail, en continu, depuis l'installation du
systeme. Il indexe les noms ET le texte des PDF, des documents Word, des
Pages, des fichiers texte. Il repond en quelques dizaines de millisecondes.
Le reconstruire moins bien serait le contraire de l'ingenierie.

Ce module traduit donc une phrase francaise en interrogation Spotlight, puis
classe les reponses. Le travail est dans la TRADUCTION, pas dans l'index.

CE QUE CE MODULE NE FAIT PAS, ET IL FAUT LE SAVOIR

Il ne lit le contenu d'aucun fichier. Il rend des noms, des chemins, des
dates et des tailles — de quoi dire « c'est celui-la » et l'ouvrir. Lire
reste borne aux dossiers declares, par `LireFichier` et `vision/images.py`,
avec la meme regle qu'avant : ce module n'elargit pas ce que Nova a le droit
de LIRE, seulement ce qu'elle a le droit de NOMMER.

⚠️ ET SPOTLIGHT NE VOIT PAS CE QU'IL N'A PAS INDEXE.

Un releve de compte SCANNE est une image : aucun texte a l'interieur, donc
seul son nom est cherchable. « IMG_4021.pdf » ne dira jamais « releve ». La
limite est reelle, elle est dite a l'utilisateur quand la recherche echoue,
et c'est mieux que de laisser croire a une panne.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Trouvaille:
    """Un fichier trouve, et ce qu'on en sait sans l'ouvrir."""

    chemin: Path
    #: Date de derniere modification, en secondes depuis l'epoque.
    modifie: float
    octets: int
    #: Vrai si le fichier porte TOUS les mots demandes, faux s'il n'en porte
    #: qu'un par elargissement aux synonymes.
    #:
    #: ⚠️ SANS CETTE DISTINCTION, LE CLASSEMENT EST AVEUGLE.
    #:
    #: Spotlight cherche dans le nom ET dans le texte, et ne dit pas lequel a
    #: repondu. Un fichier dont le nom ne contient aucun mot cherche peut donc
    #: etre soit une trouvaille excellente — les deux mots sont dans la page —
    #: soit un homonyme lointain ramene par un synonyme. Le moteur est le seul
    #: a savoir ; il le dit ici plutot que de laisser deviner.
    precis: bool = False

    @property
    def nom(self) -> str:
        return self.chemin.name

    @property
    def dossier(self) -> str:
        """Le dossier parent, en clair. « ~/Documents/Banque »."""
        parent = str(self.chemin.parent)
        maison = str(Path.home())
        return "~" + parent[len(maison) :] if parent.startswith(maison) else parent

    @property
    def annee(self) -> int:
        return datetime.fromtimestamp(self.modifie).year

    def date_lisible(self) -> str:
        """« 12 mars 2024 » — Nova lit ce texte a voix haute."""
        MOIS = (
            "janvier", "fevrier", "mars", "avril", "mai", "juin",
            "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
        )
        quand = datetime.fromtimestamp(self.modifie)
        return f"{quand.day} {MOIS[quand.month - 1]} {quand.year}"


__all__ = ["Trouvaille"]
