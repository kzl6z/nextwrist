"""Types de donnees partages.

Des dataclasses simples plutot que des dictionnaires : l'editeur autocomplete,
les fautes de frappe sont detectees, et le code se lit sans avoir a deviner ce
que contient la structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Fact:
    """Un fait stable te concernant. Voir migrations/001_socle.sql."""

    id: int
    category: str
    content: str
    status: str  # proposed | confirmed | archived
    origin: str  # user | inferred
    confidence: float
    source: str | None
    created_at: datetime


@dataclass(slots=True)
class SearchHit:
    """Un extrait de document retenu par la recherche."""

    chunk_id: int
    document_title: str
    document_path: str
    heading: str | None
    content: str
    score: float

    def citation(self) -> str:
        """Reference courte, affichable telle quelle dans une reponse."""
        if self.heading:
            return f'[{self.document_title}, "{self.heading}"]'
        return f"[{self.document_title}]"
