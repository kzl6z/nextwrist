"""Vectorisation des textes.

Un embedding transforme un texte en liste de nombres, de sorte que deux textes
de sens proche donnent deux vecteurs proches. C'est ce qui permet de chercher
"comment financer le projet" et de trouver un paragraphe qui parle de "budget"
sans que le mot apparaisse.

AVERTISSEMENT : changer de modele d'embeddings rend inutilisables TOUS les
vecteurs deja calcules. Il faut alors une nouvelle migration et une
re-vectorisation complete. Ce choix se fait une fois.

⚠️ NOVA UTILISE DEUX MODELES, ET OLLAMA DOIT POUVOIR LES GARDER TOUS LES DEUX

Ce module appelle Ollama avec bge-m3 ; l'orchestrateur l'appelle avec le
modele de conversation. Ce sont DEUX modeles, charges dans le meme serveur.

    OLLAMA_MAX_LOADED_MODELS=1

decharge donc le modele de conversation a chaque vectorisation, et le
rechargement est paye au coup d'apres. Releve en conditions reelles sur
l'iMac M1 :

    Modele llama3.2:3b charge en 4.0 s
    prompt 3376 car. -> premier mot 5,1 s
    prompt 1812 car. -> premier mot 5,2 s     <- moitie moins de prompt,
                                                 meme temps

Le cout ne dependait pas de la taille du prompt parce que ce n'etait pas de
la lecture : c'etait un rechargement complet, a chaque question. Un defaut
de ce genre ne se voit dans aucun profil applicatif — il se passe dans un
autre processus.

Le reglage correct est 2 (ou plus). Sur 8 Go, les deux tiennent :
llama3.2:3b 2,0 Go + bge-m3 1,2 Go = 3,2 Go, pour un budget de 3,6 Go.

    launchctl setenv OLLAMA_MAX_LOADED_MODELS 2
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
