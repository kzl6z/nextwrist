"""Client vers le moteur d'inference.

Ce module est le SEUL de tout Nova qui sait qu'Ollama existe. Le reste du code
ne connait que `LLMClient`. Le jour ou tu passes a vLLM ou llama.cpp, tu ne
modifies que ce fichier — c'est la premiere des deux frontieres stables decrites
dans docs/nova/01-architecture.md.

On parle a Ollama via son API compatible OpenAI (/v1) et non son API native :
c'est le standard de fait, donc ce qui garantit l'interchangeabilite.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)

Message = dict[str, str]  # {"role": "user", "content": "..."}


class LLMError(RuntimeError):
    """Erreur remontee par le moteur d'inference, presentable a l'utilisateur."""


class LLMClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.chat_model
        self.timeout = settings.request_timeout
        self.default_temperature = settings.temperature

    # -- appel simple -------------------------------------------------------
    def chat(self, messages: list[Message], *, temperature: float | None = None) -> str:
        """Reponse complete, en un bloc. Pour la CLI et les traitements de fond."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.default_temperature if temperature is None else temperature,
            "stream": False,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise LLMError(f"Le moteur d'inference n'a pas repondu : {exc}") from exc

    # -- appel en flux ------------------------------------------------------
    def stream(self, messages: list[Message], *, temperature: float | None = None) -> Iterator[str]:
        """Reponse morceau par morceau, pour l'interface.

        Le flux n'est pas cosmetique : sur un modele local, la premiere phrase
        arrive en ~1 s alors que la reponse complete peut prendre 30 s. C'est la
        difference entre "ca repond" et "c'est fige".

        Format SSE renvoye par l'API : des lignes `data: {json}`, terminees par
        `data: [DONE]`.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.default_temperature if temperature is None else temperature,
            "stream": True,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            delta = json.loads(data)["choices"][0]["delta"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue  # fragment malforme : on ignore, on ne casse pas
                        if content := delta.get("content"):
                            yield content
        except httpx.HTTPError as exc:
            raise LLMError(f"Le moteur d'inference n'a pas repondu : {exc}") from exc

    def health(self) -> bool:
        """Le moteur repond-il ? Utilise par /health."""
        try:
            with httpx.Client(timeout=5.0) as client:
                return client.get(f"{self.base_url}/models").status_code == 200
        except httpx.HTTPError:
            return False
