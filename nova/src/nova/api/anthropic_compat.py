"""Nova parle aussi le protocole Anthropic (/v1/messages).

POURQUOI CE FICHIER EXISTE

L'architecture repose sur un principe : Nova Core se presente comme un modele,
et l'interface est jetable. Jusqu'ici Nova portait un seul masque, celui de
l'API OpenAI. Ce module en ajoute un second.

Le cas d'usage est reel : une application existante — avec son design, sa voix,
son mot de reveil — appelle deja l'API Anthropic. Deux facons de la brancher
sur Nova :

  a) modifier son code pour parler le protocole OpenAI ;
  b) apprendre a Nova a parler le protocole Anthropic.

(b) gagne : une URL a changer, aucun code touche, et l'application peut revenir
en arriere a tout moment. C'est exactement ce que promettait l'architecture —
on remplace le cerveau sans toucher au visage.

DEUX TYPES DE CLIENTS, DEUX COMPORTEMENTS

  - Client conversationnel (aucun champ `system`) : Nova construit tout. Son
    identite ne se delegue pas a une interface.

  - Client structure (champ `system` fourni) : la consigne du client est un
    CONTRAT — elle definit le format attendu, souvent du JSON strict. L'ecraser
    casserait l'application sans un mot : elle recevrait de la prose la ou elle
    attend un objet, echouerait a l'analyser, et se replierait en silence sur
    son mode degrade. On respecte donc le contrat, et on y INJECTE la memoire.

C'est la nuance qu'un vrai branchement a revelee, et elle merite d'etre retenue :
« ignorer le prompt du client » est la bonne regle pour une interface de chat,
et la mauvaise pour un client qui attend une structure.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nova import orchestrator
from nova.llm.client import LLMError
from nova.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["anthropic"])


class AnthropicMessage(BaseModel):
    role: str
    # Anthropic accepte une chaine OU une liste de blocs typés.
    content: Any


class MessagesRequest(BaseModel):
    model: str = "nova"
    messages: list[AnthropicMessage]
    max_tokens: int = 1024
    stream: bool = False
    system: Any = None  # accepte et ignore : Nova reconstruit toujours le sien
    metadata: dict | None = None

    model_config = {"extra": "allow"}


def _texte(content: Any) -> str:
    """Ramene un contenu Anthropic a du texte simple.

    Le format autorise une chaine, ou une liste de blocs ({"type": "text", ...},
    images, appels d'outils...). En V1 on ne traite que le texte : on ignore
    silencieusement le reste plutot que d'echouer, pour qu'une interface un peu
    bavarde ne casse pas la conversation.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            bloc.get("text", "")
            for bloc in content
            if isinstance(bloc, dict) and bloc.get("type") == "text"
        )
    return str(content or "")


def _mode(nom_modele: str) -> str:
    return "critique" if "critique" in nom_modele else "normal"


def _contrat(system: Any) -> str | None:
    """Consigne imposee par le client, si elle existe."""
    texte = _texte(system).strip()
    return texte or None


def _exige_du_json(contrat: str | None) -> bool:
    """Le contrat demande-t-il une sortie JSON ?

    Heuristique volontairement simple et lisible. Quand elle se declenche, on
    active le decodage contraint du moteur : la sortie ne PEUT plus etre du JSON
    invalide. C'est indispensable avec un petit modele local, qui produit
    regulierement des accolades manquantes ou du texte autour de l'objet.
    """
    return bool(contrat) and "json" in contrat.lower()


def _flux(request: MessagesRequest) -> Iterator[str]:
    """Serie d'evenements SSE au format Anthropic.

    La sequence est imposee par le protocole : message_start, puis un bloc de
    contenu ouvert, les deltas, la fermeture, et message_stop. Un client
    conforme s'attend a chaque etape — en sauter une le fait echouer.
    """
    message_id = f"msg_{uuid.uuid4().hex[:24]}"

    def evenement(nom: str, payload: dict) -> str:
        return f"event: {nom}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield evenement(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": request.model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )
    yield evenement(
        "content_block_start",
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    )

    contrat = _contrat(request.system)
    mots = 0
    try:
        for morceau in orchestrator.answer_stream(
            [{"role": m.role, "content": _texte(m.content)} for m in request.messages],
            conversation_external_id=(request.metadata or {}).get("user_id"),
            mode=_mode(request.model),
            contrat=contrat,
            json_mode=_exige_du_json(contrat),
            max_tokens=request.max_tokens,
        ):
            mots += 1
            yield evenement(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": morceau},
                },
            )
    except LLMError as exc:
        log.error("Echec de generation : %s", exc)
        yield evenement(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": f"\n\nNova n'a pas pu repondre : {exc}"},
            },
        )

    yield evenement("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield evenement(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": mots},
        },
    )
    yield evenement("message_stop", {"type": "message_stop"})


@router.post("/messages")
def messages(request: MessagesRequest):
    """Point d'entree compatible avec l'API Anthropic Messages."""
    if request.stream:
        return StreamingResponse(
            _flux(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    contrat = _contrat(request.system)
    texte = "".join(
        orchestrator.answer_stream(
            [{"role": m.role, "content": _texte(m.content)} for m in request.messages],
            conversation_external_id=(request.metadata or {}).get("user_id"),
            mode=_mode(request.model),
            contrat=contrat,
            json_mode=_exige_du_json(contrat),
            max_tokens=request.max_tokens,
        )
    )
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": request.model,
        "content": [{"type": "text", "text": texte}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": len(texte.split())},
        "created": int(time.time()),
    }
