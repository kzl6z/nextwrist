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


@router.get("/facts")
def get_facts(status: str | None = None) -> list[dict]:
    return [f.__dict__ for f in facts.list_facts(status=status)]


@router.post("/facts", status_code=201)
def post_fact(payload: FactIn) -> dict:
    if payload.category not in facts.CATEGORIES:
        raise HTTPException(400, f"Categorie inconnue. Attendu : {facts.CATEGORIES}")
    return facts.add(
        payload.content,
        category=payload.category,
        origin=payload.origin,
        source=payload.source,
    ).__dict__


@router.post("/facts/{fact_id}/confirm")
def confirm_fact(fact_id: int) -> dict:
    facts.confirm(fact_id)
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
