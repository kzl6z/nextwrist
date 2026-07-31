"""La passerelle : Nova se presente comme un modele compatible OpenAI.

C'est la decision d'architecture centrale de la V1 (docs/nova/11-architecture-v1.md).

L'interface croit parler a un modele nomme `nova`. En realite elle parle a ton
code, qui charge ta memoire, cherche dans tes documents, puis interroge Ollama.

Consequence : n'importe quelle interface compatible OpenAI fonctionne
instantanement, et l'intelligence reste chez toi, pas dans un produit tiers.

Astuce de conception : les MODES de travail sont exposes comme des MODELES
differents (`nova`, `nova-critique`). L'interface a deja un selecteur de modele
— on s'en sert comme selecteur de mode, sans ecrire la moindre ligne d'interface.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from nova import orchestrator
from nova.llm.client import LLMError
from nova.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["openai"])

# Nom du modele -> mode d'orchestration.
MODELS = {"nova": "normal", "nova-critique": "critique"}


class ChatMessage(BaseModel):
    role: str
    content: str = ""


class ChatRequest(BaseModel):
    model: str = "nova"
    messages: list[ChatMessage]
    stream: bool = False
    # Accepte et ignore les autres champs OpenAI : les interfaces en envoient
    # beaucoup, et refuser une requete pour un champ inconnu serait absurde.
    user: str | None = Field(default=None)

    model_config = {"extra": "allow"}


@router.get("/models")
def list_models() -> dict:
    """Liste des modeles exposes — c'est ce que l'interface affiche."""
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "created": now, "owned_by": "nova"}
            for name in MODELS
        ],
    }


def _sse(payload: dict) -> str:
    """Encode un fragment au format Server-Sent Events attendu par les clients."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream_response(request: ChatRequest, mode: str) -> Iterator[str]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    def envelope(delta: dict, finish: str | None = None) -> dict:
        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }

    yield _sse(envelope({"role": "assistant"}))
    try:
        for piece in orchestrator.answer_stream(
            [m.model_dump() for m in request.messages],
            conversation_external_id=request.user,
            mode=mode,
        ):
            yield _sse(envelope({"content": piece}))
    except LLMError as exc:
        # On renvoie l'erreur DANS le flux : l'utilisateur voit un message clair
        # dans la conversation plutot qu'une roue qui tourne indefiniment.
        log.error("Echec de generation : %s", exc)
        yield _sse(envelope({"content": f"\n\n_Nova n'a pas pu repondre : {exc}_"}))

    yield _sse(envelope({}, finish="stop"))
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
def chat_completions(request: ChatRequest):
    """Point d'entree unique des interfaces.

    Fonction `def` et non `async def` : FastAPI l'execute alors dans un pool de
    threads. Tout le code metier reste synchrone, donc beaucoup plus simple a
    lire et a deboguer — sans perte mesurable pour un usage personnel.
    """
    mode = MODELS.get(request.model, "normal")

    if request.stream:
        return StreamingResponse(
            _stream_response(request, mode),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    content = "".join(
        orchestrator.answer_stream(
            [m.model_dump() for m in request.messages],
            conversation_external_id=request.user,
            mode=mode,
        )
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
