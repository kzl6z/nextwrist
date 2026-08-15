"""Ce qui relie une INTENTION a un OUTIL.

POURQUOI CETTE TABLE EST UNE DONNEE PURE

Elle n'importe rien — ni `voice`, ni `outils`. C'est deliberé : la couche voix
sait reconnaitre « ouvre Discord », la couche outils sait ouvrir une
application, et aucune des deux n'a besoin de connaitre l'autre. Seul
l'orchestrateur, qui a le droit de tout connaitre, fait le raccord.

Sans cette separation, ajouter une action obligerait a toucher a la
reconnaissance vocale — et reciproquement.

LE SEUIL DE CONFIANCE, ET POURQUOI IL EST SI HAUT

Reconnaitre une intention n'autorise pas a l'executer. Deux confiances
independantes doivent etre elevees :

    la PAROLE    a-t-on bien entendu la phrase ?      (comprehension)
    l'INTENTION  cette phrase est-elle bien un ordre ? (intentions)

Une seule des deux ne suffit pas. « Sur quelle planete pour lui en ouvrir »
etait une transcription bancale contenant « ouvrir » : intention nette,
parole douteuse. Agir sur ce seul signal aurait lance une application au
milieu d'une question d'astronomie.

Dans le doute, Nova PARLE au lieu d'AGIR. C'est toujours rattrapable dans ce
sens-la, jamais dans l'autre.
"""

from __future__ import annotations

from typing import NamedTuple


class Action(NamedTuple):
    """L'outil a appeler pour une intention, et sous quel argument."""

    outil: str
    #: Nom de l'argument qui recoit la cible. `None` = l'outil n'en prend pas.
    argument: str | None = None
    #: Catalogue contre lequel la cible doit etre confrontee au reel avant
    #: d'atteindre l'outil. `None` = on passe la cible telle quelle.
    #:
    #: POURQUOI UNE DONNEE PLUTOT QU'UN `if` DANS L'ORCHESTRATEUR
    #:
    #: « ouvre X » attend un nom d'application, « cherche X » attend une
    #: question, « envoie a X » attendra un contact. Ecrire `if outil ==
    #: "ouvrir_application"` marcherait aujourd'hui et se dupliquerait a
    #: chaque nouveau catalogue. Le declarer ici garde la connaissance a
    #: l'endroit ou elle se lit.
    catalogue: str | None = None


#: Le seul catalogue existant a ce jour. Nomme plutot qu'ecrit en clair : le
#: jour ou un deuxieme arrive (contacts, fichiers), la faute de frappe se voit
#: au chargement du module et non a l'execution de l'action.
CATALOGUE_APPLICATIONS = "applications"


#: Intention reconnue -> outil a executer.
#:
#: Une intention ABSENTE de cette table n'est pas une erreur : c'est une
#: intention qu'on sait reconnaitre mais pas encore executer. Nova en parle
#: alors normalement, au lieu de refuser ou d'inventer.
ACTIONS: dict[str, Action] = {
    "ouvrir_application": Action("ouvrir_application", "cible", catalogue=CATALOGUE_APPLICATIONS),
    "fermer_application": Action("fermer_application", "cible", catalogue=CATALOGUE_APPLICATIONS),
    "volume_haut": Action("monter_le_son"),
    "volume_bas": Action("baisser_le_son"),
    "silence": Action("couper_le_son"),
    "arret_pc": Action("eteindre_ordinateur"),
}

#: En dessous, on ne declenche RIEN — meme si l'intention est reconnue.
#:
#: 0,90 est le score que `intentions.reconnaitre` accorde a un declencheur
#: place en tete de phrase avec une cible presente. Un declencheur trouve
#: plus loin descend a 0,70 et n'agira donc pas : « je me demande si tu peux
#: ouvrir Discord » se discute, ne s'execute pas.
SEUIL_INTENTION = 0.90


def action_pour(intention: str) -> Action | None:
    """L'outil correspondant a cette intention, ou `None` si aucun."""
    return ACTIONS.get(intention)


def executable(intention: str, confiance_intention: float, parole_sure: bool) -> bool:
    """Cette intention peut-elle etre executee en l'etat ?

    Les trois conditions sont cumulatives, et l'ordre du `and` importe peu :
    ce qui compte est qu'aucune ne puisse etre contournee par les deux autres.
    """
    return (
        intention in ACTIONS
        and confiance_intention >= SEUIL_INTENTION
        and parole_sure
    )
