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

OPEN, CLOSE = "<think>", "</think>"


class ThinkFilter:
    """Retire les blocs <think>...</think> d'un flux de texte.

    Pourquoi c'est necessaire : certains modeles "raisonneurs" ecrivent leur
    reflexion directement dans la reponse. Constate en conditions reelles avec
    qwen3:4b — 2600 caracteres de raisonnement pour repondre "Bonjour !".

    Ce filtre ne rend pas le modele plus rapide : le temps est deja depense.
    Il evite simplement d'infliger le monologue a l'utilisateur. Le vrai
    remede est de choisir un modele sans phase de reflexion (scripts/bench_models.py).

    La difficulte : en flux, une balise peut etre coupee entre deux fragments.
    On conserve donc une petite queue tampon plutot que de tester chaque fragment.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, piece: str) -> str:
        self._buffer += piece
        out: list[str] = []
        while True:
            if not self._inside:
                index = self._buffer.find(OPEN)
                if index == -1:
                    # On garde de quoi reconstituer une balise coupee en deux.
                    keep = max(0, len(self._buffer) - len(OPEN) + 1)
                    out.append(self._buffer[:keep])
                    self._buffer = self._buffer[keep:]
                    break
                out.append(self._buffer[:index])
                self._buffer = self._buffer[index + len(OPEN) :]
                self._inside = True
            else:
                index = self._buffer.find(CLOSE)
                if index == -1:
                    keep = max(0, len(self._buffer) - len(CLOSE) + 1)
                    self._buffer = self._buffer[keep:]  # le raisonnement est jete
                    break
                self._buffer = self._buffer[index + len(CLOSE) :]
                self._inside = False
        return "".join(out)

    def flush(self) -> str:
        """Ce qui reste en tampon a la fin du flux."""
        return "" if self._inside else self._buffer


class LLMError(RuntimeError):
    """Erreur remontee par le moteur d'inference, presentable a l'utilisateur."""


class LLMClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.chat_model
        self.timeout = settings.request_timeout
        self.default_temperature = settings.temperature
        self.max_tokens = settings.max_tokens

    # -- appel simple -------------------------------------------------------
    def chat(self, messages: list[Message], *, temperature: float | None = None) -> str:
        """Reponse complete, en un bloc. Pour la CLI et les traitements de fond."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.default_temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
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
            "max_tokens": self.max_tokens,
            # keep_alive : champ propre a Ollama, ignore par les autres moteurs.
            # Garde le modele en memoire entre deux questions — sans lui, chaque
            # appel recharge 2,5 Go depuis le disque.
            "keep_alive": "30m",
            "stream": True,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload
                ) as resp:
                    resp.raise_for_status()
                    filtre = ThinkFilter()
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
                            if visible := filtre.feed(content):
                                yield visible
                    if reste := filtre.flush():
                        yield reste
        except httpx.HTTPError as exc:
            raise LLMError(f"Le moteur d'inference n'a pas repondu : {exc}") from exc

    def health(self) -> bool:
        """Le moteur repond-il ? Utilise par /health."""
        try:
            with httpx.Client(timeout=5.0) as client:
                return client.get(f"{self.base_url}/models").status_code == 200
        except httpx.HTTPError:
            return False
