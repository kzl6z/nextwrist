"""Les espaces de travail : le contexte durable d'une suite d'echanges.

CE QU'UN ESPACE N'EST PAS

Ce n'est pas une vue de l'interface. L'application actuelle a des
« workspaces » qui sont des mises en scene : d'ailleurs son propre code le
dit, « tant qu'aucune action reelle n'existe, tous les espaces menent au
centre ».

CE QU'UN ESPACE EST

Ce qui donne un SENS a une suite d'echanges : ou ranger les documents, quels
outils sont pertinents, ce qu'il faut montrer. L'interface s'y adapte —
l'inverse serait l'erreur, car elle changera plusieurs fois d'ici dix ans
tandis que « un projet a des documents et une echeance » restera vrai.

CHAQUE ESPACE EST UN MODULE

Un espace se declare avec son nom, ce qu'il sait faire, et sa capacite a
juger s'il est concerne. Rien d'autre. On peut donc en developper un
separement, le tester seul, et le retirer sans toucher au reste.

    @registre_espaces.enregistrer
    class Impression3D:
        nom = "impression3d"
        description = "Pieces a imprimer, reglages, historique"
        capacites = frozenset({"action", "vision"})
        def accueille(self, demande): ...

POURQUOI UN SCORE ET PAS UN CLASSEMENT

`accueille` rend une pertinence entre 0 et 1 plutot qu'un booleen. Deux
espaces peuvent legitimement convenir — « analyse la video de ma piece
imprimee » releve autant de Vision que d'Impression 3D. Un booleen forcerait
un choix arbitraire ; un score laisse l'arbitrage a l'appelant, et le rend
observable.
"""

from __future__ import annotations

import re
import unicodedata

from nova.core.contrats import Demande
from nova.core.registre import Registre

registre_espaces: Registre = Registre("espace")


def _normaliser(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sans_accents.lower()).strip()


class EspaceParMots:
    """Espace dont la pertinence se juge sur des mots declencheurs.

    Base commune volontairement simple. Un espace qui aura besoin de mieux —
    lire un fichier joint, interroger la memoire, appeler un modele —
    redefinira `accueille` sans rien demander a personne : le contrat est un
    `Protocol`, pas une classe de base imposee.
    """

    nom = "sans-nom"
    description = ""
    capacites: frozenset[str] = frozenset()
    declencheurs: tuple[str, ...] = ()

    def accueille(self, demande: Demande) -> float:
        texte = _normaliser(demande.texte)
        touches = sum(1 for mot in self.declencheurs if mot in texte)
        if not touches:
            return 0.0
        # Deux declencheurs valent mieux qu'un, mais on sature vite : au-dela,
        # ce n'est plus de la pertinence, c'est du bavardage.
        return min(1.0, 0.6 + 0.2 * (touches - 1))


@registre_espaces.enregistrer
class Projet(EspaceParMots):
    nom = "projet"
    description = "Un projet suivi dans la duree : documents, decisions, echeances"
    capacites = frozenset({"raisonnement", "redaction", "recherche"})
    declencheurs = ("projet", "je construis", "je developpe", "mon appli", "avancement")


@registre_espaces.enregistrer
class Etude(EspaceParMots):
    nom = "etude"
    description = "Apprendre un sujet : notes, sources, revisions"
    capacites = frozenset({"recherche", "redaction", "raisonnement"})
    declencheurs = ("expose", "cours", "revision", "apprendre", "etudier", "devoir")


@registre_espaces.enregistrer
class Voyage(EspaceParMots):
    nom = "voyage"
    description = "Preparer un deplacement : dates, itineraire, reservations"
    capacites = frozenset({"recherche", "raisonnement"})
    declencheurs = ("voyage", "vol", "hotel", "itineraire", "sejour", "je pars")


@registre_espaces.enregistrer
class Analyse(EspaceParMots):
    nom = "analyse"
    description = "Comprendre un document ou un jeu de donnees"
    capacites = frozenset({"extraction", "raisonnement"})
    declencheurs = ("analyse", "compare", "resume", "rapport", "donnees", "statistique")


@registre_espaces.enregistrer
class Presentation(EspaceParMots):
    nom = "presentation"
    description = "Construire un expose : plan, diapositives, illustrations"
    capacites = frozenset({"redaction", "vision", "action"})
    declencheurs = ("presentation", "diapo", "powerpoint", "slide", "soutenance")


@registre_espaces.enregistrer
class Code(EspaceParMots):
    nom = "code"
    description = "Ecrire et corriger du logiciel"
    capacites = frozenset({"code", "raisonnement"})
    declencheurs = ("code", "coder", "bug", "fonction", "script", "compile", "programme")


@registre_espaces.enregistrer
class Vision(EspaceParMots):
    nom = "vision"
    description = "Images, videos et camera : reconnaitre, annoter, documenter"
    capacites = frozenset({"vision", "extraction"})
    declencheurs = ("image", "photo", "video", "camera", "scanne", "reconnais")


def choisir_espace(demande: Demande, seuil: float = 0.5):
    """L'espace le plus pertinent, ou `None` si aucun ne l'est vraiment.

    `None` est une reponse legitime et frequente : la plupart des phrases ne
    relevent d'aucun espace. Forcer un rattachement produirait des espaces
    peuples de conversations sans rapport — exactement ce qui rend un second
    cerveau inutilisable au bout de six mois.
    """
    scores = [(espace, espace.accueille(demande)) for espace in registre_espaces.tout()]
    scores = [(e, s) for e, s in scores if s >= seuil]
    if not scores:
        return None
    return max(scores, key=lambda couple: couple[1])[0]
