"""Recherche dans la base documentaire — hybride.

Pourquoi hybride et pas seulement vectoriel :

  - la recherche VECTORIELLE comprend le sens ("financer" trouve "budget"),
    mais elle echoue sur les termes rares : un nom propre, une reference
    produit, un identifiant. Ces mots-la n'ont pas de voisinage semantique.
  - la recherche PLEIN TEXTE trouve exactement ces termes, mais rate toute
    reformulation.

On lance donc les deux et on fusionne par RRF (Reciprocal Rank Fusion) :

    score(document) = somme sur chaque moteur de  1 / (k + rang)

Simple, sans parametre a regler, et regulierement meilleur que des ponderations
savantes. C'est le genre de decision a prendre MAINTENANT : la rattraper plus
tard imposerait de tout re-vectoriser.
"""

from __future__ import annotations

from nova.db import connection
from nova.documents.ranking import reciprocal_rank_fusion
from nova.llm.embeddings import embed_one
from nova.memory.models import SearchHit
from nova.settings import get_tuning


def _vector_ranking(conn, query: str, limit: int) -> list[int]:
    """Classement par proximite semantique. `<=>` = distance cosinus (pgvector)."""
    vector = embed_one(query)
    rows = conn.execute(
        """
        SELECT id
        FROM chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (str(vector), limit),
    ).fetchall()
    return [r["id"] for r in rows]


def _fulltext_ranking(conn, query: str, limit: int) -> list[int]:
    """Classement par correspondance de mots (index GIN, configuration francaise)."""
    rows = conn.execute(
        """
        SELECT id
        FROM chunks
        WHERE tsv @@ plainto_tsquery('french', %s)
        ORDER BY ts_rank(tsv, plainto_tsquery('french', %s)) DESC
        LIMIT %s
        """,
        (query, query, limit),
    ).fetchall()
    return [r["id"] for r in rows]


def search(query: str, limit: int | None = None) -> list[SearchHit]:
    """Retourne les meilleurs extraits pour une question."""
    tuning = get_tuning()
    limit = limit or tuning.extraits_max
    candidates = tuning.candidats_par_moteur

    with connection() as conn:
        rankings = [
            _vector_ranking(conn, query, candidates),
            _fulltext_ranking(conn, query, candidates),
        ]
        scores = reciprocal_rank_fusion(rankings)
        if not scores:
            return []

        best = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]

        # Un seul aller-retour pour recuperer le detail des morceaux retenus.
        rows = conn.execute(
            """
            SELECT c.id, c.heading, c.content, d.title, d.source_path
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ANY(%s)
            """,
            (best,),
        ).fetchall()

    by_id = {r["id"]: r for r in rows}
    return [
        SearchHit(
            chunk_id=cid,
            document_title=by_id[cid]["title"],
            document_path=by_id[cid]["source_path"],
            heading=by_id[cid]["heading"],
            content=by_id[cid]["content"],
            score=scores[cid],
        )
        for cid in best
        if cid in by_id
    ]
