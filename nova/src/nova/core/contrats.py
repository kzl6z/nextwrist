"""Les contrats du noyau : ce que doit fournir une brique pour etre branchee.

CE FICHIER EST LE PLUS IMPORTANT DU PROJET

Tout le reste est remplacable. Ces contrats, non — ou plutot : les changer
casse tout ce qui les implemente. C'est precisement pour ca qu'ils sont
petits, qu'ils ne dependent de rien, et qu'ils ne connaissent ni Ollama, ni
Postgres, ni Electron.

POURQUOI DES `Protocol` ET PAS DES CLASSES DE BASE

Un outil, un agent ou un espace de travail n'a rien a importer de Nova pour
en devenir un. Il lui suffit d'avoir les bons attributs et les bonnes
methodes. C'est du typage structurel :

    class Horloge:
        nom = "horloge"
        description = "Donne l'heure"
        def executer(self, **arguments): ...

    # Aucun héritage, aucun import : c'est deja un outil valide.

Consequence concrete : un module ecrit dans trois ans, sans connaitre ce
fichier, se branche sans modification. Un heritage aurait impose une
dependance vers le noyau, donc un couplage dans le mauvais sens.

LA REGLE DE DEPENDANCE, ETENDUE

    api  ->  orchestrator  ->  core  ->  contrats
                           ->  memory / documents / llm / voice  ->  db

`core` ne connait NI la memoire, NI le moteur d'inference, NI la base. Il ne
manipule que des descriptions et des decisions. C'est ce qui permet de tester
le routage et la planification sans machine, sans modele et sans reseau — et
c'est ce qui les rendra encore vrais quand tout le reste aura change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ── Vocabulaire commun ────────────────────────────────────────────────────
#
# Ces chaines circulent entre le planificateur, le routeur et les agents. Les
# ecrire en clair plutot que dans une enumeration est deliberé : un module
# tiers ne doit pas avoir a importer une enumeration pour dire ce qu'il sait
# faire. Le prix a payer est une faute de frappe possible ; le garde-fou est
# `CAPACITES_CONNUES` et le test qui verifie que tout ce qui est declare y
# figure.
CAPACITES_CONNUES: frozenset[str] = frozenset(
    {
        "conversation",     # repondre, expliquer, discuter
        "raisonnement",     # analyser, comparer, critiquer, planifier
        "code",             # ecrire, lire ou corriger du code
        "redaction",        # produire un texte long et structure
        "extraction",       # tirer des donnees structurees d'un texte
        "vision",           # comprendre une image ou une video
        "recherche",        # aller chercher une information
        "action",           # modifier le monde : fichiers, impression, envoi
    }
)


@dataclass(frozen=True)
class Demande:
    """Ce que l'utilisateur veut, avant toute decision.

    Volontairement pauvre : du texte, et de quoi retrouver le fil. Enrichir
    cette structure serait la premiere marche vers un noyau qui sait tout et
    dont plus rien ne peut etre teste isolement.
    """

    texte: str
    conversation: str | None = None
    #: Renseignements que l'appelant possede deja. Sert aux images, aux
    #: fichiers joints, au contexte d'un espace de travail.
    pieces: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Etape:
    """Une etape d'un plan. Ce qu'il faut faire, et par quoi."""

    intitule: str
    capacite: str
    #: Outil ou agent pressenti. `None` = le gestionnaire choisira.
    executant: str | None = None
    #: Indices des etapes dont celle-ci depend. Vide = peut demarrer tout de
    #: suite. C'est ce qui permettra plus tard de paralleliser sans rien
    #: reecrire ici.
    depend_de: tuple[int, ...] = ()


@dataclass(frozen=True)
class Plan:
    """La reponse du planificateur : ce que Nova compte faire, et pourquoi.

    Un plan est une DONNEE, pas une execution. On peut donc l'afficher, le
    journaliser, le faire valider, le rejouer — et surtout le tester sans
    rien executer.
    """

    demande: str
    etapes: tuple[Etape, ...]
    #: Comment ce plan a ete obtenu : « modele », « deterministe », « repli ».
    #: Sans cette trace, un plan bizarre est indebogable.
    origine: str = "deterministe"

    @property
    def direct(self) -> bool:
        """Une seule etape de conversation : rien a orchestrer.

        Le cas de loin le plus frequent — « quelle heure est-il », « merci ».
        Le detecter explicitement evite de faire tourner une machinerie
        d'agents pour une phrase.
        """
        return len(self.etapes) == 1 and self.etapes[0].capacite == "conversation"


@dataclass(frozen=True)
class Modele:
    """Description d'un modele disponible, telle que le routeur la voit.

    Aucune de ces valeurs n'est devinee : `scripts/bench_models.py` les
    mesure sur la machine reelle. C'est la lecon la plus chere du projet —
    une fiche technique ne dit pas si un modele est utilisable ici.
    """

    nom: str
    capacites: frozenset[str]
    #: Jetons par seconde en ecriture, mesures.
    vitesse: float = 0.0
    #: Taille sur disque en Go. Sert a departager a capacites egales : le plus
    #: gros est le plus capable.
    poids: float = 0.0
    #: Le modele monologue-t-il avant de repondre ? Disqualifiant pour le
    #: vocal, quelles que soient ses autres qualites.
    raisonne_a_voix_haute: bool = False
    #: Sort-il de la machine ? Le local est prefere a competence egale.
    distant: bool = False


# ── Contrats structurels ──────────────────────────────────────────────────


@runtime_checkable
class Outil(Protocol):
    """Une capacite concrete : lire un fichier, imprimer, ouvrir un navigateur.

    Un outil est SYNCHRONE et RETOURNE UNE VALEUR. Il ne parle pas a
    l'utilisateur, il ne decide de rien : il fait une chose et rend le
    resultat. C'est ce qui le rend testable et remplacable.
    """

    nom: str
    description: str
    capacite: str

    def executer(self, **arguments: Any) -> Any:
        """Fait le travail. Leve une exception en cas d'echec."""
        ...


@runtime_checkable
class Agent(Protocol):
    """Un specialiste qui mene une etape a son terme.

    La difference avec un outil : un agent peut appeler un modele, enchainer
    plusieurs outils, et decider. Un outil execute, un agent conduit.
    """

    nom: str
    description: str
    capacites: frozenset[str]

    def peut_traiter(self, etape: Etape) -> bool:
        """Cet agent sait-il faire cette etape ?"""
        ...

    def executer(self, etape: Etape, demande: Demande) -> Any:
        ...


@runtime_checkable
class EspaceDeTravail(Protocol):
    """Un contexte de travail durable : un projet, un voyage, une etude.

    Ce n'est pas une vue de l'interface. C'est ce qui donne un SENS a une
    suite d'echanges : ou ranger les documents, quels outils sont pertinents,
    quoi montrer. L'interface s'y adapte, l'inverse serait une erreur.
    """

    nom: str
    description: str
    capacites: frozenset[str]

    def accueille(self, demande: Demande) -> float:
        """Pertinence de cet espace pour cette demande, de 0 a 1."""
        ...
