"""Les agents : des specialistes qui menent une etape a son terme.

OUTIL, AGENT : LA DIFFERENCE EST NETTE ET ELLE COMPTE

    Un OUTIL execute.  Il fait une chose et rend le resultat. Aucun jugement.
    Un AGENT conduit.  Il peut appeler un modele, enchainer des outils, et
                       decider de la suite.

Confondre les deux est le premier pas vers un systeme ou tout appelle tout.
La regle pratique : si ca peut se tester sans modele, c'est un outil.

CE QUI EXISTE AUJOURD'HUI, ET POURQUOI SI PEU

Un seul agent reel : celui de la conversation, qui couvre l'ecrasante
majorite des demandes. Les autres — redaction, code, vision — attendent leur
etape, et surtout attendent d'avoir un modele qui les rende utiles : sur
cette machine, un modele de trois milliards de parametres ne redigera pas un
expose de vingt diapositives.

C'est deliberé. Enregistrer six agents vides donnerait l'illusion d'un
systeme complet et rendrait chaque debogage plus difficile. Le contrat est
pret, le registre est pret ; les agents arriveront quand ils auront quelque
chose a faire.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nova.core import contrats
from nova.core.contrats import Demande, Etape
from nova.core.registre import Registre
from nova.logging_setup import get_logger

log = get_logger(__name__)

registre_agents: Registre = Registre("agent")


class Conversationnel:
    """L'agent du quotidien : il repond.

    Sa fonction de reponse est INJECTEE. Deux consequences, et la seconde est
    la vraie raison :

      1. il se teste sans modele, sans reseau et sans machine ;
      2. il ne sait pas ce qu'est Ollama, ce qui le laissera intact le jour ou
         Ollama disparaitra.
    """

    nom = "conversationnel"
    description = "Repond a une question ou tient la conversation"
    capacites = frozenset({"conversation", "raisonnement", "redaction"})
    # ⚠️ CET ATTRIBUT MANQUAIT, ET SON ABSENCE RENDAIT L'AGENT INUTILISABLE.
    #
    # Le registre exige que tout ce qui s'execute declare ce qu'il en coute si
    # Nova se trompe. Ces agents ont ete ecrits avant ce bareme et jamais mis
    # a jour : `registre_agents.enregistrer` les REFUSAIT donc, silencieusement
    # du point de vue de l'utilisateur, puisque personne ne les enregistrait.
    # Le systeme se presentait comme ayant zero agent — un inventaire exact
    # d'un systeme vide, alors que le code etait la et teste.
    #
    # LECTURE : il parle. Il ne touche a rien.
    niveau = contrats.LECTURE

    def __init__(self, repondre: Callable[[str], str]) -> None:
        self._repondre = repondre

    def peut_traiter(self, etape: Etape) -> bool:
        return etape.capacite in self.capacites

    def executer(self, etape: Etape, demande: Demande) -> Any:
        return self._repondre(demande.texte)


class Documentaire:
    """Repond a partir des documents ingeres, et cite ses sources.

    Separe du conversationnel a dessein : ici, ne pas trouver est une reponse
    legitime — « je n'ai rien la-dessus dans tes documents » vaut mieux qu'une
    invention plausible. Un agent qui a le droit de dire non est un agent
    different.
    """

    nom = "documentaire"
    description = "Cherche dans tes documents et repond en citant ses sources"
    capacites = frozenset({"recherche", "extraction"})
    #: LECTURE : il lit des documents deja ingeres, il n'en modifie aucun.
    niveau = contrats.LECTURE

    def peut_traiter(self, etape: Etape) -> bool:
        return etape.capacite in self.capacites

    def executer(self, etape: Etape, demande: Demande) -> Any:
        from nova.outils import registre_outils

        outil = registre_outils.get("chercher_documents")
        if outil is None:
            return {"trouve": [], "note": "recherche documentaire indisponible"}
        return {"trouve": outil.executer(demande.texte)}


def choisir_agent(etape: Etape) -> Any | None:
    """Le premier agent capable de traiter cette etape.

    Premier et non « meilleur » : departager demanderait un score, donc une
    heuristique, donc un endroit de plus ou se tromper. L'ordre
    d'enregistrement est explicite et suffit tant qu'un seul agent couvre
    chaque capacite.
    """
    if etape.executant and (nomme := registre_agents.get(etape.executant)):
        return nomme
    for agent in registre_agents.tout():
        if agent.peut_traiter(etape):
            return agent
    return None
