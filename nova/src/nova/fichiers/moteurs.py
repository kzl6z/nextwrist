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

#: Plafond de resultats rapportes par un moteur.
#:
#: ⚠️ CE PLAFOND TRONQUE UN ENSEMBLE NON TRIE — DONC IL PERD DES REPONSES.
#:
#: `mdfind` ne classe rien : les premiers rendus ne sont pas les meilleurs.
#: Releve sur la machine — 2907 resultats, tronques a 400, zero retenu au
#: classement. Le bon fichier n'etait probablement pas dans les 400.
#:
#: La vraie correction est en amont (`interrogation_par_groupes`, qui ne
#: cherche plus les synonymes dans le TEXTE). Le plafond reste, mais plus
#: haut : ce qu'il coute est une lecture de `stat` par fichier, ce qu'il fait
#: perdre est la reponse.
PLAFOND = 1200

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


def _chemin(mot: str) -> str:
    """Le mot cherche dans le CHEMIN COMPLET, pas dans le seul nom de fichier.

    ⚠️ LE DOSSIER PORTE SOUVENT LE SEUL MOT UTILE, ET JE L'IGNORAIS.

    Releve sur la machine. Le dossier s'appelle « avis d impositions » et
    contient trois fichiers :

        impos 2024 1.pdf     ← « impos », sans le t
        impos 2024 2.pdf     ← « impos », sans le t
        impots 2024 3.pdf    ← le seul que Nova trouvait

    `kMDItemFSName` ne voit que le nom du fichier. Deux avis sur trois
    n'avaient donc aucun mot cherchable — alors que leur dossier les nommait
    tous les trois, sans ambiguite.

    L'incoherence etait interne : `_mots_du_chemin`, cote classement, lisait
    deja le chemin ENTIER. La requete cherchait moins loin que le classement,
    donc le classement n'a jamais eu la chance de faire son travail.
    """
    return f'kMDItemPath == "*{mot}*"cd'


def _texte(mot: str) -> str:
    return f'kMDItemTextContent == "*{mot}*"cd'


def interrogation(mots: Iterable[str], *, tous: bool) -> str:
    """L'interrogation Spotlight pour ces mots, sans notion de synonyme.

    Sert la passe de repli et les bancs. Chaque mot est cherche dans le NOM et
    dans le TEXTE : « releve » peut etre le titre du fichier comme le premier
    mot de la page.
    """
    morceaux = [
        f"({_chemin(propre)} || {_texte(propre)})"
        for mot in mots
        if (propre := _echapper(mot))
    ]
    if not morceaux:
        return ""
    return (" && " if tous else " || ").join(morceaux)


def _meme_mot(a: str, b: str) -> bool:
    """« impots » et « impot » sont le MEME mot. « impots » et « taxe » non.

    ⚠️ LA DIFFERENCE DECIDE DE CE QU'ON CHERCHE DANS LE TEXTE DES DOCUMENTS.

    On dit « mes impotS » et l'avis ecrit « impôt sur le revenu » — au
    singulier. Chercher le texte pour le seul mot prononce raterait le
    document ; l'ouvrir a tous les synonymes ramenerait tout document francais
    contenant « avis ».

    Une variante de nombre ou de genre n'est pas un synonyme, c'est le meme
    mot : elle garde donc le droit d'etre cherchee dans le contenu. Quatre
    lettres communes en prefixe suffisent a le decider, et evitent qu'« an »
    ou « cv » ne s'accrochent a n'importe quoi.
    """
    court, long = sorted((a, b), key=len)
    return len(court) >= 4 and long.startswith(court)


def interrogation_par_groupes(
    groupes: Iterable[frozenset[str]], mots: Iterable[str]
) -> str:
    """L'interrogation qui exige chaque IDEE, en acceptant ses synonymes.

    ⚠️ CETTE FONCTION EXISTE PARCE QUE LA PRECEDENTE RAMENAIT 2907 FICHIERS.

    Releve sur la machine, mot pour mot :

        Recherche de fichier : mots=['avis','imposition','impots'] annee=2004
        Spotlight : 2907 resultats ramenes a 400.
        Fichiers : 5 candidat(s), 0 retenu(s)

    La passe large etait un OU sur toute la famille elargie — « avis »,
    « declaration », « taxe », « fiscal » — cherchee dans le TEXTE de chaque
    fichier du disque. Autant dire : tout document francais un peu long. Le
    plafond de 400 tranchait ensuite au hasard, et le bon fichier n'etait
    peut-etre meme pas dedans. Le classement n'y pouvait plus rien : ce qu'on
    ne lui donne pas, il ne peut pas le remonter.

    Deux corrections, et la seconde est la vraie :

    1. ET ENTRE LES IDEES, OU A L'INTERIEUR. « impots » ET « 2024 », pas
       « impots » OU « avis » OU « taxe ». Chaque groupe de sens doit etre
       represente — c'est la meme notion de groupe que le classement.

    2. ⚠️ UN SYNONYME NE SE CHERCHE QUE DANS LE NOM.

       Un fichier dont le NOM porte « avis » est un avis d'imposition. Un
       fichier dont le CONTENU contient « avis » est n'importe quel document
       francais — le mot y est ordinaire. Les mots reellement prononces
       gardent le droit d'etre cherches dans le texte ; ce sont eux que la
       personne a en tete.
    """
    exiges = {propre for mot in mots if (propre := _echapper(mot))}
    conditions: list[str] = []
    for groupe in groupes:
        variantes: list[str] = []
        for mot in sorted(groupe):
            if not (propre := _echapper(mot)):
                continue
            dans_le_texte = any(_meme_mot(propre, dit) for dit in exiges)
            variantes.append(
                f"({_chemin(propre)} || {_texte(propre)})"
                if dans_le_texte
                else _chemin(propre)
            )
        if variantes:
            conditions.append("(" + " || ".join(variantes) + ")")
    return " && ".join(conditions)


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
            # ⚠️ UNE TRONCATURE N'EST PAS UNE STATISTIQUE, C'EST UNE PERTE.
            #
            # `mdfind` ne trie pas : les 400 gardes sont un echantillon
            # arbitraire, et le bon fichier peut ne pas en faire partie. Le
            # classement ne pourra alors rien remonter, et l'echec ressemblera
            # a « ce fichier n'existe pas ». C'etait le cas sur la machine —
            # 2907 resultats, zero retenu — et la ligne etait en INFO, noyee.
            log.warning(
                "Spotlight : %d resultats, tronques a %d. La recherche est trop "
                "large : le bon fichier peut avoir ete ecarte avant le classement.",
                len(lignes), PLAFOND,
            )
        return [Path(ligne) for ligne in lignes[:PLAFOND]]

    def chercher(self, recherche: Recherche) -> list[Trouvaille]:
        """Les fichiers qui correspondent, en deux passes.

        ⚠️ LA PASSE PRECISE PORTE DEJA LES SYNONYMES, ET C'EST LE CHANGEMENT.

        Elle exige chaque IDEE — « impots » ET « 2024 » — en acceptant pour
        chacune n'importe lequel de ses mots. Elle est donc a la fois etroite
        et tolerante : `avis-imposition-2024.pdf` repond a « mes impots de
        2024 » sans qu'on ait besoin d'une passe large.

        La passe large ne sert plus que de dernier recours, et sur les mots
        REELLEMENT PRONONCES : un OU sur toute la famille elargie ramenait
        2907 fichiers sur cette machine, tranches a 400 au hasard.
        """
        vus: dict[Path, Trouvaille] = {}

        from nova.fichiers.requete import groupes

        precise = interrogation_par_groupes(groupes(recherche.mots), recherche.mots)
        if precise:
            for chemin in self._lancer(precise):
                if not acceptable(chemin, recherche):
                    continue
                if (trouve := _trouvaille(chemin, precis=True)) is not None:
                    vus[chemin] = trouve
        if vus:
            return list(vus.values())

        # Rien de precis : on retente sur les seuls mots prononces, sans
        # exiger qu'ils soient tous la. C'est le filet, pas la methode.
        large = interrogation(recherche.mots, tous=False)
        if large:
            for chemin in self._lancer(large):
                if chemin in vus or not acceptable(chemin, recherche):
                    continue
                if (trouve := _trouvaille(chemin, precis=False)) is not None:
                    vus[chemin] = trouve
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
