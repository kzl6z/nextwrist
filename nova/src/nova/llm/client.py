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


class FinDeJson:
    """Detecte la fermeture du premier objet JSON de premier niveau.

    POURQUOI CETTE CLASSE EXISTE

    Le decodage contraint garantit que la sortie EST du JSON valide. Il ne
    garantit pas que le moteur s'arrete une fois l'objet ecrit : Ollama
    continue d'emettre du remplissage jusqu'au plafond de jetons. Mesure sur
    la machine reelle, pour une reponse dont le texte utile faisait six
    caracteres (« samedi ») :

        max_tokens 300  ->  24 431 ms

    Presque tout ce temps partait apres l'accolade fermante. On coupe donc le
    flux nous-memes : fermer la connexion interrompt la generation cote
    moteur, et la reponse arrive des qu'elle est complete plutot qu'a
    l'epuisement du quota.

    L'analyse suit les regles du JSON — une accolade dans une chaine de
    caracteres ne compte pas, et un guillemet echappe ne ferme pas la chaine.
    """

    def __init__(self) -> None:
        self.profondeur = 0
        self.dans_chaine = False
        self.echappe = False
        self.commence = False
        self.termine = False

    def feed(self, morceau: str) -> str:
        """Renvoie la portion a conserver ; positionne `termine` a la fermeture."""
        if self.termine:
            return ""
        for i, caractere in enumerate(morceau):
            if self.dans_chaine:
                if self.echappe:
                    self.echappe = False
                elif caractere == "\\":
                    self.echappe = True
                elif caractere == '"':
                    self.dans_chaine = False
                continue
            if caractere == '"':
                self.dans_chaine = True
            elif caractere in "{[":
                self.profondeur += 1
                self.commence = True
            elif caractere in "}]":
                self.profondeur -= 1
                if self.commence and self.profondeur <= 0:
                    self.termine = True
                    return morceau[: i + 1]
        return morceau


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


def _explique(exc: httpx.HTTPError, modele: str) -> str:
    """Traduit une erreur HTTP en message actionnable.

    Un message d'erreur doit dire QUOI FAIRE, pas seulement ce qui a echoue.
    `Client error '404 Not Found'` est exact et inutile : il n'indique ni la
    cause (le modele n'est pas installe) ni le remede (`ollama pull`).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 404:
            return (
                f"le modele « {modele} » n'existe pas dans Ollama.\n"
                f"Installe-le :  ollama pull {modele}\n"
                f"Ou change NOVA_CHAT_MODEL dans .env — modeles disponibles : ollama list"
            )
        return f"le moteur a repondu {exc.response.status_code}."
    if isinstance(exc, httpx.ConnectError):
        return (
            "impossible de joindre Ollama.\n"
            "Verifie que l'application est lancee (icone dans la barre de menus)."
        )
    if isinstance(exc, httpx.ReadTimeout):
        return "le moteur n'a pas repondu a temps (modele trop lourd pour la machine ?)."
    return str(exc)


class LLMClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.chat_model
        self.timeout = settings.request_timeout
        self.default_temperature = settings.temperature
        self.max_tokens = settings.max_tokens

    # -- appel simple -------------------------------------------------------
    def _payload(
        self,
        messages: list[Message],
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.default_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "keep_alive": "30m",
        }
        if json_mode:
            # Sortie JSON garantie par le moteur : il contraint le decodage token
            # par token, ce qui rend une sortie invalide IMPOSSIBLE plutot
            # qu'improbable. Sans cela, un petit modele produit regulierement du
            # JSON casse — et une application qui fait JSON.parse() se replie
            # silencieusement sur autre chose, sans que personne ne le voie.
            payload["response_format"] = {"type": "json_object"}
            payload["format"] = "json"  # champ natif Ollama, ignore ailleurs
        return payload

    def chat(self, messages: list[Message], *, temperature: float | None = None) -> str:
        """Reponse complete, en un bloc. Pour la CLI et les traitements de fond."""
        payload = self._payload(messages, temperature, None, False) | {"stream": False}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise LLMError(_explique(exc, self.model)) from exc

    # -- appel en flux ------------------------------------------------------
    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        """Reponse morceau par morceau, pour l'interface.

        Le flux n'est pas cosmetique : sur un modele local, la premiere phrase
        arrive en ~1 s alors que la reponse complete peut prendre 30 s. C'est la
        difference entre "ca repond" et "c'est fige".

        Format SSE renvoye par l'API : des lignes `data: {json}`, terminees par
        `data: [DONE]`.
        """
        # keep_alive garde le modele en memoire entre deux questions ; sans lui,
        # chaque appel rechargerait plusieurs Go depuis le disque.
        payload = self._payload(messages, temperature, max_tokens, json_mode) | {"stream": True}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload
                ) as resp:
                    resp.raise_for_status()
                    filtre = ThinkFilter()
                    # En mode contraint, on coupe des que l'objet est ferme :
                    # tout ce qui suit est du remplissage jusqu'au plafond.
                    fin = FinDeJson() if json_mode else None
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
                            visible = filtre.feed(content)
                            if fin is not None:
                                visible = fin.feed(visible)
                                if visible:
                                    yield visible
                                if fin.termine:
                                    log.info("Objet JSON complet : flux interrompu.")
                                    return
                            elif visible:
                                yield visible
                    if reste := filtre.flush():
                        yield reste
        except httpx.HTTPError as exc:
            raise LLMError(_explique(exc, self.model)) from exc

    def health(self) -> bool:
        """Le moteur repond-il ? Utilise par /health."""
        try:
            with httpx.Client(timeout=5.0) as client:
                return client.get(f"{self.base_url}/models").status_code == 200
        except httpx.HTTPError:
            return False
