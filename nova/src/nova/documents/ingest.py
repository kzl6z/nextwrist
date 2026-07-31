"""Ingestion : fichier -> morceaux -> vecteurs -> base.

V1 : Markdown et texte brut uniquement. Les PDF complexes arrivent en V0.2 avec
Docling. Raison : un PDF mal extrait produit du bruit qui degrade TOUTES les
recherches, y compris sur les documents propres. Mieux vaut peu et fiable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from nova.db import connection
from nova.documents.chunking import chunk_text
from nova.llm.embeddings import embed
from nova.logging_setup import get_logger
from nova.settings import get_tuning

log = get_logger(__name__)

SUPPORTED = {".md", ".markdown", ".txt"}
EMBED_BATCH = 32  # compromis entre nombre d'appels et taille des requetes


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_file(path: Path) -> tuple[int, int]:
    """Ingere un fichier. Retourne (nombre de morceaux, 1 si traite sinon 0).

    Si le contenu n'a pas change depuis la derniere fois, on ne fait rien :
    la vectorisation est de loin l'operation la plus couteuse de la chaine.
    """
    path = path.resolve()
    if path.suffix.lower() not in SUPPORTED:
        log.debug("Ignore (format non gere) : %s", path.name)
        return (0, 0)

    content = path.read_text(encoding="utf-8", errors="replace")
    digest = _hash(content)

    with connection() as conn:
        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE source_path = %s", (str(path),)
        ).fetchone()

        if existing and existing["content_hash"] == digest:
            log.info("Inchange : %s", path.name)
            return (0, 0)

        if existing:
            # Le document a change : on repart de zero pour ce document.
            # ON DELETE CASCADE supprime les morceaux associes.
            conn.execute("DELETE FROM documents WHERE id = %s", (existing["id"],))

        document = conn.execute(
            "INSERT INTO documents (source_path, title, content_hash) VALUES (%s, %s, %s) "
            "RETURNING id",
            (str(path), path.stem, digest),
        ).fetchone()
        document_id = document["id"]

    tuning = get_tuning()
    chunks = chunk_text(content, size=tuning.chunk_size, overlap=tuning.chunk_overlap)
    if not chunks:
        return (0, 1)

    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        vectors = embed([c.content for c in batch])
        with connection() as conn:
            for chunk, vector in zip(batch, vectors, strict=True):
                conn.execute(
                    """
                    INSERT INTO chunks (document_id, ordinal, heading, content, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    # Le vecteur est passe en litteral texte puis converti par
                    # Postgres : c'est la forme qui marche quel que soit
                    # l'adaptateur installe cote Python.
                    (document_id, chunk.ordinal, chunk.heading, chunk.content, str(vector)),
                )

    log.info("Ingere : %s (%d morceaux)", path.name, len(chunks))
    return (len(chunks), 1)


def ingest_path(target: Path) -> tuple[int, int]:
    """Ingere un fichier ou un dossier entier (recursivement)."""
    target = Path(target)
    if target.is_file():
        return ingest_file(target)

    total_chunks = total_files = 0
    for path in sorted(target.rglob("*")):
        if path.is_file():
            chunks, files = ingest_file(path)
            total_chunks += chunks
            total_files += files
    return (total_chunks, total_files)
