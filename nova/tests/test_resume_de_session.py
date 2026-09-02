"""Le resume de session : ce qui reste quand les messages tombent du budget.

⚠️ LE DEFAUT QUE CES BANCS SURVEILLENT EST SILENCIEUX.

`derniers_echanges` borne le passe a 1200 caracteres en gardant les messages
RECENTS. C'est le bon arbitrage — le present avant le passe — mais au bout
d'une heure de travail, tout ce qui a ete etabli au debut a disparu du
prompt. Sans un mot, sans une ligne de journal : on croit parler a quelqu'un
qui suit, et on parle a quelqu'un qui a oublie le sujet.

    — « On part sur un moteur electrique, batterie a l'arriere. »
      … quarante messages plus tard …
    — « Et le refroidissement, on le met ou ? »
      « De quel refroidissement parles-tu ? »

Le premier banc de ce fichier REPRODUIT cette perte. Les suivants verifient
qu'un resume la comble sans faire grossir le prompt.
"""

from __future__ import annotations

import importlib
import threading
import uuid

import pytest

from nova.memory import resume

psycopg = pytest.importorskip("psycopg")


def _schema_pret() -> bool:
    from nova.settings import get_settings

    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return (
                conn.execute("SELECT to_regclass('public.resumes_de_session')").fetchone()[0]
                is not None
            )
    except Exception:  # noqa: BLE001
        return False


#: ⚠️ PAS DE `pytestmark` GLOBAL ICI.
#:
#: La mise en forme du resume — troncature, bloc de prompt — n'a besoin
#: d'aucune base. La marquer « Postgres requis » la ferait sauter sur toute
#: machine sans base, et ces bancs-la sont precisement ceux qui tournent
#: partout.
besoin_de_base = pytest.mark.skipif(
    not _schema_pret(),
    reason="base absente ou migrations non appliquees — lance `uv run nova db migrate`",
)

DEBUT = "on part sur un moteur electrique, batterie a l'arriere"


@pytest.fixture
def conversation():
    """Une conversation a nous, effacee a la fin.

    ⚠️ ON EFFACE ICI, CONTRAIREMENT AUX BANCS DE MEMOIRE.

    La memoire s'archive plutot que de se supprimer, parce qu'un banc lance
    sur la machine de quelqu'un effacerait ses faits. Cette conversation-ci
    n'existe que pour le banc : son identifiant externe porte un UUID, elle
    ne peut appartenir a personne.
    """
    from nova.db import connection
    from nova.memory import conversations

    cid = conversations.get_or_create(f"banc-resume-{uuid.uuid4()}")
    yield cid
    with connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id = %s", (cid,))


def _dire(cid: int, combien: int, *, longueur: int = 80, depart: int = 0) -> None:
    from nova.memory import conversations

    for i in range(depart, depart + combien):
        role = "user" if i % 2 == 0 else "assistant"
        texte = f"message {i:03d} " + "x" * max(0, longueur - 12)
        conversations.log_message(cid, role, texte)


def _poser_un_resume(cid: int, texte: str, jusqu_a: int) -> None:
    from nova.db import connection

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO resumes_de_session (conversation_id, resume, jusqu_au_message)
            VALUES (%s, %s, %s)
            """,
            (cid, texte, jusqu_a),
        )


def _identifiants(cid: int) -> list[int]:
    from nova.db import connection

    with connection() as conn:
        return [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM messages WHERE conversation_id = %s ORDER BY id", (cid,)
            ).fetchall()
        ]


# ══════════════════════════════════════════════════════════════════════════
#  LE DEFAUT, REPRODUIT
# ══════════════════════════════════════════════════════════════════════════


@besoin_de_base
def test_le_debut_d_une_longue_conversation_tombe_du_budget(conversation):
    """⚠️ C'EST LA PERTE QUE CE CHANTIER CORRIGE, ECRITE NOIR SUR BLANC.

    Sans ce banc, rien ne dit que le probleme existait, et le module suivant
    ressemblerait a une precaution theorique.
    """
    from nova.memory import conversations

    conversations.log_message(conversation, "user", DEBUT)
    _dire(conversation, 40, depart=1)

    rappeles = conversations.derniers_echanges(conversation, budget_caracteres=1200)

    assert rappeles, "le rappel brut ne rend rien du tout"
    assert not any(DEBUT in m["content"] for m in rappeles), (
        "le debut tenait encore dans le budget : le banc ne reproduit rien"
    )


# ══════════════════════════════════════════════════════════════════════════
#  LA LECTURE
# ══════════════════════════════════════════════════════════════════════════


@besoin_de_base
def test_sans_resume_le_rappel_est_exactement_celui_d_avant(conversation):
    """Ce module doit pouvoir arriver sans rien changer.

    Tant que le fil d'entretien n'a pas tourne, `rappeler` rend ce que
    `derniers_echanges` rendait — sinon on ne saurait pas si un changement de
    comportement vient du resume ou de son absence.
    """
    from nova.memory import conversations

    _dire(conversation, 6)

    rappel = resume.rappeler(conversation, budget_caracteres=1200)

    assert rappel.resume == ""
    assert rappel.messages == conversations.derniers_echanges(
        conversation, budget_caracteres=1200
    )


@besoin_de_base
def test_avec_un_resume_le_debut_de_la_conversation_survit(conversation):
    """La meme conversation que le banc du defaut, avec un resume par-dessus."""
    from nova.memory import conversations

    conversations.log_message(conversation, "user", DEBUT)
    _dire(conversation, 40, depart=1)
    ids = _identifiants(conversation)
    _poser_un_resume(conversation, f"- {DEBUT}", ids[30])

    rappel = resume.rappeler(conversation, budget_caracteres=1200)

    assert DEBUT in rappel.resume, "le debut est reste perdu"
    assert DEBUT in resume.bloc(rappel)


@besoin_de_base
def test_un_message_couvert_par_le_resume_ne_revient_pas_brut(conversation):
    """⚠️ DEUX VERSIONS DU MEME PASSE N'EN FONT PAS UNE MEILLEURE.

    Un message a la fois resume et cite mot pour mot donne au modele deux
    recits du meme moment, sans aucun moyen de savoir qu'il s'agit du meme.
    """
    _dire(conversation, 20)
    ids = _identifiants(conversation)
    _poser_un_resume(conversation, "- resume des dix premiers", ids[9])

    rappel = resume.rappeler(conversation, budget_caracteres=4000)

    rappeles = " ".join(m["content"] for m in rappel.messages)
    assert "message 009" not in rappeles, "un message couvert par le resume est revenu brut"
    assert "message 010" in rappeles, "le premier message non couvert manque : il y a un trou"


@besoin_de_base
def test_le_rappel_tient_dans_le_budget(conversation):
    """⚠️ LE RESUME PREND UNE PART DU BUDGET, IL NE S'Y AJOUTE PAS.

    Corriger l'oubli en allongeant le prompt de 700 caracteres deplacerait le
    probleme sur CHAQUE question suivante — a 3,3 ms par caractere mesures
    sur la machine de reference, deux secondes de plus avant le premier mot.
    C'est le risque R13, et il ne se contourne pas par la porte de derriere.
    """
    _dire(conversation, 20, longueur=120)
    ids = _identifiants(conversation)
    _poser_un_resume(conversation, "\n".join(f"- point numero {i}" * 4 for i in range(12)), ids[9])

    rappel = resume.rappeler(conversation, budget_caracteres=1200)

    total = len(rappel.resume) + sum(len(m["content"]) for m in rappel.messages)
    assert rappel.resume, "le resume a entierement disparu : le partage est mal regle"
    assert total <= 1200, f"le rappel pese {total} caracteres pour un budget de 1200"


@besoin_de_base
def test_quand_le_present_remplit_le_budget_c_est_le_resume_qui_cede(conversation):
    """Le present passe avant le passe, ici comme partout ailleurs."""
    from nova.memory import conversations

    conversations.log_message(conversation, "user", "a" * 3000)
    ids = _identifiants(conversation)
    _poser_un_resume(conversation, "- un resume qu'on ne verra pas", ids[0] - 1)

    rappel = resume.rappeler(conversation, budget_caracteres=1200)

    assert rappel.messages, "le message present a ete jete"
    assert rappel.resume == "", "le resume s'est ajoute par-dessus un budget deja plein"


@besoin_de_base
def test_lire_le_passe_n_appelle_aucun_modele(conversation, monkeypatch):
    """⚠️ LA LECTURE EST SUR LE CHEMIN DE CHAQUE REPONSE.

    Un appel de modele glisse ici coute plusieurs secondes AVANT le premier
    mot de Nova, a chaque question. Ce banc casse le banc si quelqu'un
    l'introduit, plutot que de le decouvrir a l'oreille.
    """
    from nova.modeles import routage

    def interdit(*args, **kwargs):
        raise AssertionError("un modele a ete appele pour relire le passe")

    monkeypatch.setattr(routage, "generer", interdit)
    monkeypatch.setattr(routage, "flux", interdit)

    _dire(conversation, 20)
    ids = _identifiants(conversation)
    _poser_un_resume(conversation, "- deja resume", ids[9])

    assert resume.rappeler(conversation, budget_caracteres=1200).resume


# ══════════════════════════════════════════════════════════════════════════
#  QUAND RESUMER — sans modele, donc verifiable
# ══════════════════════════════════════════════════════════════════════════


@besoin_de_base
def test_une_conversation_courte_ne_vaut_pas_un_appel_de_modele(conversation):
    _dire(conversation, 10)

    assert resume.a_resumer(conversation) is None


@besoin_de_base
def test_les_derniers_messages_restent_hors_du_resume(conversation):
    """⚠️ « ET ON POURRAIT Y VIVRE ? » NE SE RESOUT PAS AVEC UN RESUME.

    « L'utilisateur a parle de Mars » ne dit pas a quoi « y » renvoie : il
    faut la phrase, telle qu'elle a ete dite. Le resume sert le lointain ; le
    proche reste brut, toujours.

    ⚠️ CE BANC LISAIT `resume.GARDE_BRUTE` DANS SON ASSERTION.

    Il suivait donc la constante : mise a zero, le banc restait vert en
    verifiant tranquillement que zero message etait garde. Un banc qui
    s'aligne sur ce qu'il surveille ne surveille rien. Les nombres sont
    ecrits en clair.
    """
    _dire(conversation, 20)
    ids = _identifiants(conversation)

    _, echanges, jusqu_a = resume.a_resumer(conversation)

    assert len(echanges) == 14
    assert jusqu_a == ids[13]
    plies = " ".join(m["content"] for m in echanges)
    assert "message 013" in plies
    assert "message 014" not in plies, "un des six derniers messages a ete plie"
    assert "message 019" not in plies


@besoin_de_base
def test_une_conversation_qui_parle_encore_n_est_pas_resumee(conversation):
    """Le silence se mesure par conversation, pas sur la machine."""
    _dire(conversation, 20)

    assert conversation not in resume.conversations_posees(silence_s=120.0)
    assert conversation in resume.conversations_posees(silence_s=0.0)


# ══════════════════════════════════════════════════════════════════════════
#  L'ECRITURE
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def modele_de_facade(monkeypatch):
    """Un modele qui rend un resume fixe, et retient ce qu'on lui a demande."""
    from nova.modeles import routage

    appels: list[tuple[str, str]] = []

    def generer(usage, messages, **kwargs):
        appels.append((usage, "\n".join(m["content"] for m in messages)))
        return f"- resume numero {len(appels)}\n- {DEBUT}"

    monkeypatch.setattr(routage, "generer", generer)
    return appels


@besoin_de_base
def test_resumer_ecrit_une_ligne_relisible(conversation, modele_de_facade):
    _dire(conversation, 20)

    texte = resume.resumer(conversation)

    assert texte
    enregistre = resume.courant(conversation)
    assert enregistre is not None
    assert enregistre.texte == texte
    assert enregistre.jusqu_au_message == _identifiants(conversation)[13]


@besoin_de_base
def test_resumer_ne_replie_pas_deux_fois_les_memes_messages(conversation, modele_de_facade):
    """Sans borne, chaque passage du fil relirait toute la conversation."""
    _dire(conversation, 20)
    resume.resumer(conversation)

    assert resume.resumer(conversation) is None, "le meme passe a ete replie une seconde fois"
    assert len(modele_de_facade) == 1


@besoin_de_base
def test_le_resume_precedent_entre_dans_le_suivant(conversation, modele_de_facade):
    """⚠️ C'EST TOUT LE MECANISME : LE DEBUT SURVIT A N COMPRESSIONS.

    Sans cette reinjection, chaque resume ne couvrirait que la tranche qui
    vient de passer, et le debut de la conversation retomberait du prompt une
    heure plus tard — le defaut d'origine, avec une etape de plus.
    """
    _dire(conversation, 20)
    premier = resume.resumer(conversation)
    _dire(conversation, 20, depart=100)

    second = resume.resumer(conversation)

    assert second is not None
    assert premier in modele_de_facade[1][1], (
        "le premier resume n'a pas ete redonne au modele : le debut est perdu"
    )


@besoin_de_base
def test_le_resume_ne_sort_pas_de_la_machine(conversation, modele_de_facade):
    """⚠️ UNE CONVERSATION ENTIERE PARTANT CHEZ UN TIERS POUR ETRE CONDENSEE.

    C'est le pire endroit ou relacher la regle du local d'abord : le resume
    voit TOUT, y compris ce qui n'aurait jamais ete cite dans une question.
    """
    from nova.core.routeur import USAGES

    _dire(conversation, 20)
    resume.resumer(conversation)

    usage = modele_de_facade[0][0]
    assert usage == "extraction"
    assert USAGES[usage].local_exige, f"l'usage « {usage} » autorise la sortie des donnees"


@besoin_de_base
def test_le_resume_survit_a_un_redemarrage(conversation, modele_de_facade):
    """⚠️ EN MEMOIRE VIVE, IL AURAIT DISPARU AU PREMIER REDEMARRAGE.

    Le module est recharge : tout etat qu'il garderait en variable est perdu,
    comme dans un nouveau processus. Ce qui revient vient donc de la base.
    """
    _dire(conversation, 20)
    ecrit = resume.resumer(conversation)

    recharge = importlib.reload(resume)

    retrouve = recharge.courant(conversation)
    assert retrouve is not None and retrouve.texte == ecrit


@besoin_de_base
def test_un_passage_ne_resume_qu_une_conversation(conversation, modele_de_facade, monkeypatch):
    """Vingt conversations en retard, c'est vingt appels de modele d'affilee.

    Le fil n'est jamais presse : il en fait une, dort une minute, et rattrape
    son retard en vingt minutes que personne ne voit.
    """
    from nova.db import connection
    from nova.memory import conversations as journal

    # Le fil attend deux minutes de silence ; le banc n'attend pas.
    monkeypatch.setattr(resume, "SILENCE_S", 0.0)
    autre = journal.get_or_create(f"banc-resume-{uuid.uuid4()}")
    try:
        _dire(conversation, 20)
        _dire(autre, 20)

        assert resume.un_passage() == 1
        assert len(modele_de_facade) == 1
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = %s", (autre,))


@besoin_de_base
def test_le_fil_survit_a_un_passage_qui_leve(conversation, monkeypatch):
    """Un resume rate degrade une conversation longue. Il n'arrete pas le fil."""
    monkeypatch.setattr(resume, "DEMARRAGE_S", 0.0)
    monkeypatch.setattr(resume, "REPOS_S", 0.0)
    passages: list[int] = []

    def casse() -> int:
        passages.append(1)
        if len(passages) >= 3:
            arret.set()
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(resume, "un_passage", casse)
    arret = threading.Event()

    resume.entretenir(arret)

    assert len(passages) >= 3, "le fil s'est arrete au premier echec"


# ══════════════════════════════════════════════════════════════════════════
#  LE CABLAGE
#
#  ⚠️ SANS CES DEUX BANCS, TOUT CE QUI PRECEDE POURRAIT ETRE JUSTE ET INUTILE.
#
#  C'est exactement le defaut que le Model Router a corrige : un module qui
#  existe, qui est teste, et dont personne ne lit le resultat. Ici il y a deux
#  fils a couper — la lecture dans l'orchestrateur, l'ecriture dans le fil
#  d'entretien — et couper l'un ou l'autre suffit a ce que le resume
#  n'existe qu'en theorie.
# ══════════════════════════════════════════════════════════════════════════


def test_l_orchestrateur_donne_le_resume_au_modele(monkeypatch):
    """La lecture : sans ce banc, `rappeler` pourrait n'etre appele nulle part."""
    from nova import orchestrator

    capture: dict = {}

    def faux_flux(usage, messages, **kwargs):
        capture["messages"] = messages
        yield "reponse"

    monkeypatch.setattr(orchestrator.routage, "flux", faux_flux)
    monkeypatch.setattr(orchestrator, "build_system_prompt", lambda *a, **k: ("SYS", []))
    monkeypatch.setattr(orchestrator.conversations, "get_or_create", lambda *a, **k: 1)
    monkeypatch.setattr(orchestrator.conversations, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator.resume,
        "rappeler",
        lambda *a, **k: resume.Rappel(resume=f"- {DEBUT}", messages=[]),
    )

    # « et pourquoi ? » ne porte aucun sujet : c'est une phrase qui s'appuie
    # sur ce qui precede, donc une de celles qui declenchent le rappel.
    list(orchestrator.answer_stream([{"role": "user", "content": "et pourquoi ?"}]))

    entete = capture["messages"][0]["content"]
    assert entete.startswith("SYS"), "le resume a remplace le prompt systeme"
    assert DEBUT in entete, "le resume n'est jamais arrive jusqu'au modele"


def test_le_fil_de_resume_demarre_avec_nova(monkeypatch):
    """L'ecriture : la lecture est cablee, mais rien n'ecrirait jamais une ligne."""
    import asyncio

    from nova.api import app as api

    lances: list[tuple[str, object]] = []

    class FilDeFacade:
        def __init__(self, target=None, name="", **kwargs):
            lances.append((name, target))

        def start(self):
            pass

    monkeypatch.setattr(api.threading, "Thread", FilDeFacade)
    monkeypatch.setattr(api, "run_migrations", lambda: [])

    async def demarrer():
        async with api.lifespan(None):
            pass

    asyncio.run(demarrer())

    noms = {nom for nom, _ in lances}
    assert "resumes" in noms, f"aucun fil de resume au demarrage — fils lances : {noms}"
    cible = next(cible for nom, cible in lances if nom == "resumes")
    assert cible is resume.entretenir


# ══════════════════════════════════════════════════════════════════════════
#  LA MISE EN FORME — aucune base requise
# ══════════════════════════════════════════════════════════════════════════


def test_la_troncature_coupe_a_la_ligne_jamais_au_milieu_d_un_point():
    """Un point coupe en deux devient une phrase FAUSSE — pire que perdue."""
    texte = "- le moteur est electrique\n- la batterie est a l'arriere\n- reste le froid"

    coupe = resume._tronquer(texte, 40)

    assert coupe == "- le moteur est electrique"


def test_la_troncature_laisse_passer_ce_qui_tient():
    texte = "- une seule ligne"
    assert resume._tronquer(texte, 700) == texte


def test_le_bloc_est_vide_quand_il_n_y_a_pas_de_resume():
    """Un titre « ## Le debut de cette conversation » suivi de rien serait pire
    que rien : le modele inventerait ce qui manque sous le titre."""
    assert resume.bloc(resume.Rappel()) == ""


def test_le_bloc_ne_porte_aucune_consigne_de_comportement():
    """⚠️ UN MODELE DE 3 MILLIARDS CONTINUE CE QU'IL VIENT DE LIRE.

    « Ne reponds pas a ce resume » est une consigne qu'il enfreint une fois
    sur trois, et qui lui souffle en prime l'idee d'y repondre. Un titre et du
    texte : il le lit comme du contexte, ce qu'il est.
    """
    rendu = resume.bloc(resume.Rappel(resume="- le moteur est electrique"))

    assert "## Le debut de cette conversation" in rendu
    assert "- le moteur est electrique" in rendu
    assert "reponds" not in rendu.lower()
    assert "n'invente" not in rendu.lower()
