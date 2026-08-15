"""API du noyau : ce que Nova a compris, avant qu'elle reponde.

POURQUOI CE POINT D'ENTREE EXISTE

L'exigence est la reactivite : pendant un traitement long, Nova doit
IMMEDIATEMENT montrer qu'elle a compris. Or comprendre et repondre n'ont pas
le meme cout :

    planifier + choisir l'espace   ~0 ms   (aucun appel au modele)
    repondre                        secondes

Les separer en deux points d'entree permet a l'interface d'afficher le plan
tout de suite, puis de laisser la reponse arriver. C'est la difference entre
« elle rame » et « elle travaille » — pour un temps total identique.

    POST /v1/plan        -> ce qu'elle compte faire        (immediat)
    GET  /v1/capacites   -> ce dont elle dispose           (immediat)
    POST /v1/messages    -> la reponse                     (le temps qu'il faut)

Aucun de ces points d'entree ne remplace les autres. Le chemin eprouve n'est
pas touche : c'est la condition pour qu'il n'y ait aucune regression.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from nova import orchestrator
from nova.core import plateforme
from nova.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["noyau"])


class DemandeEntrante(BaseModel):
    texte: str


@router.post("/plan")
def plan(entree: DemandeEntrante) -> dict:
    """Ce que Nova compte faire. Retourne en une milliseconde.

    Aucun appel au modele : le planificateur deterministe reconnait les
    familles connues, et tout le reste est une phrase a laquelle on repond.
    C'est ce qui permet a l'interface d'appeler ce point d'entree a CHAQUE
    demande sans rien ralentir.
    """
    plan, espace = orchestrator.analyser(entree.texte)
    return {
        "demande": plan.demande,
        "direct": plan.direct,
        "origine": plan.origine,
        "espace": espace,
        "etapes": [
            {
                "intitule": etape.intitule,
                "capacite": etape.capacite,
                "depend_de": list(etape.depend_de),
            }
            for etape in plan.etapes
        ],
    }


@router.get("/capacites")
def capacites() -> dict:
    """L'inventaire de Nova : outils, agents, espaces, modeles, machine.

    Destine autant a l'interface — griser ce qui n'est pas disponible plutot
    que de l'offrir puis d'echouer — qu'au debogage : une seule requete dit
    ce que le systeme croit savoir faire.
    """
    from nova.agents import registre_agents
    from nova.espaces import registre_espaces
    from nova.outils import registre_outils
    from nova.vision import disponible as vision_disponible

    machine = plateforme.detecter()
    pression = plateforme.pression_memoire()
    return {
        "machine": {
            "systeme": machine.systeme,
            "architecture": machine.architecture,
            "memoire_go": machine.memoire_go,
            "profil": machine.profil,
            "budget_modele_go": machine.budget_modele_go,
            "menager_le_gpu": machine.menager_le_gpu,
        },
        # Mesure d'INSTANT, contrairement au bloc ci-dessus. C'est la premiere
        # chose a regarder quand la machine se fige : une pagination ne se
        # corrige par aucun reglage d'interface.
        "memoire": {
            "swap_utilise_go": pression.swap_utilise_go,
            "swap_total_go": pression.swap_total_go,
            "pagine": pression.pagine,
            "mesurable": pression.disponible,
        },
        "outils": [
            {"nom": o.nom, "description": o.description} for o in registre_outils.tout()
        ],
        "agents": [
            {"nom": a.nom, "description": a.description} for a in registre_agents.tout()
        ],
        "espaces": [
            {"nom": e.nom, "description": e.description} for e in registre_espaces.tout()
        ],
        "modeles": [
            {"nom": m.nom, "vitesse": m.vitesse, "capacites": sorted(m.capacites)}
            for m in orchestrator.routeur().modeles
        ],
        "vision": vision_disponible(),
    }
