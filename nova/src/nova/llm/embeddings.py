"""Vectorisation des textes.

Un embedding transforme un texte en liste de nombres, de sorte que deux textes
de sens proche donnent deux vecteurs proches. C'est ce qui permet de chercher
"comment financer le projet" et de trouver un paragraphe qui parle de "budget"
sans que le mot apparaisse.

AVERTISSEMENT : changer de modele d'embeddings rend inutilisables TOUS les
vecteurs deja calcules. Il faut alors une nouvelle migration et une
re-vectorisation complete. Ce choix se fait une fois.
"""

from __future__ import annotations

import httpx

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)


class EmbeddingError(RuntimeError):
    pass


def embed(texts: list[str]) -> list[list[float]]:
    """Vectorise une liste de textes.

    On envoie un LOT plutot que des appels un par un : c'est plusieurs fois plus
    rapide, car le cout fixe par requete domine sur des textes courts.
    """
    if not texts:
        return []

    settings = get_settings()
    payload = {"model": settings.embedding_model, "input": texts}
    try:
        with httpx.Client(timeout=settings.request_timeout) as client:
            resp = client.post(f"{settings.ollama_url.rstrip('/')}/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()["data"]
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"Vectorisation impossible : {exc}") from exc

    # L'API ne garantit pas l'ordre : on trie sur l'index renvoye.
    vectors = [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]

    # Verification explicite : une dimension inattendue produirait sinon une
    # erreur SQL obscure au moment de l'insertion.
    if vectors and len(vectors[0]) != settings.embedding_dim:
        raise EmbeddingError(
            f"Le modele {settings.embedding_model} renvoie {len(vectors[0])} dimensions, "
            f"la base en attend {settings.embedding_dim}. "
            "Verifie NOVA_EMBEDDING_MODEL, ou cree une migration."
        )
    return vectors


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
