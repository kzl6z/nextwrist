"""Couper Nova pendant qu'elle parle.

LE DEFAUT

Une reponse partie etait une reponse qu'on subissait jusqu'au bout. Nova lit
sa phrase, on voit des la premiere seconde qu'elle a mal compris, et il ne
reste qu'a attendre — puis a tout reformuler par-dessus.

    « quelle est la carte la plus rare, Pokemon ? »
    « Je ne trouve pas de CARTE BLANCHE correspondant a un SKATE… »
    « attends — »
    « …les cartes de skate se collectionnent depuis les annees 1990, et… »

⚠️ CE QUI EST TESTE ICI N'EST PAS « LE SON S'ARRETE ».

Le haut-parleur appartient a l'application de bureau : elle joue les phrases
une a une, en demandant chaque synthese a Nova Core pendant que le modele
ecrit les suivantes. Nova Core ne peut pas couper le son en cours.

Ce qu'elle tient, et ce que ces bancs verifient :

    la generation s'arrete           → la machine est rendue tout de suite
    la synthese suivante est muette  → Nova se tait a la phrase d'apres
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nova.api.app import app
from nova.voice import interruption, session, transcribe

client = TestClient(app)

AUDIO = b"RIFF" + b"\0" * 4000


@pytest.fixture(autouse=True)
def _propre():
    session.oublier()
    interruption.oublier()
    yield
    session.oublier()
    interruption.oublier()


@pytest.fixture
def entendu(monkeypatch):
    def installer(texte: str):
        def transcrire(audio, *, langue="fr", modele=None, amorce=None, beam=None):
            return transcribe.Transcription(texte=texte, logprob=-0.15, duree=2.0)

        monkeypatch.setattr(transcribe, "transcrire", transcrire)

    return installer


def appeler() -> dict:
    reponse = client.post("/v1/audio/wake", files={"file": ("x.wav", AUDIO, "audio/wav")})
    assert reponse.status_code == 200
    return reponse.json()


# ══════════════════════════════════════════════════════════════════════════
#  RECONNAITRE
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "phrase",
    [
        "attends",
        "attends attends",
        "attend",  # Whisper ecrit souvent la troisieme personne
        "attendez",
        "stop",
        "chut",
        "tais-toi",
        "arrete",
        "arrete-toi",
        "arrete de parler",
        "silence",
        "une seconde",
        "ca suffit",
        "nova, stop",
        "non attends",
    ],
)
def test_ces_phrases_coupent_la_parole(phrase):
    assert interruption.demande_d_interruption(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ LE PIEGE QUI A DECIDE DE LA CONCEPTION.
        #
        # « arrete » prend un complement. Le traiter comme un prefixe
        # d'interruption ferait de cette phrase la commande « la musique » —
        # qui ne veut plus rien dire, et qui partirait quand meme au modele.
        "arrete la musique",
        "arrete le minuteur",
        "arrete de chercher ce fichier",
        # Une demande ordinaire ne coupe rien.
        "ouvre le deuxieme fichier",
        "quelle heure est-il",
        "retrouve mes impots de 2024",
        # Ni un accord, ni un refus : ils repondent a une proposition.
        "oui",
        "non",
        "ok",
        "",
    ],
)
def test_ces_phrases_ne_coupent_rien(phrase):
    assert not interruption.demande_d_interruption(phrase), phrase


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        # ⚠️ ON COUPE PARCE QU'ON A QUELQUE CHOSE A DIRE.
        #
        # Jeter la suite obligerait a la repeter, ce qui rendrait
        # l'interruption plus couteuse que d'attendre la fin — et personne ne
        # s'en servirait.
        ("attends, ouvre plutot le deuxieme", "ouvre plutot le deuxieme"),
        ("attends non je voulais la photo", "non je voulais la photo"),
        ("une seconde, retrouve mes impots", "retrouve mes impots"),
        # Rien derriere : rien a faire.
        ("attends", ""),
        ("attends attends", ""),
        ("attends nova", ""),
        ("attends, euh", ""),
        # ⚠️ « arrete » NE LAISSE JAMAIS DE RESTE : ce n'est pas un prefixe.
        ("arrete la musique", ""),
        ("stop", ""),
    ],
)
def test_ce_qui_suit_l_interruption_reste_une_demande(phrase, attendu):
    assert interruption.reste_apres(phrase) == attendu


# ══════════════════════════════════════════════════════════════════════════
#  L'ETAT
# ══════════════════════════════════════════════════════════════════════════


def test_au_depart_nova_a_le_droit_de_parler():
    assert not interruption.interrompue()


def test_interrompre_puis_reprendre():
    interruption.interrompre("attends")

    assert interruption.interrompue()
    assert interruption.raison() == "attends"

    interruption.reprendre()

    assert not interruption.interrompue()
    assert interruption.raison() == ""


# ══════════════════════════════════════════════════════════════════════════
#  LE POINT D'ENTREE VOCAL
# ══════════════════════════════════════════════════════════════════════════


def test_une_interruption_ne_reveille_pas_et_fait_taire(entendu):
    session.ouvrir()
    entendu("attends")

    reponse = appeler()

    assert reponse["wake"] is False
    assert reponse["commande"] == ""
    assert interruption.interrompue()


def test_interrompre_ne_referme_pas_la_conversation(entendu):
    """⚠️ CE N'EST PAS UN CONGE, ET C'EST TOUTE LA DIFFERENCE.

    On coupe precisement parce qu'on a quelque chose a dire. Raccrocher
    obligerait a redire « Nova » juste apres.
    """
    session.ouvrir()
    entendu("attends")

    appeler()

    assert session.est_ouverte()


def test_la_demande_qui_suit_l_interruption_part_quand_meme(entendu):
    session.ouvrir()
    entendu("attends, ouvre plutot le deuxieme")

    reponse = appeler()

    assert reponse["wake"] is True
    assert reponse["commande"] == "ouvre plutot le deuxieme"
    assert interruption.interrompue(), "la parole en cours n'a pas ete coupee"


def test_un_conge_passe_avant_et_raccroche(entendu):
    """« ca suffit » coupe ET referme. Le conge est teste en premier, et doit
    le rester : sinon l'interruption garderait la fenetre ouverte."""
    session.ouvrir()
    entendu("ca suffit")

    assert appeler()["wake"] is False
    assert not session.est_ouverte()


# ══════════════════════════════════════════════════════════════════════════
#  LA SYNTHESE — le seul endroit ou Nova Core peut faire taire Nova
# ══════════════════════════════════════════════════════════════════════════


def test_la_phrase_suivante_est_muette_apres_une_interruption(monkeypatch):
    from nova.voice import synthese

    def jamais(*a, **k):
        raise AssertionError("la synthese a tourne alors que Nova etait interrompue")

    monkeypatch.setattr(synthese, "synthetiser", jamais)
    interruption.interrompre("attends")

    reponse = client.post("/v1/audio/speech", json={"input": "la suite de ma phrase"})

    assert reponse.status_code == 200, "un silence voulu ne doit pas ressembler a une panne"
    assert reponse.headers["content-type"].startswith("audio/wav")
    assert reponse.content == synthese.silence()


def test_le_silence_est_un_wav_valide():
    """⚠️ UNE ERREUR FERAIT PASSER UN SILENCE VOULU POUR UN DEFAUT.

    L'application a un precedent : le jour ou la synthese distante a echoue,
    elle est repassee a la voix du systeme, masculine et anglophone, sans
    rien dire. Un WAV valide et muet ne peut pas declencher ce repli.
    """
    import io
    import wave

    from nova.voice import synthese

    with wave.open(io.BytesIO(synthese.silence()), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getframerate() == synthese.ECHANTILLONNAGE
        assert f.getnframes() > 0
        assert set(f.readframes(f.getnframes())) == {0}


def test_sans_interruption_la_synthese_a_lieu(monkeypatch):
    """La regression qui couterait le plus cher : Nova muette pour toujours."""
    from nova.voice import synthese

    monkeypatch.setattr(synthese, "synthetiser", lambda *a, **k: b"RIFFvraie voix")

    reponse = client.post("/v1/audio/speech", json={"input": "bonjour"})

    assert reponse.content == b"RIFFvraie voix"


# ══════════════════════════════════════════════════════════════════════════
#  LA GENERATION — rendre la machine, pas seulement se taire
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def modele_bavard(monkeypatch):
    """Un modele qui produit dix morceaux, et compte ceux qu'on lui prend."""
    from nova import orchestrator

    produits: list[str] = []

    def flux(usage, messages, **kwargs):
        for i in range(10):
            produits.append(f"m{i}")
            yield f"m{i} "

    monkeypatch.setattr(orchestrator.routage, "flux", flux)
    monkeypatch.setattr(orchestrator, "build_system_prompt", lambda *a, **k: ("SYS", []))
    monkeypatch.setattr(orchestrator.conversations, "get_or_create", lambda *a, **k: 1)
    monkeypatch.setattr(orchestrator.conversations, "log_message", lambda *a, **k: None)
    return produits


def test_interrompre_arrete_la_generation(modele_bavard):
    """⚠️ SUR 8 GO, SE TAIRE NE SUFFIT PAS.

    Une reponse de trois cents mots que personne n'ecoutera occupe le modele
    pendant que la question suivante attend. Couper la generation rend la
    machine tout de suite.
    """
    from nova import orchestrator

    morceaux = []
    for morceau in orchestrator.answer_stream([{"role": "user", "content": "raconte"}]):
        morceaux.append(morceau)
        if len(morceaux) == 2:
            interruption.interrompre("attends")

    assert len(morceaux) < 10, "la generation est allee au bout malgre l'interruption"
    assert len(modele_bavard) < 10, "le modele a continue de produire dans le vide"


def test_sans_interruption_la_reponse_va_au_bout(modele_bavard):
    from nova import orchestrator

    morceaux = list(orchestrator.answer_stream([{"role": "user", "content": "raconte"}]))

    assert len(morceaux) == 10


def test_le_premier_mot_de_la_reponse_suivante_leve_le_silence(modele_bavard):
    """⚠️ LE SILENCE SE LEVE AU PREMIER MOT PRODUIT, PAS A L'ARRIVEE DE LA
    QUESTION.

    Entre « attends » et la reponse suivante, l'application peut encore
    demander la synthese des phrases qu'elle avait en attente. Lever le
    silence plus tot les laisserait passer : on entendrait la fin de la
    reponse qu'on venait de couper, apres avoir parle.

    ⚠️ CE BANC N'OBSERVAIT D'ABORD RIEN DU TOUT.

    Il appelait `answer_stream` puis verifiait le drapeau avant le premier
    `next`. Or `answer_stream` est un GENERATEUR : rien de son corps ne
    s'execute a l'appel. Deplacer la levee tout en haut de la fonction le
    laissait vert — le banc mesurait la paresse de Python, pas l'ordre du
    code.

    On observe donc le drapeau PENDANT la construction du prompt, qui est
    justement la phase longue — memoire, documents, contexte — et donc la
    fenetre exacte ou l'application vide sa file.
    """
    from nova import orchestrator

    vu: list[bool] = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        orchestrator,
        "build_system_prompt",
        lambda *a, **k: (vu.append(interruption.interrompue()), ("SYS", []))[1],
    )
    try:
        interruption.interrompre("attends")
        flux = orchestrator.answer_stream([{"role": "user", "content": "et donc ?"}])

        next(flux)

        assert vu == [True], "le silence est tombe pendant que le prompt se construisait"
        assert not interruption.interrompue(), "le premier mot n'a pas rendu la parole"
        flux.close()
    finally:
        monkeypatch.undo()


def test_une_action_rend_la_parole_a_nova(monkeypatch):
    """« attends, ouvre plutot le deuxieme » coupe PUIS agit. Sans levee, la
    confirmation serait prononcee en silence et Nova paraitrait n'avoir rien
    fait."""
    interruption.interrompre("attends")

    reponse = client.post("/v1/action", json={"texte": "quelle heure est-il"})

    assert reponse.status_code == 200
    assert reponse.json()["message"], "ce banc suppose une reponse qui se prononce"
    assert not interruption.interrompue()
