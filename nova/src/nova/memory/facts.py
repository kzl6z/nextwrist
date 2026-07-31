"""Memoire semantique : les faits stables.

C'est la piece la plus importante de la V1, et la plus simple techniquement.

Principe de conception (docs/nova/01-architecture.md) : cette table reste PETITE
— quelques centaines de lignes — et elle est injectee TELLE QUELLE dans le prompt
systeme, sans recherche vectorielle. C'est ce qui donne l'impression que Nova te
connait des le premier mot.

Chercher les faits par similarite serait une erreur : le fait important est
souvent celui qui ne ressemble pas a la question.
"""

from __future__ import annotations

from nova.db import connection
from nova.memory.models import Fact
from nova.settings import get_tuning

CATEGORIES = ("profil", "projet", "preference", "contrainte", "objectif")


def _row_to_fact(row: dict) -> Fact:
    return Fact(
        id=row["id"],
        category=row["category"],
        content=row["content"],
        status=row["status"],
        origin=row["origin"],
        confidence=row["confidence"],
        source=row["source"],
        created_at=row["created_at"],
    )


def add(
    content: str,
    *,
    category: str = "profil",
    origin: str = "user",
    status: str | None = None,
    confidence: float = 1.0,
    source: str | None = None,
) -> Fact:
    """Ajoute un fait.

    Regle de conception : ce que TU declares est confirme d'office ; ce que le
    MODELE deduit entre en `proposed` et attend ta validation. C'est la
    protection contre le pourrissement de la memoire (risque R5) — sans elle,
    Nova devient confiante et fausse au bout d'un an.
    """
    if status is None:
        status = "confirmed" if origin == "user" else "proposed"

    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO facts (category, content, status, origin, confidence, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (category, content, status, origin, confidence, source),
        ).fetchone()
    return _row_to_fact(row)


def list_facts(status: str | None = None, category: str | None = None) -> list[Fact]:
    """Liste les faits, du plus recent au plus ancien."""
    clauses, params = ["status <> 'archived'"], []
    if status:
        clauses, params = ["status = %s"], [status]
    if category:
        clauses.append("category = %s")
        params.append(category)

    with connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM facts WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [_row_to_fact(r) for r in rows]


def confirm(fact_id: int) -> None:
    """Valide un fait propose. C'est le geste de la revue du matin (V0.3)."""
    with connection() as conn:
        conn.execute(
            "UPDATE facts SET status = 'confirmed', reviewed_at = now() WHERE id = %s",
            (fact_id,),
        )


def archive(fact_id: int) -> None:
    """Archive au lieu de supprimer.

    Un fait devenu faux garde de la valeur : l'historique de tes changements
    d'avis est une information, pas un dechet.
    """
    with connection() as conn:
        conn.execute(
            "UPDATE facts SET status = 'archived', archived_at = now() WHERE id = %s",
            (fact_id,),
        )


def render_for_prompt() -> str:
    """Rend les faits confirmes sous forme de bloc injectable dans le prompt.

    Groupes par categorie : un modele suit nettement mieux une liste structuree
    qu'un paragraphe continu.
    """
    facts = list_facts(status="confirmed")[: get_tuning().faits_max]
    if not facts:
        return ""

    by_category: dict[str, list[str]] = {}
    for fact in facts:
        by_category.setdefault(fact.category, []).append(fact.content)

    lines = ["## Ce que tu sais de ton interlocuteur", ""]
    for category in CATEGORIES:
        if items := by_category.get(category):
            lines.append(f"**{category.capitalize()}**")
            lines.extend(f"- {item}" for item in items)
            lines.append("")
    return "\n".join(lines).strip()
