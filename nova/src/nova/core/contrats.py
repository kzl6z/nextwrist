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


# ══════════════════════════════════════════════════════════════════════════
#  LES NIVEAUX DE RISQUE
#
#  ⚠️ CE BAREME EST ECRIT AVANT LE PREMIER OUTIL QUI AGIT, PAS APRES.
#
#  C'est la seule fenetre ou il peut l'etre. Une fois qu'un outil sait
#  supprimer un fichier ou envoyer un message, ajouter des niveaux devient
#  une migration : il faut retrouver tous les appelants, decider pour chacun,
#  et vivre avec ceux qu'on a oublies. Ecrit maintenant, c'est une ligne par
#  outil et le compilateur — enfin, le registre — nous rappelle a l'ordre.
#
#  LE PRINCIPE QUI GOUVERNE TOUT
#
#      Un modele de langue PROPOSE. Il n'AUTORISE jamais.
#
#  Un modele local de trois milliards de parametres se trompe. Il hallucine
#  des noms de fichiers, confond deux applications, prend une transcription
#  bancale pour un ordre. Rien de tout cela n'est grave tant qu'il ne fait
#  que parler. Le jour ou il peut agir, chacune de ces erreurs devient une
#  action reelle sur la machine de quelqu'un.
#
#  Le bareme ne rend pas le modele plus fiable. Il rend ses erreurs
#  RATTRAPABLES — ce qui est la seule chose qu'on puisse garantir.
# ══════════════════════════════════════════════════════════════════════════

#: Lire, chercher, calculer. Ne modifie RIEN. S'execute sans rien demander.
LECTURE = 0

#: Modifie quelque chose, mais le geste se defait : ouvrir une application,
#: creer un dossier, monter le son. Si Nova se trompe, on ferme la fenetre.
REVERSIBLE = 1

#: Consequences durables ou visibles par d'autres : envoyer un message,
#: publier, acheter, ecrire dans un fichier existant. Se defait mal, ou
#: devant temoins.
CONSEQUENT = 2

#: Ne se defait pas : supprimer, formater, eteindre, payer, envoyer un
#: courriel definitif. Une erreur ici ne se rattrape pas.
IRREVERSIBLE = 3

NIVEAUX: dict[int, str] = {
    LECTURE: "lecture",
    REVERSIBLE: "reversible",
    CONSEQUENT: "consequent",
    IRREVERSIBLE: "irreversible",
}

#: A partir d'ici, une confirmation explicite est exigee.
#:
#: Pourquoi 2 et pas 3 : « envoyer un message a la mauvaise personne » ne se
#: defait pas davantage que « supprimer un fichier », et se remarque
#: davantage. Reserver la confirmation a l'irreversible laisserait passer
#: exactement la categorie d'erreurs qui coute le plus cher socialement.
SEUIL_CONFIRMATION = CONSEQUENT


def nom_du_niveau(niveau: int) -> str:
    """Le niveau en toutes lettres. « inconnu » plutot qu'une exception :
    un bareme etendu demain ne doit pas faire tomber un journal."""
    return NIVEAUX.get(niveau, f"inconnu ({niveau})")


def exige_confirmation(niveau: int) -> bool:
    """Cette action doit-elle etre confirmee avant d'etre executee ?

    Un niveau INCONNU exige la confirmation. C'est le seul defaut sur : si
    quelqu'un ajoute un niveau 4 sans toucher a cette fonction, on demande
    au lieu d'agir. L'inverse — agir sur un niveau qu'on ne comprend pas —
    est precisement ce qu'on cherche a rendre impossible.
    """
    return niveau >= SEUIL_CONFIRMATION or niveau not in NIVEAUX


@runtime_checkable
class Outil(Protocol):
    """Une capacite concrete : lire un fichier, imprimer, ouvrir un navigateur.

    Un outil est SYNCHRONE et RETOURNE UNE VALEUR. Il ne parle pas a
    l'utilisateur, il ne decide de rien : il fait une chose et rend le
    resultat. C'est ce qui le rend testable et remplacable.

    `niveau` dit ce qu'il en coute si Nova se trompe d'outil ou d'argument.
    Il n'y a PAS de valeur par defaut a l'usage : le registre refuse un outil
    qui n'en declare pas. Un defaut a LECTURE ferait passer pour inoffensif
    tout outil dont l'auteur a oublie d'y penser — c'est-a-dire exactement
    ceux dont il faut se mefier.
    """

    nom: str
    description: str
    capacite: str
    niveau: int

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
