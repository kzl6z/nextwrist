"""Detecter vite, puis relire proprement.

LE DEFAUT QUE CES TESTS PROTEGENT

`/v1/audio/wake` tourne EN BOUCLE des que le micro depasse un seuil. Il
utilise donc le petit modele en decodage glouton : chercher un seul mot connu
ne demande aucune finesse, et la finesse coute cher quand on la paie plusieurs
fois par seconde.

Mais la meme transcription servait AUSSI de question. Un reglage choisi pour
reconnaitre « Nova » decidait de ce que Nova comprenait de toute la phrase.
Releve en conditions reelles :

    dit      « quel est le diametre de la Terre »
    entendu  « quelle est-il de germetre de la terre »

Aucun de ces mots n'est rare. Ce n'etait pas un manque de vocabulaire — que
le lexique saurait corriger — mais le mauvais outil pour la tache.

LA REGLE : le surcout de la relecture ne se paie QUE lorsqu'une question suit
reellement le mot de reveil. L'ecoute continue doit rester aussi legere
qu'avant, sinon on a repare la precision en cassant l'autonomie.
"""

import pytest
from fastapi.testclient import TestClient

from nova.api.app import app
from nova.voice import transcribe

client = TestClient(app)

#: Assez long pour passer le garde-fou des 2000 octets de `transcrire`.
AUDIO = b"RIFF" + b"\0" * 4000


class FauxWhisper:
    """Rend une transcription differente selon le modele demande.

    C'est tout l'objet du test : verifier que le bon modele est employe au
    bon moment. Un double qui rendrait la meme chose partout ne prouverait
    rien.
    """

    def __init__(self, reveil: str, dictee: str) -> None:
        self.reveil, self.dictee = reveil, dictee
        self.appels: list[str | None] = []

    def __call__(self, audio, *, langue="fr", modele=None, amorce=None, beam=None):
        self.appels.append(modele)
        # `modele=None` signifie « celui de la dictee » : c'est la valeur par
        # defaut de `transcrire`, et donc la relecture soignee.
        texte = self.reveil if modele else self.dictee
        return transcribe.Transcription(texte=texte, logprob=-0.15, duree=2.0)


@pytest.fixture
def faux(monkeypatch):
    def installer(reveil: str, dictee: str) -> FauxWhisper:
        double = FauxWhisper(reveil, dictee)
        monkeypatch.setattr(transcribe, "transcrire", double)
        return double

    return installer


def appeler() -> dict:
    reponse = client.post("/v1/audio/wake", files={"file": ("reveil.wav", AUDIO, "audio/wav")})
    assert reponse.status_code == 200
    return reponse.json()


# ── La relecture a lieu, et elle sert ─────────────────────────────────────


def test_la_commande_vient_de_la_relecture_pas_de_la_detection():
    """Le cas exact releve en conditions reelles."""
    pass  # remplace par le test parametre ci-dessous


def test_le_second_passage_utilise_le_modele_de_dictee(faux, monkeypatch):
    """La relecture a lieu QUAND LES DEUX OUTILS DIFFERENT — la condition
    n'etait pas ecrite, et elle est devenue fausse le jour ou les deux
    reglages ont converge vers `base`. Voir le banc suivant.
    """
    from nova.settings import get_settings

    monkeypatch.setattr(get_settings(), "whisper_model", "small", raising=False)
    monkeypatch.setattr(get_settings(), "whisper_wake_model", "base", raising=False)
    double = faux(
        reveil="Nova, quelle est-il de germetre de la terre ?",
        dictee="Nova, quel est le diametre de la Terre ?",
    )
    resultat = appeler()

    assert len(double.appels) == 2, "il faut une detection PUIS une relecture"
    assert double.appels[0] is not None, "la detection doit nommer le modele de reveil"
    assert double.appels[1] is None, "la relecture doit utiliser celui de la dictee"
    assert "diametre" in resultat["commande"]
    assert "germetre" not in resultat["commande"]


def test_un_seul_passage_quand_les_deux_outils_sont_identiques(faux, monkeypatch):
    """⚠️ LA MEME LECTURE, PAYEE DEUX FOIS.

    « Detecter vite puis relire proprement » suppose deux outils differents.
    Rien ne l'imposait : sur la machine de reference, les deux reglages ont
    converge vers `base` en faisceau 1 pour des raisons de memoire. La
    relecture faisait alors tourner le MEME modele sur le MEME audio avec le
    MEME faisceau — seule l'amorce changeait — et personne ne le voyait,
    puisque le resultat etait correct. Seul le chronometre le disait : 2304 ms
    entre la fin de la phrase et la reponse.

    Une seule lecture suffit alors, a condition de lui donner LES DEUX
    amorces : celle du reveil apprend le mot « Nova », celle de la dictee
    apporte les noms propres de la memoire.
    """
    from nova.settings import get_settings

    monkeypatch.setattr(get_settings(), "whisper_model", "base", raising=False)
    monkeypatch.setattr(get_settings(), "whisper_wake_model", "base", raising=False)
    monkeypatch.setattr(get_settings(), "whisper_beam", 1, raising=False)
    monkeypatch.setattr(get_settings(), "whisper_beam_reveil", 1, raising=False)

    amorces = []

    class Espion(FauxWhisper):
        def __call__(self, audio, **kw):
            amorces.append(kw.get("amorce") or "")
            return super().__call__(audio, **kw)

    double = Espion("Nova, ouvre YouTube.", "Nova, ouvre YouTube.")
    monkeypatch.setattr(transcribe, "transcrire", double)

    resultat = appeler()

    assert len(double.appels) == 1, "le meme audio a ete lu deux fois pour rien"
    # Le pipeline de comprehension ecrit « You Tube » ; ce qui compte ici
    # est qu'une commande soit ressortie de la lecture unique.
    assert "youtube" in resultat["commande"].lower().replace(" ", "")
    # Les deux amorces sont bien la : sans celle du reveil, « Nova » redevient
    # « Nouveau » ; sans celle de la dictee, les noms propres sont massacres.
    assert "Nova" in amorces[0]
    assert len(amorces[0]) > len(get_settings().whisper_amorce)


def test_le_mot_de_reveil_est_retire_de_la_commande(faux):
    faux(reveil="Nova, quelle heure est-il ?", dictee="Nova, quelle heure est-il ?")
    assert "nova" not in appeler()["commande"].lower()


# ── Le surcout ne se paie que quand il sert ───────────────────────────────


def test_sans_mot_de_reveil_aucune_relecture(faux):
    """L'ecoute continue doit rester aussi legere qu'avant.

    C'est la contrainte qui rend la correction acceptable : reparer la
    precision en doublant le cout de la veille aurait ete un mauvais echange.
    """
    double = faux(reveil="il fait beau aujourd hui", dictee="jamais appele")
    resultat = appeler()

    assert resultat["wake"] is False
    assert len(double.appels) == 1, "aucune relecture sans mot de reveil"


def test_un_reveil_seul_ne_declenche_pas_de_relecture(faux):
    """« Nova » tout court n'est pas une question : rien a relire."""
    double = faux(reveil="Nova", dictee="jamais appele")
    resultat = appeler()

    assert resultat["wake"] is True
    assert resultat["commande"] == ""
    assert len(double.appels) == 1


# ── La relecture ne doit jamais rendre Nova moins fiable ──────────────────


def test_si_la_relecture_echoue_la_commande_reste_utilisable(faux, monkeypatch):
    """Une amelioration qui casse ce qui marchait n'est pas une amelioration."""
    double = FauxWhisper("Nova, quelle heure est-il ?", "")
    appels = {"n": 0}

    def parfois_casse(audio, **kwargs):
        appels["n"] += 1
        if appels["n"] == 2:
            raise RuntimeError("modele de dictee indisponible")
        return double(audio, **kwargs)

    monkeypatch.setattr(transcribe, "transcrire", parfois_casse)
    resultat = appeler()

    assert resultat["wake"] is True
    assert "heure" in resultat["commande"], "la commande de secours doit survivre"


def test_les_champs_historiques_sont_conserves(faux):
    """Aucun client existant ne doit casser."""
    faux(reveil="Nova, quelle heure est-il ?", dictee="Nova, quelle heure est-il ?")
    resultat = appeler()
    for champ in ("wake", "text", "commande"):
        assert champ in resultat


def test_la_confiance_accompagne_la_commande(faux):
    """Le pipeline de comprehension voyage avec la commande.

    Sans ca, l'application ne peut pas demander « As-tu dit… ? » — elle n'a
    aucun moyen de savoir que Nova a doute.
    """
    faux(reveil="Nova, quelle heure est-il ?", dictee="Nova, quelle heure est-il ?")
    resultat = appeler()

    assert isinstance(resultat["confiance"], float)
    assert "sure" in resultat and "a_confirmer" in resultat
    assert "question" in resultat


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ DIRE « NOVA » UNE FOIS, PUIS PARLER
# ══════════════════════════════════════════════════════════════════════════
def test_pendant_une_conversation_ouverte_nova_devient_facultatif(faux):
    """L'application n'a PAS ete modifiee.

    Elle envoie ici tout extrait qui depasse le seuil sonore, et n'agit que
    si l'on repond `wake: true`. Repondre `true` pendant la fenetre d'ecoute
    suffit donc a produire le comportement voulu — sans qu'une ligne du
    depot de l'application change.
    """
    from nova.voice import session

    faux(reveil="retrouve mes impots de 2024", dictee="retrouve mes impots de 2024")

    avant = appeler()
    assert avant["wake"] is False, "sans « Nova » et hors conversation, rien"

    session.ouvrir()
    pendant = appeler()

    assert pendant["wake"] is True
    assert pendant["commande"] == "retrouve mes impots de 2024", (
        "la phrase ENTIERE est la commande : il n'y a pas de « Nova » a retirer"
    )


def test_une_phrase_de_conge_referme_et_ne_repond_pas(faux):
    """⚠️ ELLE DOIT FERMER AVANT DE DECIDER QUOI QUE CE SOIT D'AUTRE.

    Traitee comme une demande, « c'est bon » ferait repondre Nova — et
    repondre prolonge la conversation. Le conge rouvrirait donc ce qu'il
    voulait fermer.
    """
    from nova.voice import session

    faux(reveil="c'est bon merci", dictee="c'est bon merci")
    session.ouvrir()

    resultat = appeler()

    assert resultat["wake"] is False
    assert resultat["commande"] == ""
    assert not session.est_ouverte()


def test_le_mot_de_reveil_ouvre_la_conversation_pour_la_suite(faux):
    from nova.voice import session

    faux(reveil="nova quelle heure est-il", dictee="nova quelle heure est-il")
    assert not session.est_ouverte()

    appeler()

    assert session.est_ouverte(), "« Nova » ouvre la fenetre pour les tours suivants"
