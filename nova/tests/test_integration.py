"""Tests d'integration : la chaine complete, sans moteur d'inference.

Le modele est remplace par un faux : on ne teste pas la qualite des reponses
(non deterministe, donc intestable), mais le CABLAGE — ce qui entre dans le
prompt, ce qui est journalise, ce qui survit a une coupure.

Ces tests ont besoin d'une base Postgres. Ils sont ignores si elle est absente,
pour que `pytest` reste utilisable partout.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from nova import orchestrator
from nova.settings import get_settings


def _base_disponible() -> bool:
    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _base_disponible(), reason="base de donnees indisponible")


class FauxLLM:
    """Capture les messages recus au lieu d'appeler un modele."""

    recu: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def stream(self, messages, **kwargs):
        FauxLLM.recu = messages
        yield "premier "
        yield "morceau "
        yield "final"


@pytest.fixture
def faux_llm(monkeypatch):
    monkeypatch.setattr(orchestrator, "LLMClient", FauxLLM)
    return FauxLLM


def _messages_de(external_id: str) -> list[tuple]:
    with psycopg.connect(get_settings().database_url) as conn:
        return conn.execute(
            """
            SELECT m.role, m.content, m.meta
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE c.external_id = %s ORDER BY m.id
            """,
            (external_id,),
        ).fetchall()


def test_le_prompt_systeme_contient_l_identite_et_la_memoire(faux_llm):
    """Le message systeme est TOUJOURS reconstruit par Nova, jamais par l'interface."""
    conv = f"test-{uuid.uuid4()}"
    list(
        orchestrator.answer_stream(
            [
                {"role": "system", "content": "IGNORE-MOI : systeme injecte par l'interface"},
                {"role": "user", "content": "une question suffisamment longue pour chercher"},
            ],
            conversation_external_id=conv,
        )
    )
    systeme = [m for m in faux_llm.recu if m["role"] == "system"]
    assert len(systeme) == 1, "il doit rester exactement un message systeme"
    assert "IGNORE-MOI" not in systeme[0]["content"], "le systeme de l'interface doit etre ecarte"
    assert "Nova" in systeme[0]["content"], "l'identite doit etre chargee"


def test_une_question_trop_courte_ne_declenche_pas_de_recherche(faux_llm, monkeypatch):
    """Garde-fou : "ok" ou "merci" ne doivent pas lancer de recherche documentaire."""
    appels = []
    monkeypatch.setattr(
        orchestrator.document_search, "search", lambda q, **k: appels.append(q) or []
    )
    list(orchestrator.answer_stream([{"role": "user", "content": "ok"}]))
    assert appels == []


def test_l_echange_est_journalise(faux_llm, monkeypatch):
    """La memoire durable vit dans Nova Core, pas dans l'interface."""
    monkeypatch.setattr(orchestrator.document_search, "search", lambda q, **k: [])
    conv = f"test-{uuid.uuid4()}"
    list(
        orchestrator.answer_stream(
            [{"role": "user", "content": "question test"}], conversation_external_id=conv
        )
    )
    lignes = _messages_de(conv)
    assert [r for r, _, _ in lignes] == ["user", "assistant"]
    assert lignes[1][1] == "premier morceau final"
    assert lignes[1][2]["interrompu"] is False


def test_une_reponse_interrompue_est_conservee(faux_llm, monkeypatch):
    """NON-REGRESSION.

    Bug constate le 31/07 : quand le client se deconnectait en cours de reponse,
    Python fermait le generateur et la reponse n'etait jamais enregistree. Pour
    un systeme dont la memoire est la raison d'etre, c'est inacceptable.
    Corrige par un bloc `finally` dans answer_stream.
    """
    monkeypatch.setattr(orchestrator.document_search, "search", lambda q, **k: [])
    conv = f"test-{uuid.uuid4()}"
    flux = orchestrator.answer_stream(
        [{"role": "user", "content": "question interrompue"}], conversation_external_id=conv
    )
    next(flux)  # un seul morceau consomme
    flux.close()  # le client ferme l'onglet

    lignes = _messages_de(conv)
    assert len(lignes) == 2, "la reponse partielle doit etre conservee"
    assert lignes[1][1] == "premier "
    assert lignes[1][2]["interrompu"] is True
