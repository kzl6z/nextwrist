"""La memoire, de la phrase prononcee jusqu'a la base et retour.

⚠️ CE FICHIER EXIGE POSTGRES, ET C'EST TOUT SON INTERET.

Les bancs du moteur (`test_memoire_moteur.py`) tournent partout, sans base :
c'est ce qui les rend fiables. Mais un moteur juste dont RIEN N'APPELLE
L'ECRITURE est exactement le defaut que ce chantier corrige — l'intention
« memoire » etait reconnue depuis des mois, avec zero ligne ecrite derriere.

Ces bancs-la vont donc jusqu'au bout : POST /v1/action, la base, et le prompt.

LA RECETTE DU CAHIER DES CHARGES, §14

    « Souviens-toi que mon projet s'appelle NOVA »
    (redemarrage)
    « Comment s'appelle mon projet ? »
    → Nova doit retrouver l'information.

Le redemarrage est simule en vidant le cache de l'orchestrateur : c'est
exactement ce qu'un relancement fait, et cela evite un banc qui dure trente
secondes.
"""

from __future__ import annotations

import pytest

from nova.memory import facts

psycopg = pytest.importorskip("psycopg")


def _schema_pret() -> bool:
    from nova.settings import get_settings

    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return (
                conn.execute("SELECT to_regclass('public.facts')").fetchone()[0]
                is not None
            )
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _schema_pret(),
    reason="base absente ou migrations non appliquees — lance `uv run nova db migrate`",
)


@pytest.fixture
def memoire_vide():
    """Une memoire propre avant et apres. On archive, on ne supprime pas.

    ⚠️ MEME REGLE QUE LE CODE : ARCHIVER, PAS EFFACER.

    Un banc qui ferait `DELETE FROM facts` effacerait la memoire reelle de
    quelqu'un qui lance la suite sur sa machine. Archiver rend les faits
    invisibles a Nova sans rien detruire.
    """
    for fait in facts.list_facts():
        facts.archive(fait.id)
    yield
    for fait in facts.list_facts():
        facts.archive(fait.id)


def _client():
    from fastapi.testclient import TestClient

    from nova.api.app import app

    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
#  LA RECETTE DU §14 — LE BANC CENTRAL DE TOUT CE CHANTIER
# ══════════════════════════════════════════════════════════════════════════
def test_memoriser_puis_redemarrer_puis_se_souvenir(memoire_vide, monkeypatch):
    """⚠️ CE BANC NE POUVAIT PAS PASSER AVANT CE CHANTIER.

    L'intention etait reconnue, aucune action ne se trouvait derriere, et zero
    ligne partait en base. Nova repondait poliment sans avoir rien retenu.
    """
    from nova import orchestrator
    from nova.documents import search as document_search
    from nova.memory import conversations

    with _client() as client:
        reponse = client.post(
            "/v1/action",
            json={"texte": "souviens-toi que mon projet s'appelle NOVA"},
        ).json()

    assert reponse["etat"] == "executee"
    assert reponse["message"] == "C'est noté."
    # ⚠️ ON VERIFIE LA BASE, PAS LE MESSAGE.
    #
    # « Ne jamais pretendre qu'une memoire est enregistree si elle ne l'est
    # pas » — regle explicite du cahier des charges. Un banc qui se contente
    # du message verifierait la politesse de Nova, pas sa memoire.
    en_base = [f.content for f in facts.list_facts(status="confirmed")]
    assert "mon projet s'appelle NOVA" in en_base

    # Le redemarrage : le cache tombe, tout doit venir de la base.
    orchestrator.oublier_le_vocabulaire()
    monkeypatch.setattr(document_search, "search", lambda *a, **k: [])
    monkeypatch.setattr(conversations, "derniers_echanges", lambda *a, **k: [])

    prompt, _ = orchestrator.build_system_prompt("comment s'appelle mon projet ?")

    assert "mon projet s'appelle NOVA" in prompt


def test_le_message_ne_ment_pas_quand_rien_n_est_ecrit(memoire_vide):
    """⚠️ « C'EST NOTE » SANS NOTER EST PIRE QU'UNE ABSENCE DE MEMOIRE.

    On cesse de verifier. Une phrase que le moteur ne sait pas decouper doit
    donc dire qu'elle n'a pas ete comprise, pas dire que c'est fait.
    """
    with _client() as client:
        reponse = client.post("/v1/action", json={"texte": "il fait chaud"}).json()

    assert reponse["intention"] != "retenir_memoire"
    assert facts.list_facts(status="confirmed") == []


# ══════════════════════════════════════════════════════════════════════════
#  MISE A JOUR ET CONTRADICTION, EN BASE
# ══════════════════════════════════════════════════════════════════════════
def test_une_information_qui_change_remplace_l_ancienne(memoire_vide):
    """⚠️ SANS CELA, DEUX FAITS CONTRADICTOIRES COEXISTAIENT DANS LE PROMPT.

    « Le modèle principal est X » et « le modèle principal est Y », tous deux
    confirmes, tous deux injectes. Le modele en choisissait un — au hasard, du
    point de vue de l'utilisateur.
    """
    with _client() as client:
        client.post(
            "/v1/action",
            json={"texte": "retiens que le modèle principal de NOVA est llama"},
        )
        client.post(
            "/v1/action",
            json={"texte": "retiens que le modèle principal de NOVA est qwen"},
        )

    actifs = [f.content for f in facts.list_facts(status="confirmed")]

    assert len(actifs) == 1, f"un seul modèle principal, pas deux : {actifs}"
    assert "qwen" in actifs[0], "le plus récent gagne"


def test_le_fait_remplace_dit_ce_qu_il_remplace(memoire_vide):
    """⚠️ ON N'ECRASE PAS : LE LIEN GARDE L'HISTORIQUE DU CHANGEMENT.

    Ecraser la ligne effacerait le fait qu'un changement a eu lieu — et
    l'historique de tes changements d'avis est une information, pas un dechet.
    C'est deja la raison pour laquelle `archive` existe plutot qu'un DELETE.
    """
    with _client() as client:
        client.post("/v1/action", json={"texte": "retiens que j'habite à Lyon"})
        client.post("/v1/action", json={"texte": "retiens que j'habite à Paris"})

    nouveau = facts.list_facts(status="confirmed")[0]

    assert nouveau.supersedes is not None, "le nouveau désigne celui qu'il remplace"


# ══════════════════════════════════════════════════════════════════════════
#  L'OUBLI, EN BASE
# ══════════════════════════════════════════════════════════════════════════
def test_oublie_ca_retire_reellement_le_fait(memoire_vide):
    with _client() as client:
        client.post("/v1/action", json={"texte": "retiens que j'habite à Lyon"})
        assert facts.list_facts(status="confirmed")

        reponse = client.post("/v1/action", json={"texte": "oublie ça"}).json()

    assert reponse["etat"] == "executee"
    assert facts.list_facts(status="confirmed") == [], "réellement retiré"


def test_n_oublie_pas_que_RETIENT_au_lieu_d_effacer(memoire_vide):
    """⚠️ LE CONTRESENS LE PLUS DANGEREUX DE TOUT CE MODULE.

    Les deux formules contiennent le mot « oublie ». Sans la garde de
    negation, cette phrase effacait un fait au moment precis ou l'on demandait
    de le garder — et l'oubli etant teste en premier, il gagnait.

    Trouve par un banc, pas par la relecture : les deux motifs avaient l'air
    distincts en les lisant l'un apres l'autre.
    """
    with _client() as client:
        client.post("/v1/action", json={"texte": "retiens que j'habite à Lyon"})
        reponse = client.post(
            "/v1/action",
            json={"texte": "n'oublie pas que je suis allergique aux arachides"},
        ).json()

    assert reponse["intention"] == "retenir_memoire", "c'est une demande de RETENIR"
    contenus = [f.content for f in facts.list_facts(status="confirmed")]
    assert any("arachides" in c for c in contenus)
    assert any("Lyon" in c for c in contenus), "et rien n'a été effacé"


# ══════════════════════════════════════════════════════════════════════════
#  L'INTEGRATION AVEC LES AGENTS
# ══════════════════════════════════════════════════════════════════════════
def test_un_agent_peut_consulter_la_memoire_sans_la_recevoir_entiere(memoire_vide):
    """⚠️ UN AGENT NE RECOIT PAS AUTOMATIQUEMENT TOUTE LA MEMOIRE.

    Il la DEMANDE, par un outil, et l'outil passe par le meme portillon que
    toute autre lecture. C'est la difference entre une capacite et un
    privilège.
    """
    from nova.outils import executer_outil

    with _client() as client:
        client.post("/v1/action", json={"texte": "retiens que j'habite à Lyon"})

        trouve = executer_outil("chercher_memoire")

    assert any("Lyon" in item["fait"] for item in trouve)
