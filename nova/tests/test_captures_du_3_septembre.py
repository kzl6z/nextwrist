"""Quatre defauts releves sur les journaux de la machine, le 3 septembre.

    « je cherche a creer une centrale nucleaire. Donc, l'objectif, c'est de
      produire 900 MW, on part sur un »
    → « C'est ouvert : centrale nucleaire. Donc, l'objectif, c'est de
        produire 900 MW, on part sur un. »
    → puis un DOSSIER de ce nom, cree sur le Bureau.

    [reveil] → « Hier, le poste, le poste, le poste. »
    → « Le public s'est montre car 3 photos de toi avec ta casquette
        blanche sur ton bureau. »

Le premier est un nom qui avale un paragraphe. Le second est Nova qui
s'entend elle-meme et se repond. Les deux ont la meme cause profonde : on
avait suppose une phrase la ou Whisper rend un bloc.
"""

from __future__ import annotations

import pytest

from nova.contexte import commandes
from nova.voice import interruption

#: La transcription exacte du journal.
BLOC = (
    "je cherche à créer une centrale nucléaire. Donc, l'objectif, c'est de "
    "produire 900 MW, on part sur un refroidissement passif parce qu'il n'y "
    "a pas de pompe"
)


# ══════════════════════════════════════════════════════════════════════════
#  1. LE NOM DU PROJET AVALAIT LA PHRASE — ET LE DOSSIER AVEC
# ══════════════════════════════════════════════════════════════════════════


def test_le_nom_du_projet_s_arrete_a_la_premiere_phrase():
    """⚠️ CE NOM DEVIENT UN DOSSIER SUR LE BUREAU.

    `(?P<nom>.+?)$` prenait tout jusqu'a la fin. Nova a ouvert un projet
    nomme comme ce paragraphe, puis en a fait un dossier du meme nom — qu'il
    faut ensuite retrouver et supprimer a la main.
    """
    ordre = commandes.lire(BLOC)

    assert ordre is not None
    assert ordre.genre == "ouvrir"
    assert ordre.contenu == "centrale nucléaire"


@pytest.mark.parametrize(
    ("phrase", "nom"),
    [
        ("Nova, ouvre le projet moteur. Et ensuite on verra", "moteur"),
        ("je veux construire une fusée, donc il faudra du budget", "fusée"),
        ("revenons au projet moteur ; on avait dit quoi ?", "moteur"),
    ],
)
def test_le_nom_s_arrete_avant_ce_qui_enchaine(phrase, nom):
    ordre = commandes.lire(phrase)

    assert ordre is not None
    assert ordre.contenu == nom


def test_un_nom_de_projet_reste_court():
    """Whisper rend parfois trente secondes de parole d'un bloc."""
    long = "je cherche à créer " + "un truc très long " * 20
    ordre = commandes.lire(long)

    assert ordre is not None
    assert len(ordre.contenu) <= commandes.NOM_DE_PROJET_MAX


# ══════════════════════════════════════════════════════════════════════════
#  2. TROIS ORDRES DANS UNE TRANSCRIPTION, UN SEUL EXECUTE
# ══════════════════════════════════════════════════════════════════════════


def test_une_transcription_peut_porter_plusieurs_ordres():
    """⚠️ ON PARLE EN ENCHAINANT ; LE DECOUPAGE DOIT S'ADAPTER.

    `lire` n'en rendait qu'un — le premier — et les deux autres etaient
    perdus sans que rien ne le dise. L'objectif et la decision d'un projet
    qu'on venait d'ouvrir.
    """
    ordres = commandes.lire_tous(BLOC)

    assert [o.genre for o in ordres] == ["ouvrir", "objectif", "decision"]
    assert ordres[0].contenu == "centrale nucléaire"
    assert "900 MW" in ordres[1].contenu
    assert ordres[2].contenu == "un refroidissement passif"
    assert ordres[2].pourquoi == "il n'y a pas de pompe"


def test_la_ponctuation_du_francais_parle_ne_casse_plus_les_marqueurs():
    """⚠️ « L'OBJECTIF, C'EST… » DEVENAIT « l objectif  c est » — DEUX ESPACES.

    L'aplatissement preserve les positions : une virgule au milieu d'une
    formule y laisse un espace de PLUS, et le motif ecrit avec un seul espace
    ne matchait plus. C'est la ponctuation la plus naturelle du francais parle
    qui tombait, sans que rien ne le dise.
    """
    assert commandes.lire("Donc, l'objectif, c'est de produire 900 MW") is not None
    assert commandes.lire("l'objectif c'est de produire 900 MW") is not None


def test_une_phrase_sans_ordre_ne_rend_rien():
    """Le decoupage ne peut pas inventer : sans ordre, il ne rend rien."""
    assert commandes.lire_tous("quelle heure est-il ? il fait beau aujourd'hui") == []
    assert commandes.lire_tous("") == []


# ══════════════════════════════════════════════════════════════════════════
#  3. NOVA S'ENTENDAIT ELLE-MEME, ET SE REPONDAIT
# ══════════════════════════════════════════════════════════════════════════


AUDIO = b"RIFF" + b"\0" * 4000


@pytest.fixture
def entendu(monkeypatch):
    from nova.voice import transcribe

    def installer(texte: str):
        def transcrire(audio, *, langue="fr", modele=None, amorce=None, beam=None):
            return transcribe.Transcription(texte=texte, logprob=-0.15, duree=2.0)

        monkeypatch.setattr(transcribe, "transcrire", transcrire)

    return installer


def _reveil() -> dict:
    from fastapi.testclient import TestClient

    from nova.api.app import app

    reponse = TestClient(app).post(
        "/v1/audio/wake", files={"file": ("x.wav", AUDIO, "audio/wav")}
    )
    assert reponse.status_code == 200
    return reponse.json()


def test_ce_que_nova_entend_pendant_qu_elle_parle_est_de_l_echo(entendu):
    """⚠️ LE CAS EXACT DU JOURNAL, TROIS FOIS DE SUITE.

        [reveil] → « Hier, le poste, le poste, le poste. »
        Nova : « Le public s'est montre car 3 photos de toi… »

    Le micro reste ouvert pendant la lecture : Whisper transcrit la voix de
    Nova, en charabia, et ce charabia repartait au modele comme une question.
    """
    from nova.voice import session

    session.ouvrir()
    interruption.nova_parle_pendant(5.0)
    entendu("Hier, le poste, le poste, le poste.")

    reponse = _reveil()

    assert reponse["wake"] is False, "Nova a répondu à son propre écho"
    assert reponse["commande"] == ""


def test_attends_traverse_meme_pendant_qu_elle_parle(entendu):
    """⚠️ ON NE FERME PAS L'OREILLE, ET C'EST TOUT LE POINT.

    C'est le meme flux qui porte « attends ». Le jeter avec l'echo rendrait
    l'interruption impossible — or c'est PENDANT qu'elle parle qu'on coupe.
    """
    from nova.voice import session

    session.ouvrir()
    interruption.nova_parle_pendant(5.0)
    entendu("attends")

    reponse = _reveil()

    assert interruption.interrompue(), "« attends » a été pris pour de l'écho"
    assert reponse["interrompre"] is True, (
        "l'application n'a aucun moyen de savoir qu'elle doit couper le son"
    )


def test_le_nom_traverse_meme_pendant_qu_elle_parle(entendu):
    """Ignorer quelqu'un qui vous appelle par votre nom n'est jamais correct."""
    from nova.voice import session

    session.ouvrir()
    interruption.nova_parle_pendant(5.0)
    entendu("Nova, quelle heure est-il")

    assert _reveil()["wake"] is True


def test_un_conge_traverse_et_coupe_la_parole(entendu):
    """« c'est bon » doit couper, pas attendre la fin de ce qu'on arrête."""
    from nova.voice import session

    session.ouvrir()
    interruption.nova_parle_pendant(5.0)
    entendu("c'est bon merci")

    _reveil()

    assert not session.est_ouverte()
    assert interruption.interrompue()
    assert not interruption.nova_parle(), "l'oreille reste fermée sur du silence"


def test_une_fois_qu_elle_a_fini_tout_retraverse(entendu):
    """L'echo cesse avec la parole : la fenetre ne dure pas une seconde de
    plus que le son."""
    from nova.voice import session

    session.ouvrir()
    interruption.nova_parle_pendant(-1.0)
    entendu("ouvre le deuxième fichier")

    assert not interruption.nova_parle()
    assert _reveil()["wake"] is True


def test_la_duree_vient_du_wav_pas_du_nombre_de_caracteres(monkeypatch):
    """⚠️ UNE PHRASE COURTE LUE LENTEMENT DURE PLUS QU'UNE LONGUE LUE VITE.

    Et c'est pendant ce surplus que l'echo revient. La duree se lit donc dans
    l'en-tete du WAV, jamais deduite du texte.
    """
    from fastapi.testclient import TestClient

    from nova.api.app import app
    from nova.voice import synthese

    # Deux secondes de silence : court en caracteres, long a prononcer.
    monkeypatch.setattr(synthese, "synthetiser", lambda *a, **k: synthese.silence(2.0))

    TestClient(app).post("/v1/audio/speech", json={"input": "oui"})

    assert interruption.nova_parle()
    assert 1.5 < interruption.secondes_de_parole() <= 2.0


def test_deux_syntheses_de_suite_prolongent_au_lieu_d_ecraser():
    """L'application demande parfois la phrase suivante avant d'avoir fini la
    precedente. Ecraser l'echeance rouvrirait l'oreille au milieu."""
    interruption.nova_parle_pendant(3.0)
    interruption.nova_parle_pendant(3.0)

    assert interruption.secondes_de_parole() > 5.0


def _base_joignable() -> bool:
    """⚠️ « PSYCOPG EST INSTALLE » NE VEUT PAS DIRE « LA BASE REPOND ».

    Le premier `skipif` ne testait que l'import. Le banc tombait donc des que
    Postgres etait arrete — pour une raison qui n'avait rien a voir avec ce
    qu'il protege, et seulement dans la suite complete.
    """
    try:
        import psycopg

        from nova.settings import get_settings

        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return conn.execute("SELECT to_regclass('public.projets')").fetchone()[0] is not None
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _base_joignable(), reason="base injoignable")
def test_les_trois_ordres_arrivent_jusqu_au_contexte():
    """⚠️ `lire_tous` PEUT ETRE JUSTE ET N'ETRE APPELE NULLE PART.

    C'est le defaut que le Model Router a corrige, et il s'est represente
    ici : debrancher `/v1/action` de `lire_tous` laissait tous les bancs de ce
    fichier verts, parce qu'aucun ne passait par le point d'entree.

    Ce banc dit ce que la personne ENTEND : les trois ordres, dans une seule
    reponse.
    """
    from fastapi.testclient import TestClient

    from nova.api.app import app
    from nova.db import connection

    with connection() as conn:
        conn.execute("UPDATE projets SET actif = false WHERE actif")
    try:
        dit = TestClient(app).post("/v1/action", json={"texte": BLOC}).json()
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM projets WHERE nom = 'centrale nucléaire'")

    assert dit["etat"] == "executee", dit["message"]
    assert "C'est ouvert : centrale nucléaire." in dit["message"]
    assert "Objectif noté" in dit["message"], "l'objectif s'est perdu en route"
    assert "Décision notée" in dit["message"], "la décision s'est perdue en route"
