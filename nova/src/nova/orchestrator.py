"""Le coeur de Nova : assembler le contexte, puis interroger le modele.

C'est le seul module autorise a connaitre tous les autres. Tout le reste
respecte la regle de dependance :

    api -> orchestrator -> memory / documents / llm -> db

Ce que fait l'orchestrateur, dans l'ordre :
  1. charge l'identite de Nova (config/prompts/identity.md)
  2. y ajoute les faits confirmes te concernant     <- la memoire
  3. cherche des extraits pertinents                <- les documents
  4. assemble le message systeme
  5. appelle le modele en flux
  6. journalise l'echange

Choix de conception V1 : c'est NOTRE code qui decide de chercher, pas le modele.
C'est deterministe, debogable et previsible. L'appel d'outils par le modele
(MCP) s'ajoutera en V0.3 par-dessus cette base, sans la remplacer.
"""

from __future__ import annotations

from collections.abc import Iterator

from nova import prompts
from nova.documents import search as document_search
from nova.llm.client import LLMClient, Message
from nova.logging_setup import get_logger
from nova.memory import conversations, facts
from nova.memory.models import SearchHit
from nova.settings import get_settings

log = get_logger(__name__)

# En dessous, la question ne porte pas assez d'information pour qu'une recherche
# documentaire soit utile ("ok", "merci", "et ensuite ?").
MIN_QUERY_LENGTH = 12


def _format_sources(hits: list[SearchHit]) -> str:
    """Met les extraits en forme pour le prompt.

    Chaque extrait est explicitement etiquete par sa source afin que le modele
    puisse citer. Sans cette etiquette, il invente les references — c'est
    systematique.
    """
    blocks = []
    for hit in hits:
        label = hit.heading or "sans titre"
        blocks.append(f'--- [{hit.document_title}, "{label}"]\n{hit.content}')
    return "\n\n".join(blocks)


def build_system_prompt(user_message: str, *, mode: str = "normal") -> tuple[str, list[SearchHit]]:
    """Construit le message systeme complet. Retourne aussi les sources utilisees.

    Renvoyer les sources permet de les journaliser et, plus tard, de les
    afficher dans l'interface : une reponse verifiable est une reponse a
    laquelle on peut faire confiance.
    """
    parts = [prompts.load("identity")]

    if mode == "critique":
        parts.append(prompts.load("mode_critique"))

    if memory_block := facts.render_for_prompt():
        parts.append(memory_block)

    hits: list[SearchHit] = []
    if len(user_message.strip()) >= MIN_QUERY_LENGTH:
        try:
            hits = document_search.search(user_message)
        except Exception as exc:  # noqa: BLE001
            # Une recherche en echec ne doit JAMAIS empecher Nova de repondre.
            # Chaque capacite est facultative : c'est ce qui rend le systeme
            # robuste quand on en ajoutera dix autres.
            log.warning("Recherche documentaire indisponible : %s", exc)

    if hits:
        parts.append(
            "## Extraits de tes documents\n\n"
            "Appuie-toi dessus en priorite et cite la source entre crochets. "
            "S'ils ne repondent pas a la question, dis-le explicitement.\n\n"
            + _format_sources(hits)
        )

    return "\n\n".join(parts), hits


def answer_stream(
    messages: list[Message],
    *,
    conversation_external_id: str | None = None,
    mode: str = "normal",
) -> Iterator[str]:
    """Produit la reponse morceau par morceau, et journalise l'echange.

    `messages` est l'historique fourni par l'interface (format OpenAI). On
    remplace tout message systeme qu'elle aurait ajoute par le notre : l'identite
    de Nova ne doit pas dependre de l'interface.
    """
    user_messages = [m for m in messages if m.get("role") == "user"]
    last_user = user_messages[-1]["content"] if user_messages else ""

    system_prompt, hits = build_system_prompt(last_user, mode=mode)
    history = [m for m in messages if m.get("role") != "system"]
    full: list[Message] = [{"role": "system", "content": system_prompt}, *history]

    conversation_id = conversations.get_or_create(conversation_external_id)
    conversations.log_message(conversation_id, "user", last_user)

    client = LLMClient()
    collected: list[str] = []
    for piece in client.stream(full):
        collected.append(piece)
        yield piece

    conversations.log_message(
        conversation_id,
        "assistant",
        "".join(collected),
        model=get_settings().chat_model,
        meta={"sources": [h.document_path for h in hits], "mode": mode},
    )


def answer(question: str, *, mode: str = "normal") -> str:
    """Reponse complete en un bloc. Pour la CLI et les traitements de fond."""
    return "".join(answer_stream([{"role": "user", "content": question}], mode=mode))
