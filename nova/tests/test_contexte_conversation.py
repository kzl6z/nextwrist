"""Le contexte conversationnel : « Et on pourrait y vivre ? »

LE DEFAUT QUE CES TESTS PROTEGENT

Trois defauts qui n'en formaient qu'un, et qui rendaient toute reference
implicite impossible :

  1. `brain.js` envoyait UN SEUL message — jamais l'historique.
  2. `conversations.py` savait ecrire et pas relire : aucun lecteur.
  3. Faute d'identifiant, Nova Core creait une conversation NEUVE a chaque
     question. L'historique existait en base, fragmente en lignes d'un seul
     message.

Nova avait donc une memoire parfaite de ce qui s'etait dit, et aucun moyen
de s'en servir :

    — « Parle-moi de Mars. »        Nova repond.
    — « Et on pourrait y vivre ? »  « y » ne renvoyait a rien.

Ce n'etait pas un manque d'intelligence du modele : on ne lui avait
simplement pas donne la phrase precedente.
"""

import pytest

from nova import orchestrator
from nova.memory import conversations


class FausseBase:
    """Une conversation en memoire, avec les messages qu'on lui donne."""

    def __init__(self, messages: list[tuple[str, str]]) -> None:
        # Stockes du plus RECENT au plus ancien, comme le fait la requete
        # (ORDER BY id DESC).
        self.messages = list(reversed(messages))
        self.ecrits: list[tuple[str, str]] = []

    def execute(self, sql: str, params=None):
        if "SELECT role, content" in sql:
            limite = params[1] if params and len(params) > 1 else len(self.messages)
            return _Resultat(
                [{"role": r, "content": c} for r, c in self.messages[:limite]]
            )
        if "INSERT INTO messages" in sql:
            self.ecrits.append((params[1], params[2]))
        return _Resultat([])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Resultat:
    def __init__(self, lignes):
        self.lignes = lignes

    def fetchall(self):
        return self.lignes

    def fetchone(self):
        return self.lignes[0] if self.lignes else None


@pytest.fixture
def base(monkeypatch):
    def installer(messages):
        fausse = FausseBase(messages)
        monkeypatch.setattr(conversations, "connection", lambda: fausse)
        return fausse

    return installer


# ── Le lecteur qui manquait ───────────────────────────────────────────────


def test_les_echanges_reviennent_dans_l_ordre_du_temps(base):
    """Le modele lit du passe vers le present, pas l'inverse.

    La requete remonte du plus recent (ORDER BY id DESC) pour pouvoir
    s'arreter des que le budget est plein. Rendre cette liste telle quelle
    donnerait une conversation a l'envers — ou « Et on pourrait y vivre ? »
    precederait « Parle-moi de Mars ».
    """
    base([
        ("user", "Parle-moi de Mars."),
        ("assistant", "Mars est la quatrieme planete du systeme solaire."),
        ("user", "Et on pourrait y vivre ?"),
    ])
    echanges = conversations.derniers_echanges(1, budget_caracteres=2000)
    assert [m["content"] for m in echanges] == [
        "Parle-moi de Mars.",
        "Mars est la quatrieme planete du systeme solaire.",
        "Et on pourrait y vivre ?",
    ]


def test_le_budget_garde_le_present_et_sacrifie_le_passe(base):
    """C'est le risque R13 : le passe se paie sur chaque question a venir.

    Quand il faut couper, on coupe le plus ANCIEN. Le contexte immediat est
    celui qui sert a comprendre « y » ou « et chez BMW ».
    """
    base([
        ("user", "A" * 800),
        ("assistant", "B" * 800),
        ("user", "la question la plus recente"),
    ])
    echanges = conversations.derniers_echanges(1, budget_caracteres=900)
    assert echanges[-1]["content"] == "la question la plus recente"
    assert sum(len(m["content"]) for m in echanges) <= 900


def test_un_message_seul_plus_gros_que_le_budget_passe_quand_meme(base):
    """Rendre une liste vide serait pire : on perdrait TOUT le contexte."""
    base([("user", "X" * 5000)])
    assert len(conversations.derniers_echanges(1, budget_caracteres=100)) == 1


def test_les_messages_vides_sont_ignores(base):
    base([("user", "   "), ("assistant", ""), ("user", "une vraie question")])
    echanges = conversations.derniers_echanges(1, budget_caracteres=2000)
    assert [m["content"] for m in echanges] == ["une vraie question"]


def test_le_nombre_de_tours_est_borne_aussi(base):
    """Un budget seul laisserait passer mille messages minuscules."""
    base([("user", f"q{n}") for n in range(200)])
    echanges = conversations.derniers_echanges(1, budget_caracteres=10**6, tours_max=3)
    assert len(echanges) <= 6


def test_une_conversation_neuve_ne_rend_rien(base):
    base([])
    assert conversations.derniers_echanges(1, budget_caracteres=2000) == []


# ── L'assemblage : ou le contexte se retrouve dans le prompt ──────────────


def _sans_modele(monkeypatch, capture: dict):
    """Intercepte l'appel au modele pour observer ce qu'on lui envoie."""

    def faux_stream(self, messages, **kwargs):
        capture["messages"] = messages
        yield "reponse"

    monkeypatch.setattr(orchestrator.LLMClient, "stream", faux_stream)
    monkeypatch.setattr(orchestrator, "build_system_prompt", lambda *a, **k: ("SYS", []))
    monkeypatch.setattr(orchestrator.conversations, "get_or_create", lambda *a, **k: 1)
    monkeypatch.setattr(orchestrator.conversations, "log_message", lambda *a, **k: None)


def test_le_passe_precede_la_question_en_cours(monkeypatch):
    capture: dict = {}
    _sans_modele(monkeypatch, capture)
    monkeypatch.setattr(
        orchestrator.conversations, "derniers_echanges",
        lambda *a, **k: [
            {"role": "user", "content": "Parle-moi de Mars."},
            {"role": "assistant", "content": "Mars est la quatrieme planete."},
        ],
    )

    list(orchestrator.answer_stream([{"role": "user", "content": "Et on pourrait y vivre ?"}]))

    roles = [m["role"] for m in capture["messages"]]
    contenus = [m["content"] for m in capture["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert contenus[-1] == "Et on pourrait y vivre ?", "la question du moment vient en dernier"
    assert "Mars" in contenus[1]


def test_un_client_qui_envoie_son_historique_fait_foi(monkeypatch):
    """Deux versions du meme passe, dans le desordre, seraient pires que rien.

    L'application de bureau n'envoie qu'un message ; un autre client peut
    envoyer toute la conversation. Injecter la notre par-dessus la sienne
    donnerait au modele deux recits concurrents, sans moyen de trancher.
    """
    capture: dict = {}
    _sans_modele(monkeypatch, capture)
    appels = {"lecture": 0}
    monkeypatch.setattr(
        orchestrator.conversations, "derniers_echanges",
        lambda *a, **k: appels.__setitem__("lecture", appels["lecture"] + 1) or [],
    )

    list(orchestrator.answer_stream([
        {"role": "user", "content": "premiere"},
        {"role": "assistant", "content": "reponse"},
        {"role": "user", "content": "seconde"},
    ]))

    assert appels["lecture"] == 0, "le client fournissait deja son contexte"
    assert [m["content"] for m in capture["messages"]] == [
        "SYS", "premiere", "reponse", "seconde",
    ]


def test_un_historique_indisponible_n_empeche_pas_de_repondre(monkeypatch):
    """Chaque capacite est facultative : sans contexte, Nova repond quand meme."""
    capture: dict = {}
    _sans_modele(monkeypatch, capture)

    def casse(*a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(orchestrator.conversations, "derniers_echanges", casse)

    morceaux = list(orchestrator.answer_stream([{"role": "user", "content": "bonjour"}]))
    assert morceaux == ["reponse"]
    assert [m["content"] for m in capture["messages"]] == ["SYS", "bonjour"]


def test_la_question_en_cours_ne_figure_pas_deux_fois(monkeypatch):
    """On relit AVANT de journaliser : sinon la question serait a la fois
    passe et present, et le modele croirait qu'on se repete."""
    capture: dict = {}
    ordre: list[str] = []
    _sans_modele(monkeypatch, capture)
    monkeypatch.setattr(
        orchestrator.conversations, "derniers_echanges",
        lambda *a, **k: ordre.append("lecture") or [],
    )
    monkeypatch.setattr(
        orchestrator.conversations, "log_message",
        lambda *a, **k: ordre.append("ecriture"),
    )

    list(orchestrator.answer_stream([{"role": "user", "content": "bonjour"}]))
    assert ordre[:2] == ["lecture", "ecriture"]


# ── Le budget est configurable, comme les autres ──────────────────────────


def test_le_budget_de_contexte_est_configurable():
    budget = orchestrator.get_tuning().historique_budget
    assert 200 <= budget <= 10000
