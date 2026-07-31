"""Journal des echanges.

Question legitime : l'interface garde deja l'historique, pourquoi le dupliquer ?

Parce que l'interface est jetable et que la memoire ne l'est pas. Toute
l'architecture repose sur ce principe : ce qui a de la valeur vit dans Nova
Core. Le jour ou tu changes d'interface, tu ne dois rien perdre.

C'est aussi cette table que lira la consolidation nocturne en V0.3 pour produire
les resumes et extraire les faits nouveaux.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from nova.db import connection


def get_or_create(external_id: str | None, title: str | None = None) -> int:
    """Retourne l'identifiant interne de la conversation, en la creant au besoin.

    `external_id` est fourni par l'interface. S'il est absent (appel CLI, script),
    on cree une conversation anonyme.
    """
    with connection() as conn:
        if external_id:
            row = conn.execute(
                "SELECT id FROM conversations WHERE external_id = %s", (external_id,)
            ).fetchone()
            if row:
                return row["id"]
        row = conn.execute(
            "INSERT INTO conversations (external_id, title) VALUES (%s, %s) RETURNING id",
            (external_id, title),
        ).fetchone()
        return row["id"]


def log_message(
    conversation_id: int,
    role: str,
    content: str,
    *,
    model: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Enregistre un message et rafraichit la date d'activite de la conversation.

    `meta` transporte ce qui n'est pas du texte : sources citees, duree, mode
    utilise. En JSONB, donc extensible sans migration — c'est exactement le cas
    ou le schema souple est le bon choix.
    """
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, model, meta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, role, content, model, Jsonb(meta or {})),
        )
        conn.execute(
            "UPDATE conversations SET last_message_at = now() WHERE id = %s",
            (conversation_id,),
        )
