"""Endpoints internes : memoire, ingestion, recherche, sante.

Separes de la passerelle OpenAI parce qu'ils ne suivent aucun standard externe :
ce sont les portes de Nova elle-meme.

Rappel de la regle : une route ne contient AUCUNE logique metier. Elle traduit
du HTTP vers un appel metier, et retour. Toute la logique vit dans les modules.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nova import orchestrator
from nova.core import chrono, plateforme
from nova.db import connection
from nova.documents import ingest, search
from nova.llm.client import LLMClient
from nova.memory import facts

router = APIRouter(tags=["nova"])


class FactIn(BaseModel):
    content: str
    category: str = "profil"
    origin: str = "user"
    source: str | None = None


class IngestIn(BaseModel):
    path: str


@router.get("/health")
def health() -> dict:
    """Etat des trois dependances. Premier reflexe quand quelque chose cloche."""
    status = {"database": False, "llm": False, "documents": 0}
    try:
        with connection() as conn:
            status["documents"] = conn.execute("SELECT count(*) AS n FROM documents").fetchone()[
                "n"
            ]
            status["database"] = True
    except Exception:  # noqa: BLE001
        pass
    status["llm"] = LLMClient().health()
    status["ok"] = status["database"] and status["llm"]
    return status


@router.get("/performance")
def performance() -> dict:
    """Ou sont passees les millisecondes, depuis le demarrage de Nova Core.

    ⚠️ CETTE ROUTE NE MESURE RIEN ELLE-MEME.

    Elle LIT ce que le chemin critique a deja note en passant. C'est ce qui
    la rend honnete : les chiffres viennent de vraies requetes, pas d'un banc
    qui reproduit approximativement ce que fait Nova. Un banc mesure ce qu'on
    a pense a lui faire mesurer ; un releve en production mesure ce qui s'est
    reellement produit, y compris ce qu'on n'avait pas prevu.

    Consequence a connaitre : tant que personne n'a parle a Nova, le releve
    est vide. Ce n'est pas une panne — c'est la difference entre une mesure
    et une simulation.
    """
    return {
        "etapes": chrono.releve(),
        "depuis_secondes": round(chrono.depuis_secondes(), 1),
        "machine": {
            "resume": plateforme.resume(),
            "pagination": str(plateforme.pression_memoire()),
        },
    }


@router.post("/performance/reset", status_code=204)
def reinitialiser_performance() -> None:
    """Repart de zero — pour comparer AVANT et APRES un changement.

    Sans ce bouton, une optimisation se noie dans les mesures qui l'ont
    precedee : la mediane des deux cents derniers appels bouge a peine quand
    les vingt derniers sont deux fois plus rapides.
    """
    chrono.vider()


@router.get("/facts")
def get_facts(status: str | None = None) -> list[dict]:
    return [f.__dict__ for f in facts.list_facts(status=status)]


@router.post("/facts", status_code=201)
def post_fact(payload: FactIn) -> dict:
    if payload.category not in facts.CATEGORIES:
        raise HTTPException(400, f"Categorie inconnue. Attendu : {facts.CATEGORIES}")
    fait = facts.add(
        payload.content,
        category=payload.category,
        origin=payload.origin,
        source=payload.source,
    )
    # Le nom propre que ce fait contient doit etre ENTENDU des la phrase
    # suivante. L'invalidation est ici et non dans `memory/facts.py` : la
    # memoire ne connait pas l'orchestrateur, et la fleche ne remonte jamais.
    orchestrator.oublier_le_vocabulaire()
    return fait.__dict__


@router.post("/facts/{fact_id}/confirm")
def confirm_fact(fact_id: int) -> dict:
    facts.confirm(fact_id)
    orchestrator.oublier_le_vocabulaire()
    return {"ok": True}


@router.delete("/facts/{fact_id}")
def archive_fact(fact_id: int) -> dict:
    facts.archive(fact_id)
    return {"ok": True}


@router.post("/ingest")
def post_ingest(payload: IngestIn) -> dict:
    target = Path(payload.path)
    if not target.exists():
        raise HTTPException(404, f"Chemin introuvable : {target}")
    chunks, files = ingest.ingest_path(target)
    return {"fichiers": files, "morceaux": chunks}


@router.get("/search")
def get_search(q: str, limit: int = 6) -> list[dict]:
    return [
        {
            "document": hit.document_title,
            "section": hit.heading,
            "score": round(hit.score, 5),
            "extrait": hit.content[:400],
        }
        for hit in search.search(q, limit=limit)
    ]
