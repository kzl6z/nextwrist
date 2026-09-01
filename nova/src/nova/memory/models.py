"""Types de donnees partages.

Des dataclasses simples plutot que des dictionnaires : l'editeur autocomplete,
les fautes de frappe sont detectees, et le code se lit sans avoir a deviner ce
que contient la structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True)
class Fact:
    """Un fait stable te concernant. Voir migrations/001 et 003."""

    id: int
    category: str
    content: str
    status: str  # proposed | confirmed | archived
    origin: str  # user | inferred
    confidence: float
    source: str | None
    created_at: datetime
    #: basse | moyenne | haute | critique. Decide ce qui tombe du prompt
    #: quand le budget est atteint — sans lui, la troncature se fait par date.
    importance: str = "moyenne"
    #: NULL = durable. Une date = temporaire : « je suis a Paris jusqu'a
    #: vendredi » ne doit pas etre vrai en mars prochain.
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    updated_at: datetime | None = None
    #: La categorie dit « quel genre de fait », les etiquettes « de quoi ca
    #: parle ». Un fait peut concerner deux sujets, une categorie ne le peut
    #: pas.
    tags: tuple[str, ...] = ()
    #: L'identifiant du fait que celui-ci remplace, s'il y en a un.
    supersedes: int | None = None

    def perime(self, maintenant: datetime | None = None) -> bool:
        """Ce fait a-t-il passe sa date ?

        ⚠️ PERIME N'EST PAS SUPPRIME.

        On cesse de s'en servir, on ne l'efface pas : c'est ce qui distingue
        l'oubli de l'effacement, et c'est deja la regle de `archive`.
        """
        if self.expires_at is None:
            return False
        return self.expires_at <= (maintenant or datetime.now(UTC))


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
