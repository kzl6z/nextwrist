"""Decoupage d'un document en morceaux.

C'est le maillon le plus sous-estime du RAG. Un mauvais decoupage produit une
Nova qui "ne trouve pas", sans jamais lever d'erreur :
  - morceaux trop gros  -> le passage utile est noye, le score baisse ;
  - morceaux trop petits -> le contexte est perdu, l'extrait devient inutilisable.

Deux principes appliques ici :
  1. On coupe d'abord sur la STRUCTURE (titres, paragraphes), jamais au milieu
     d'une phrase. Un morceau doit rester lisible seul.
  2. On garde le titre de section avec chaque morceau : c'est ce qui permet
     de citer precisement, et une reponse citable est une reponse verifiable.

Ce module ne contient que des fonctions pures — aucune base, aucun reseau.
C'est donc le premier endroit ou ecrire des tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
PARAGRAPH_RE = re.compile(r"\n\s*\n")


@dataclass(slots=True)
class Chunk:
    ordinal: int
    heading: str | None
    content: str


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Decoupe un Markdown en (titre, contenu) selon ses titres.

    Le texte precedant le premier titre est conserve avec un titre `None` :
    on ne perd jamais de contenu, meme mal structure.
    """
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [(None, text.strip())] if text.strip() else []

    sections: list[tuple[str | None, str]] = []
    if preamble := text[: matches[0].start()].strip():
        sections.append((None, preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if body:
            sections.append((match.group(2).strip(), body))
    return sections


def _split_by_size(text: str, size: int) -> list[str]:
    """Regroupe les paragraphes en blocs d'au plus `size` caracteres."""
    paragraphs = [p.strip() for p in PARAGRAPH_RE.split(text) if p.strip()]
    blocks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        # Paragraphe plus long que la taille cible : on coupe en dur.
        # Rare (tableau, bloc de code), mais il faut le prevoir.
        if len(paragraph) > size:
            if current:
                blocks.append(current)
                current = ""
            blocks.extend(paragraph[i : i + size] for i in range(0, len(paragraph), size))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > size:
            blocks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        blocks.append(current)
    return blocks


def _add_overlap(blocks: list[str], overlap: int) -> list[str]:
    """Fait deborder chaque morceau sur la fin du precedent.

    Pourquoi : une information a cheval sur deux morceaux serait sinon perdue
    par les deux. Le recouvrement garantit qu'elle reste entiere quelque part.
    """
    if overlap <= 0 or len(blocks) < 2:
        return blocks

    out = [blocks[0]]
    for previous, current in zip(blocks, blocks[1:], strict=False):
        tail = previous[-overlap:]
        # On repart du debut d'un mot, pas du milieu.
        if (cut := tail.find(" ")) != -1:
            tail = tail[cut + 1 :]
        out.append(f"{tail} {current}".strip() if tail else current)
    return out


def chunk_text(text: str, *, size: int = 1000, overlap: int = 150) -> list[Chunk]:
    """Decoupe complet : structure, puis taille, puis recouvrement."""
    if overlap >= size:
        raise ValueError("Le recouvrement doit etre inferieur a la taille du morceau")

    chunks: list[Chunk] = []
    for heading, body in split_sections(text):
        for block in _add_overlap(_split_by_size(body, size), overlap):
            chunks.append(Chunk(ordinal=len(chunks), heading=heading, content=block))
    return chunks
