"""Penser a voix haute devant Nova sans qu'elle reponde.

LE DEFAUT, RELEVE PAR CONCEPTION

Pendant une conversation ouverte, « Nova » devient facultatif : tout ce qui
depasse le seuil sonore part comme une demande. C'est ce qui rend la
conversation naturelle — et c'est aussi ce qui faisait repondre Nova quand on
reflechissait tout haut.

    « bon… il faudrait que je revoie le refroidissement »
    Nova : « Le refroidissement d'un moteur electrique repose sur… »

Personne n'avait rien demande.

⚠️ CE FICHIER PROTEGE SURTOUT CE QUI DOIT CONTINUER DE PASSER.

Ne pas repondre a un ordre est une regression : ca casse ce qui marchait.
La moitie des bancs ci-dessous ne verifie donc pas le silence mais son
CONTRAIRE — qu'un ordre ordinaire, un « oui » a une proposition, un conge,
traversent exactement comme avant.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nova.api.app import app
from nova.voice import adresse, session, transcribe

client = TestClient(app)

#: Assez long pour passer le garde-fou des 2000 octets de `transcrire`.
AUDIO = b"RIFF" + b"\0" * 4000

PENSEE = "bon, il faudrait que je revoie le refroidissement"


@pytest.fixture(autouse=True)
def _propre():
    session.oublier()
    yield
    session.oublier()


@pytest.fixture
def entendu(monkeypatch):
    """Fait entendre a Nova la phrase voulue, sans micro ni modele."""

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
#  CE QUI EST UNE PENSEE
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "phrase",
    [
        PENSEE,
        "il faudrait que je revoie le refroidissement",
        "faut que j'appelle le plombier",
        "va falloir que je repense tout ca",
        "je devrais relire le contrat avant lundi",
        "je dois passer a la banque demain",
        "je vais commencer par le moteur",
        "je pourrais peut-etre inverser les deux etapes",
        "je ferais mieux de recommencer",
        "je me disais que c'etait un peu court",
        "note a moi meme, verifier la garantie",
    ],
)
def test_deliberer_sur_sa_propre_action_n_est_pas_une_demande(phrase):
    assert adresse.pense_tout_haut(phrase), phrase


@pytest.mark.parametrize("phrase", ["bon", "hmm", "euh", "ben", "bon alors", "hmm donc", "bref"])
def test_une_phrase_faite_d_hesitation_ne_demande_rien(phrase):
    """Meme famille que le silence transcrit en « … » : rien a exaucer, et le
    modele en fera quand meme quelque chose."""
    assert adresse.pense_tout_haut(phrase), phrase


# ══════════════════════════════════════════════════════════════════════════
#  CE QUI N'EN EST PAS — la moitie qui protege l'existant
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "phrase",
    [
        "ouvre le deuxieme fichier",
        "retrouve mes impots de 2024",
        "quelle heure est-il",
        "montre-moi la photo de la casquette",
        "peux-tu tous les ouvrir",
        "ferme les fichiers",
        "ajoute ca aux prochaines etapes",
        "qu'est-ce qu'un trou noir",
    ],
)
def test_un_ordre_ordinaire_traverse(phrase):
    assert not adresse.pense_tout_haut(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ CES DEUX TOURNURES ETAIENT DANS MA PREMIERE LISTE.
        #
        # « j'ai besoin de » et « je me demande » ressemblent a de la
        # deliberation, et sont des demandes parfaitement ordinaires. Les
        # faire taire aurait casse ce qui marchait pour corriger un defaut
        # qui n'aurait meme pas ete celui-la.
        "j'ai besoin de mes impots de 2024",
        "je me demande quelle heure il est",
        "je cherche la photo de la casquette",
        "je veux voir ma carte d'identite",
    ],
)
def test_une_demande_a_la_premiere_personne_reste_une_demande(phrase):
    assert not adresse.pense_tout_haut(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # Le nom : ignorer quelqu'un qui vous appelle par votre nom.
        "nova, il faudrait que je revoie le refroidissement",
        # La deuxieme personne : la phrase designe Nova comme agent.
        "tu peux me rappeler qu'il faudrait que je revoie ca",
        "rappelle-toi que je dois passer a la banque",
        # L'interrogative : la question est posee a quelqu'un, meme si son
        # sujet grammatical est « je ».
        "qu'est-ce que je devrais faire maintenant",
        "pourquoi je devrais changer de moteur",
    ],
)
def test_une_marque_d_adresse_l_emporte_sur_la_deliberation(phrase):
    assert not adresse.pense_tout_haut(phrase), phrase


@pytest.mark.parametrize(
    "mot",
    [
        # ⚠️ CES MOTS-LA ONT DEJA UN SENS AILLEURS, ET LE PERDRAIENT ICI.
        #
        # « ok », « ouais », « vas y », « bien sur » sont ceux de
        # `session._ACCORD` : quand Nova vient de proposer « je te l'ouvre ? »,
        # ils valent OUI. Les ranger dans le remplissage rendrait toute
        # proposition inacceptable — le « ok » repondrait au vide.
        "ok",
        "ouais",
        "vas-y",
        "bien sur",
        "voila",
        # Un conge doit refermer la fenetre, pas etre avale comme une pensee.
        "c'est bon",
        # Et « attends » est une interruption, pas une hesitation.
        "attends",
        # « alors ? » apres une reponse veut souvent dire « et ensuite ? ».
        "alors",
        "donc",
    ],
)
def test_les_mots_qui_ont_deja_un_sens_ne_sont_pas_du_remplissage(mot):
    assert not adresse.hesitation_seule(mot), mot
    assert not adresse.pense_tout_haut(mot), mot


def test_une_phrase_vide_n_est_pas_une_pensee():
    """Le silence est deja filtre en amont, dans `transcribe`. Rendre VRAI ici
    ferait porter la meme decision a deux endroits."""
    assert not adresse.pense_tout_haut("")
    assert not adresse.hesitation_seule("")


# ══════════════════════════════════════════════════════════════════════════
#  LE JOURNAL
# ══════════════════════════════════════════════════════════════════════════


def test_chaque_decision_est_explicable():
    """⚠️ UN SILENCE SANS EXPLICATION EST INDISTINGUABLE D'UNE PANNE.

    On chercherait pourquoi Nova « ne repond plus » alors qu'elle se retient.
    """
    assert adresse.raison(PENSEE) == "delibere sur sa propre action"
    assert adresse.raison("hmm") == "hesitation sans contenu"
    assert adresse.raison("nova, il faudrait que je dorme") == "s'adresse a Nova"
    assert adresse.raison("ouvre le deuxieme") == "demande ordinaire"
    assert adresse.raison("") == "phrase vide"


# ══════════════════════════════════════════════════════════════════════════
#  LE CABLAGE
#
#  ⚠️ SANS CES BANCS, LE MODULE POURRAIT ETRE JUSTE ET N'ETRE APPELE NULLE
#     PART — le defaut exact que le Model Router a corrige.
# ══════════════════════════════════════════════════════════════════════════


def test_une_pensee_ne_reveille_pas_nova(entendu):
    """Le cas de conception, de bout en bout."""
    session.ouvrir()
    entendu(PENSEE)

    reponse = appeler()

    assert reponse["wake"] is False, "Nova a coupe la parole"
    assert reponse["commande"] == ""
    assert reponse["text"] == PENSEE, "la phrase doit rester lisible dans la reponse"


def test_un_ordre_pendant_la_conversation_reveille_toujours(entendu):
    """⚠️ LA REGRESSION QUI COUTERAIT LE PLUS CHER.

    Se taire sur un ordre casse ce qui marchait. C'est pour cela que le
    silence demande un signal positif, et que le defaut est « c'est pour
    moi ».
    """
    session.ouvrir()
    entendu("ouvre le deuxieme fichier")

    reponse = appeler()

    assert reponse["wake"] is True
    assert reponse["commande"] == "ouvre le deuxieme fichier"


def test_la_meme_pensee_precedee_du_nom_reveille(entendu):
    session.ouvrir()
    entendu("Nova, il faudrait que je revoie le refroidissement")

    assert appeler()["wake"] is True


def test_la_pensee_devient_l_antecedent_de_ca(entendu):
    """⚠️ SE TAIRE NE VEUT PAS DIRE NE PAS ECOUTER.

    C'est toute la difference avec jeter la phrase. « ajoute ca aux
    prochaines etapes », juste apres, doit savoir de quoi il parle.
    """
    session.ouvrir()
    entendu(PENSEE)

    appeler()

    assert session.propos_precedent() == PENSEE


def test_une_pensee_ne_consomme_pas_la_proposition_en_attente(entendu):
    """Nova vient de demander « je te l'ouvre ? ». Penser tout haut entre les
    deux ne doit pas faire disparaitre la question."""
    session.ouvrir()
    session.proposer("ouvrir_fichier", {"chemin": "/tmp/x.pdf"}, comme="tes impots")
    entendu(PENSEE)

    appeler()

    assert session.en_attente() == ("ouvrir_fichier", {"chemin": "/tmp/x.pdf"})


def test_un_conge_referme_toujours_la_fenetre(entendu):
    """Le conge est teste AVANT la pensee, et doit le rester : « c'est bon »
    ne s'ecoute pas, il coupe."""
    session.ouvrir()
    entendu("c'est bon merci")

    assert appeler()["wake"] is False
    assert not session.est_ouverte(), "la fenetre est restee ouverte sur un conge"


def test_reveil_sans_question(entendu):
    """« Nova, euh… » : le nom a ete dit, la fenetre s'ouvre, et rien ne part
    au modele — qui repondrait quelque chose, comme toujours."""
    entendu("Nova, euh")

    reponse = appeler()

    assert reponse["wake"] is True
    assert reponse["commande"] == ""
    assert session.est_ouverte()
