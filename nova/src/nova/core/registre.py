"""Le registre : comment une brique entre dans Nova.

UN SEUL MECANISME POUR QUATRE USAGES

Outils, agents, espaces de travail et modeles ont le meme besoin : etre
declares quelque part, retrouves par nom, et listes par capacite. Ecrire
quatre gestionnaires aurait produit quatre fois le meme code avec trois
divergences — c'est le mode d'echec classique des projets qui grossissent.

    registre_outils  = Registre[Outil]("outil")
    registre_agents  = Registre[Agent]("agent")
    registre_espaces = Registre[EspaceDeTravail]("espace")

Une classe, trois lignes, aucune duplication.

CE QUE CE FICHIER PERMET, ET QUI EST TOUT L'INTERET

Ajouter un outil en 2027 ne demandera de toucher AUCUN fichier existant :

    from nova.core.registre import registre_outils

    @registre_outils.enregistrer
    class Imprimante:
        nom = "imprimante"
        description = "Envoie un document a l'imprimante"
        capacite = "action"
        def executer(self, chemin): ...

C'est la definition operatoire de « extensible » : une capacite nouvelle
n'est pas une modification, c'est un ajout.

POURQUOI LA VALIDATION EST STRICTE

Une brique mal formee doit echouer A L'ENREGISTREMENT, au demarrage, avec un
message qui dit quoi corriger. L'alternative — decouvrir six mois plus tard
qu'un outil n'a jamais eu de `description` — est exactement le genre de dette
qui rend un projet impossible a reprendre.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from nova.core.contrats import CAPACITES_CONNUES, NIVEAUX
from nova.logging_setup import get_logger

log = get_logger(__name__)

T = TypeVar("T")


class ErreurRegistre(ValueError):
    """Une brique refusee a l'enregistrement, avec la raison."""


class Registre(Generic[T]):
    """Collection nommee de briques, validee a l'entree."""

    #: Attributs exiges de toute brique. `capacite` ou `capacites` selon le
    #: genre : un outil fait une chose, un agent en sait plusieurs.
    ATTRIBUTS = ("nom", "description")

    def __init__(self, genre: str) -> None:
        self.genre = genre
        self._entrees: dict[str, T] = {}

    # -- enregistrement ----------------------------------------------------

    def enregistrer(self, brique: type[T] | T) -> type[T] | T:
        """Ajoute une brique. Utilisable comme decorateur.

        Accepte une classe ou une instance : une classe est instanciee sur
        place. Les deux formes existent parce qu'un outil sans etat est plus
        clair en classe decoree, tandis qu'un outil qui prend des reglages a
        la construction doit etre enregistre deja construit.
        """
        instance = brique() if isinstance(brique, type) else brique

        for attribut in self.ATTRIBUTS:
            valeur = getattr(instance, attribut, None)
            if not valeur or not isinstance(valeur, str):
                raise ErreurRegistre(
                    f"{self.genre} « {type(instance).__name__} » : attribut « {attribut} » "
                    f"manquant ou vide. Chaque {self.genre} doit pouvoir se presenter."
                )

        for capacite in self._capacites(instance):
            if capacite not in CAPACITES_CONNUES:
                raise ErreurRegistre(
                    f"{self.genre} « {instance.nom} » : capacite inconnue « {capacite} ».\n"
                    f"Connues : {', '.join(sorted(CAPACITES_CONNUES))}.\n"
                    "Si la capacite est legitime, ajoute-la a CAPACITES_CONNUES — "
                    "c'est un choix d'architecture, pas une faute de frappe."
                )

        # ── LE NIVEAU DE RISQUE EST OBLIGATOIRE, ET SANS DEFAUT ───────────
        #
        # Uniquement pour les briques qui AGISSENT — un espace de travail ou
        # un modele n'execute rien, exiger un niveau d'eux n'aurait pas de
        # sens.
        #
        # Pas de valeur par defaut, et surtout pas LECTURE : un defaut a zero
        # ferait passer pour inoffensif tout outil dont l'auteur a oublie d'y
        # penser — c'est-a-dire exactement ceux dont il faut se mefier. Mieux
        # vaut un demarrage qui echoue avec un message clair qu'un outil qui
        # supprime des fichiers en etant classe « lecture ».
        if callable(getattr(instance, "executer", None)):
            niveau = getattr(instance, "niveau", None)
            if not isinstance(niveau, int) or isinstance(niveau, bool):
                raise ErreurRegistre(
                    f"{self.genre} « {instance.nom} » : attribut « niveau » manquant.\n"
                    "Tout ce qui s'execute doit dire ce qu'il en coute si Nova se "
                    "trompe :\n"
                    "    contrats.LECTURE      lit, ne modifie rien\n"
                    "    contrats.REVERSIBLE   se defait (ouvrir une application)\n"
                    "    contrats.CONSEQUENT   visible par d'autres (envoyer, publier)\n"
                    "    contrats.IRREVERSIBLE ne se defait pas (supprimer, payer)"
                )
            if niveau not in NIVEAUX:
                raise ErreurRegistre(
                    f"{self.genre} « {instance.nom} » : niveau {niveau} inconnu.\n"
                    f"Attendu l'un de : {', '.join(f'{n} ({m})' for n, m in NIVEAUX.items())}."
                )

        if instance.nom in self._entrees:
            raise ErreurRegistre(
                f"{self.genre} « {instance.nom} » deja enregistre. "
                "Deux briques de meme nom : la seconde masquerait la premiere en silence."
            )

        self._entrees[instance.nom] = instance
        log.debug("%s enregistre : %s", self.genre, instance.nom)
        return brique

    # -- consultation ------------------------------------------------------

    @staticmethod
    def _capacites(brique: object) -> frozenset[str]:
        """Lit `capacite` (une) ou `capacites` (plusieurs), indifferemment."""
        if plusieurs := getattr(brique, "capacites", None):
            return frozenset(plusieurs)
        if une := getattr(brique, "capacite", None):
            return frozenset({une})
        return frozenset()

    def get(self, nom: str) -> T | None:
        return self._entrees.get(nom)

    def exiger(self, nom: str) -> T:
        """Comme `get`, mais explique ce qui existe plutot que de rendre None."""
        if brique := self._entrees.get(nom):
            return brique
        disponibles = ", ".join(sorted(self._entrees)) or "aucun"
        raise ErreurRegistre(
            f"{self.genre} « {nom} » introuvable. Disponibles : {disponibles}."
        )

    def tout(self) -> tuple[T, ...]:
        """Dans l'ordre d'enregistrement — donc previsible et reproductible."""
        return tuple(self._entrees.values())

    def par_capacite(self, capacite: str) -> tuple[T, ...]:
        return tuple(b for b in self._entrees.values() if capacite in self._capacites(b))

    def noms(self) -> tuple[str, ...]:
        return tuple(self._entrees)

    def __len__(self) -> int:
        return len(self._entrees)

    def __contains__(self, nom: object) -> bool:
        return nom in self._entrees

    def catalogue(self) -> str:
        """Description lisible de tout ce qui est disponible.

        Destine autant a l'humain qui debogue qu'au modele : c'est ce texte
        qu'on injecte dans un prompt pour qu'il sache ce qu'il peut demander.
        """
        if not self._entrees:
            return f"Aucun {self.genre} disponible."
        lignes = []
        for brique in self._entrees.values():
            capacites = ", ".join(sorted(self._capacites(brique))) or "—"
            lignes.append(f"- {brique.nom} ({capacites}) : {brique.description}")
        return "\n".join(lignes)
