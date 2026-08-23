"""Qui va reellement chercher : Spotlight, ou un parcours a la main.

DEUX MOTEURS, ET LE SECOND N'EST PAS UN BROUILLON

`Spotlight` interroge l'index de macOS. C'est celui qui sert en vrai : il
connait tout le disque, y compris le TEXTE des PDF et des documents, et il
repond en quelques dizaines de millisecondes.

`Parcours` marche les dossiers un par un, et ne regarde que les NOMS. Il
existe pour trois raisons, dans cet ordre d'importance :

    1. les bancs. Un moteur qui ne tourne que sur macOS ne se teste pas —
       et une fonctionnalite qu'on ne teste que sur la machine de
       quelqu'un d'autre, on la casse sans le savoir.
    2. Spotlight peut etre desactive, ou l'index reconstruit.
    3. le jour ou Nova tournera ailleurs que sur un Mac.

⚠️ TROIS GARDE-FOUS, ET AUCUN N'EST DECORATIF

JAMAIS DE SHELL. La regle de `outils/systeme.py`, pour la meme raison :
`mdfind` recoit une LISTE d'arguments. Une phrase transcrite finit dans une
interrogation Spotlight ; passee a un shell, « ; rm -rf ~ » s'executerait.
En liste, c'est un mot qu'on ne trouve pas.

UN DELAI. `mdfind` sur un index en cours de reconstruction peut mettre du
temps. Ce module est appele DANS la question de l'utilisateur : il rend une
liste vide plutot que de faire attendre.

DES ZONES INTERDITES. `~/Library`, les dossiers caches, les depots de code :
des dizaines de milliers de fichiers qui ne sont jamais « mon releve de
compte », et parmi lesquels des trousseaux, des jetons et des clefs. Les
exclure sert la pertinence autant que la prudence.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

from nova.fichiers import Trouvaille
from nova.fichiers.requete import Recherche
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Au-dela, on n'attend plus : la question de l'utilisateur est en cours.
DELAI_S = 6.0

#: Plafond de resultats rapportes par un moteur. Au-dela, ce n'est plus une
#: recherche, c'est un listing — et le classement n'y changerait rien.
PLAFOND = 400

#: Ce qu'on ne parcourt jamais.
#:
#: ⚠️ « Library » PORTE LES TROUSSEAUX, LES JETONS ET LES CACHES.
#:
#: On l'exclut pour la pertinence — personne n'y range ses papiers — et le
#: fait qu'on y trouve aussi des secrets rend l'exclusion non negociable.
DOSSIERS_INTERDITS: frozenset[str] = frozenset(
    {
        "Library", "Applications", "System", "Volumes", "private", "usr", "bin",
        "node_modules", "venv", ".venv", "__pycache__", "site-packages",
        "Trash", "Corbeille", ".git", "build", "dist", "target",
    }
)

#: Ce qu'on ne nomme jamais, meme si Spotlight le connait.
#:
#: Un fichier de clef n'a rien a faire dans une reponse de Nova, et le simple
#: fait d'en donner le chemin est deja un renseignement.
EXTENSIONS_INTERDITES: frozenset[str] = frozenset(
    {".key", ".pem", ".p12", ".keychain", ".env", ".pfx", ".crt", ".cer", ".asc", ".gpg"}
)
#: `.key` est aussi l'extension de Keynote. On ne perd donc pas une
#: presentation : on la retient uniquement quand le type a ete demande.
_RENDUS_SI_DEMANDES: frozenset[str] = frozenset({".key"})

_NOMS_INTERDITS = re.compile(
    r"(?:^|[._-])(?:id_rsa|id_ed25519|secret|secrets|password|passwords|"
    r"credential|credentials|token|apikey|api_key)(?:$|[._-])",
    re.IGNORECASE,
)


def acceptable(chemin: Path, recherche: Recherche | None = None) -> bool:
    """Ce fichier a-t-il le droit d'etre nomme dans une reponse ?"""
    # ⚠️ « .env » N'A PAS D'EXTENSION — SON NOM ENTIER EST L'EXTENSION.
    #
    # `Path("/h/projet/.env").suffix` rend `""` : pour `pathlib`, c'est un
    # fichier CACHE sans suffixe. Le filtre par extension le laissait donc
    # passer, alors qu'il figurait dans la liste des interdits. Releve par le
    # banc, pas par la lecture du code.
    #
    # Ecarter tout fichier cache regle le cas et bien d'autres : `.netrc`,
    # `.npmrc`, `.git-credentials`. Aucun d'eux n'est « mon releve de
    # compte », et tous portent des secrets.
    if chemin.name.startswith("."):
        return False

    extension = chemin.suffix.lower()
    if extension in EXTENSIONS_INTERDITES:
        demande = recherche is not None and extension in recherche.extensions
        if not (extension in _RENDUS_SI_DEMANDES and demande):
            return False
    if _NOMS_INTERDITS.search(chemin.name):
        return False
    return not any(
        part in DOSSIERS_INTERDITS or part.startswith(".")
        for part in chemin.parts[:-1]
    )


def _trouvaille(chemin: Path, *, precis: bool = False) -> Trouvaille | None:
    """Un `Trouvaille` a partir d'un chemin, ou `None` s'il a disparu."""
    try:
        etat = chemin.stat()
    except OSError:
        # Spotlight garde des entrees pour des fichiers deplaces ou
        # supprimes. Les rendre ferait proposer d'ouvrir le vide.
        return None
    return Trouvaille(
        chemin=chemin, modifie=etat.st_mtime, octets=etat.st_size, precis=precis
    )


# ══════════════════════════════════════════════════════════════════════════
#  SPOTLIGHT
# ══════════════════════════════════════════════════════════════════════════
def _echapper(mot: str) -> str:
    """Un mot sur pour une interrogation Spotlight.

    Le mot part dans une chaine entre guillemets. On retire donc tout ce qui
    n'est pas alphanumerique — une precaution de ceinture, la liste
    d'arguments etant deja ce qui rend l'injection impossible.
    """
    return re.sub(r"[^A-Za-z0-9]", "", mot)


def interrogation(mots: Iterable[str], *, tous: bool) -> str:
    """L'interrogation Spotlight pour ces mots.

    `tous` vrai exige que chaque mot soit present — c'est la passe PRECISE.
    Faux se contente d'un seul — c'est la passe LARGE, celle des synonymes.

    Chaque mot est cherche dans le NOM et dans le TEXTE : « releve » peut
    etre le titre du fichier comme le premier mot de la page.
    """
    morceaux = [
        f'(kMDItemFSName == "*{propre}*"cd || kMDItemTextContent == "*{propre}*"cd)'
        for mot in mots
        if (propre := _echapper(mot))
    ]
    if not morceaux:
        return ""
    return (" && " if tous else " || ").join(morceaux)


class Spotlight:
    """L'index que macOS tient deja. Le moteur reel."""

    nom = "spotlight"

    def __init__(self, racines: tuple[Path, ...], *, delai: float = DELAI_S) -> None:
        self.racines = racines
        self.delai = delai

    @staticmethod
    def disponible() -> bool:
        return Path("/usr/bin/mdfind").exists()

    def _lancer(self, question: str) -> list[Path]:
        arguments = ["/usr/bin/mdfind"]
        for racine in self.racines:
            arguments += ["-onlyin", str(racine)]
        arguments.append(question)
        try:
            resultat = subprocess.run(  # noqa: S603
                arguments, capture_output=True, text=True, timeout=self.delai
            )
        except subprocess.TimeoutExpired:
            log.warning("Spotlight n'a pas repondu en %.0f s.", self.delai)
            return []
        except OSError as erreur:
            log.warning("Spotlight injoignable : %s", erreur)
            return []
        if resultat.returncode != 0:
            log.warning("Spotlight a refuse : %s", (resultat.stderr or "").strip())
            return []
        lignes = [ligne for ligne in resultat.stdout.splitlines() if ligne.strip()]
        if len(lignes) > PLAFOND:
            log.info("Spotlight : %d resultats ramenes a %d.", len(lignes), PLAFOND)
        return [Path(ligne) for ligne in lignes[:PLAFOND]]

    def chercher(self, recherche: Recherche) -> list[Trouvaille]:
        """Les fichiers qui correspondent, en deux passes.

        ⚠️ LA PASSE PRECISE D'ABORD, ET C'EST TOUT L'INTERET.

        « releve compte » exige les deux mots : peu de resultats, presque tous
        bons. Si elle ne rend rien, on elargit aux synonymes avec un simple
        OU — beaucoup de resultats, dont le bon, et c'est au classement de le
        remonter.

        Faire l'inverse — chercher large puis affiner — ferait payer le
        parcours du gros ensemble a chaque fois, y compris quand la question
        etait facile.
        """
        vus: dict[Path, Trouvaille] = {}
        passes = [(recherche.mots, True)]
        if len(recherche.elargis) > len(recherche.mots):
            passes.append((recherche.elargis, False))

        for mots, tous in passes:
            question = interrogation(mots, tous=tous)
            if not question:
                continue
            for chemin in self._lancer(question):
                if chemin in vus or not acceptable(chemin, recherche):
                    continue
                if (trouve := _trouvaille(chemin, precis=tous)) is not None:
                    vus[chemin] = trouve
            # Une passe precise qui rend de quoi repondre s'arrete la.
            if tous and len(vus) >= 3:
                break
        return list(vus.values())


# ══════════════════════════════════════════════════════════════════════════
#  LE PARCOURS — LES NOMS SEULEMENT
# ══════════════════════════════════════════════════════════════════════════
#: Profondeur de descente. Plus large que pour les images (2 niveaux), parce
#: qu'un papier administratif est range, souvent profond :
#: « ~/Documents/Administratif/Banque/2024/releve.pdf » fait quatre niveaux.
PROFONDEUR_MAX = 5

#: Plafond d'entrees VISITEES, pas rapportees. Un parcours sans borne dans un
#: dossier de sauvegarde peut durer des minutes — dans la question de
#: l'utilisateur.
VISITES_MAX = 40_000


class Parcours:
    """Le repli : on marche les dossiers, on ne lit que les noms."""

    nom = "parcours"

    def __init__(
        self,
        racines: tuple[Path, ...],
        *,
        profondeur: int = PROFONDEUR_MAX,
        visites: int = VISITES_MAX,
    ) -> None:
        self.racines = racines
        self.profondeur = profondeur
        self.visites = visites

    def _fichiers(self) -> Iterator[Path]:
        restant = self.visites
        for racine in self.racines:
            for dossier, sous_dossiers, noms in os.walk(racine):
                courant = Path(dossier)
                # ⚠️ ON ELAGUE `sous_dossiers` EN PLACE — c'est ce qui evite
                # de DESCENDRE dans une zone interdite, plutot que d'y
                # descendre puis d'en jeter les resultats.
                profondeur = len(courant.relative_to(racine).parts)
                if profondeur >= self.profondeur:
                    sous_dossiers[:] = []
                else:
                    sous_dossiers[:] = [
                        s
                        for s in sous_dossiers
                        if not s.startswith(".") and s not in DOSSIERS_INTERDITS
                    ]
                for nom in noms:
                    restant -= 1
                    if restant <= 0:
                        log.info("Parcours interrompu a %d entrees.", self.visites)
                        return
                    if not nom.startswith("."):
                        yield courant / nom

    def chercher(self, recherche: Recherche) -> list[Trouvaille]:
        """Les fichiers dont le NOM porte un des mots cherches.

        Pas de contenu : lire chaque fichier du disque pour y chercher un mot
        est precisement ce que Spotlight fait a notre place, et ce qu'on ne
        refera pas a la main dans une question.
        """
        cherches = [
            propre for mot in recherche.elargis if (propre := _echapper(mot).lower())
        ]
        annee = str(recherche.annee) if recherche.annee else None
        if not cherches and not annee:
            return []

        trouves: list[Trouvaille] = []
        for chemin in self._fichiers():
            if len(trouves) >= PLAFOND:
                break
            nom = _echapper(chemin.stem).lower()
            porte = any(mot in nom for mot in cherches)
            # Le parcours ne lit que les noms : « precis » veut donc dire que
            # le nom porte tous les mots d'origine, ce qui est verifiable ici.
            precis = bool(recherche.mots) and all(
                _echapper(mot).lower() in nom for mot in recherche.mots
            )
            # Une annee dans le nom suffit quand elle a ete demandee :
            # « releve-2024-03.pdf » se reconnait a ca.
            if not porte and not (annee and annee in chemin.stem):
                continue
            if not acceptable(chemin, recherche):
                continue
            if (trouve := _trouvaille(chemin, precis=precis)) is not None:
                trouves.append(trouve)
        return trouves


def moteur(racines: tuple[Path, ...]):
    """Le meilleur moteur disponible sur cette machine."""
    if Spotlight.disponible():
        return Spotlight(racines)
    log.info("Spotlight absent : recherche par parcours des noms de fichiers.")
    return Parcours(racines)
