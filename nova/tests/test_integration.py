"""Tests d'integration : la chaine complete, sans moteur d'inference.

Le modele est remplace par un faux : on ne teste pas la qualite des reponses
(non deterministe, donc intestable), mais le CABLAGE — ce qui entre dans le
prompt, ce qui est journalise, ce qui survit a une coupure.

Deux precautions apprises en conditions reelles :

  1. On verifie que le SCHEMA existe, pas seulement la connexion. Sinon, lancer
     les tests avant `nova db migrate` produit quatre echecs incomprehensibles
     (`relation "facts" does not exist`) au lieu d'un saut propre.

  2. Chaque test nettoie ce qu'il a cree. Ces tests ecrivent dans TA vraie base :
     sans nettoyage, ta memoire se remplirait de conversations de test.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from nova import orchestrator
from nova.settings import get_settings


def _schema_pret() -> bool:
    """Base joignable ET migrations appliquees."""
    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return conn.execute("SELECT to_regclass('public.facts')").fetchone()[0] is not None
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _schema_pret(),
    reason="base absente ou migrations non appliquees — lance `uv run nova db migrate`",
)


class FauxLLM:
    """Capture les messages recus au lieu d'appeler un modele.

    ⚠️ ON INTERCEPTE LE ROUTAGE, PLUS LE CLIENT.

    Ces bancs protegent le CABLAGE — quel prompt part, ce qui est journalise —
    et leur sujet n'a pas change. Ce qui a change, c'est la couture :
    l'orchestrateur ne construit plus un `LLMClient` lui-meme, il demande un
    USAGE au Model Router, qui choisit le fournisseur.

    ⚠️ ET CES QUATRE BANCS SONT LE SEUL ENDROIT DU DEPOT QUI N'ETAIT PAS
       EXERCE ICI.

    Ils exigent Postgres. Sans base, ils sont IGNORES — et « 1363 bancs
    verts » a ete annonce sans les compter. Sur la machine de Hugo la base
    tourne, ils s'executent, et les quatre sont tombes sur un attribut
    disparu.

    C'est le meme angle mort que les bancs de fichiers, qui passaient ici et
    tombaient la-bas. Ce qui n'est pas exerce se casse sans que personne ne le
    voie. Postgres est desormais installe sur la machine de developpement.
    """

    recu: list[dict] = []

    @staticmethod
    def flux(usage, messages, **kwargs):
        FauxLLM.recu = messages
        FauxLLM.usage = usage
        yield "premier "
        yield "morceau "
        yield "final"


@pytest.fixture
def faux_llm(monkeypatch):
    monkeypatch.setattr(orchestrator.routage, "flux", FauxLLM.flux)
    return FauxLLM


@pytest.fixture
def sans_recherche(monkeypatch):
    """Neutralise la recherche documentaire : on teste le cablage, pas le RAG."""
    monkeypatch.setattr(orchestrator.document_search, "search", lambda q, **k: [])


@pytest.fixture
def conversation():
    """Identifiant unique, supprime a la fin du test."""
    external_id = f"pytest-{uuid.uuid4()}"
    yield external_id
    with psycopg.connect(get_settings().database_url) as conn:
        conn.execute("DELETE FROM conversations WHERE external_id = %s", (external_id,))


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


def test_le_prompt_systeme_contient_l_identite_et_la_memoire(faux_llm, conversation):
    """Le message systeme est TOUJOURS reconstruit par Nova, jamais par l'interface."""
    list(
        orchestrator.answer_stream(
            [
                {"role": "system", "content": "IGNORE-MOI : systeme injecte par l'interface"},
                {"role": "user", "content": "une question suffisamment longue pour chercher"},
            ],
            conversation_external_id=conversation,
        )
    )
    systeme = [m for m in faux_llm.recu if m["role"] == "system"]
    assert len(systeme) == 1, "il doit rester exactement un message systeme"
    assert "IGNORE-MOI" not in systeme[0]["content"], "le systeme de l'interface doit etre ecarte"
    assert "Nova" in systeme[0]["content"], "l'identite doit etre chargee"


def test_une_question_trop_courte_ne_declenche_pas_de_recherche(
    faux_llm, monkeypatch, conversation
):
    """Garde-fou : "ok" ou "merci" ne doivent pas lancer de recherche documentaire."""
    appels: list[str] = []
    monkeypatch.setattr(
        orchestrator.document_search, "search", lambda q, **k: appels.append(q) or []
    )
    list(
        orchestrator.answer_stream(
            [{"role": "user", "content": "ok"}], conversation_external_id=conversation
        )
    )
    assert appels == []


def test_l_echange_est_journalise(faux_llm, sans_recherche, conversation):
    """La memoire durable vit dans Nova Core, pas dans l'interface."""
    list(
        orchestrator.answer_stream(
            [{"role": "user", "content": "question test"}],
            conversation_external_id=conversation,
        )
    )
    lignes = _messages_de(conversation)
    assert [r for r, _, _ in lignes] == ["user", "assistant"]
    assert lignes[1][1] == "premier morceau final"
    assert lignes[1][2]["interrompu"] is False


def test_une_reponse_interrompue_est_conservee(faux_llm, sans_recherche, conversation):
    """NON-REGRESSION.

    Bug constate le 31/07 : quand le client se deconnectait en cours de reponse,
    Python fermait le generateur et la reponse n'etait jamais enregistree. Pour
    un systeme dont la memoire est la raison d'etre, c'est inacceptable.
    Corrige par un bloc `finally` dans answer_stream.
    """
    flux = orchestrator.answer_stream(
        [{"role": "user", "content": "question interrompue"}],
        conversation_external_id=conversation,
    )
    next(flux)  # un seul morceau consomme
    flux.close()  # le client ferme l'onglet

    lignes = _messages_de(conversation)
    assert len(lignes) == 2, "la reponse partielle doit etre conservee"
    assert lignes[1][1] == "premier "
    assert lignes[1][2]["interrompu"] is True
