"""Dire « Nova » une fois, puis parler — et « oui » suffit pour ouvrir.

CE QUE CE BANC PROTEGE

    « Nova, retrouve mes impots de 2024 »
    « C'est bon, je l'ai trouve : impots 2024.pdf. Je te l'ouvre ? »
    « oui »
    → le fichier s'ouvre

Deux tours sans repeter le nom, et une action declenchee par un mot.

⚠️ ET IL PROTEGE SURTOUT CE QUI DOIT RESTER FERME.

Pendant la fenetre d'ecoute, TOUT ce qui depasse le seuil sonore part a
Nova. Trois choses la bornent, et chacune a son banc : elle ne s'ouvre
jamais seule, elle se referme au silence, et une phrase de conge la coupe.
"""

from __future__ import annotations

import pytest

from nova.voice import session


@pytest.fixture(autouse=True)
def _propre():
    session.oublier()
    yield
    session.oublier()


# ══════════════════════════════════════════════════════════════════════════
#  LA FENETRE D'ECOUTE
# ══════════════════════════════════════════════════════════════════════════
def test_rien_n_est_ouvert_au_depart():
    """⚠️ ELLE NE S'OUVRE JAMAIS TOUTE SEULE.

    C'est la premiere des trois conditions qui rendent une fenetre d'ecoute
    acceptable. Sans « Nova », Nova n'ecoute pas.
    """
    assert not session.est_ouverte()
    assert session.restant() == 0.0


def test_le_mot_de_reveil_ouvre_la_conversation():
    session.ouvrir()

    assert session.est_ouverte()
    assert 0 < session.restant() <= session.DUREE_S


def test_la_fenetre_se_referme_au_silence(monkeypatch):
    session.ouvrir()
    monkeypatch.setattr(session, "DUREE_S", -1.0)
    session.ouvrir()

    assert not session.est_ouverte()


def test_chaque_echange_repousse_la_fermeture(monkeypatch):
    """⚠️ DEPUIS LE DERNIER ECHANGE, PAS DEPUIS LE REVEIL.

    Nova met plusieurs secondes a DIRE sa reponse, et l'on enchaine juste
    apres. Une fenetre comptee depuis « Nova » se refermerait pendant qu'elle
    parle.
    """
    faux_temps = [1000.0]
    monkeypatch.setattr(session.time, "monotonic", lambda: faux_temps[0])

    session.ouvrir()
    faux_temps[0] += session.DUREE_S - 1
    assert session.est_ouverte(), "encore ouverte juste avant l'echeance"

    session.prolonger()
    faux_temps[0] += session.DUREE_S - 1

    assert session.est_ouverte(), "l'echange a repousse l'echeance"


def test_prolonger_ne_ranime_pas_une_conversation_fermee(monkeypatch):
    """⚠️ SANS CETTE GARDE, UNE REPONSE TARDIVE ROUVRIRAIT LE MICRO.

    La synthese vocale, un outil lent : une reponse peut arriver apres que le
    silence a referme la fenetre. La prolonger reviendrait a rouvrir une
    ecoute que personne n'a redemandee.
    """
    faux_temps = [1000.0]
    monkeypatch.setattr(session.time, "monotonic", lambda: faux_temps[0])

    session.ouvrir()
    faux_temps[0] += session.DUREE_S + 1
    assert not session.est_ouverte()

    session.prolonger()

    assert not session.est_ouverte()


# ══════════════════════════════════════════════════════════════════════════
#  LE CONGE
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "c'est bon",
        "c'est bon merci",
        "mets-toi en veille",
        "c'est tout",
        "laisse tomber",
        "bonne nuit",
        "merci Nova",
        "ça suffit",
    ],
)
def test_une_phrase_de_conge_referme_la_conversation(phrase):
    session.ouvrir()

    assert session.demande_de_veille(phrase), phrase

    session.fermer()
    assert not session.est_ouverte()


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ « MERCI » SEUL APPARAIT AU MILIEU D'UNE DEMANDE.
        #
        # « merci de m'ouvrir ça » n'est pas un conge. Le prendre pour tel
        # couperait la conversation au pire moment.
        "merci de m'ouvrir ça",
        "c'est bon pour toi si je te demande autre chose",
        "retrouve mes impôts",
        "ouvre le deuxième",
        "oui",
    ],
)
def test_ce_qui_n_est_pas_un_conge(phrase):
    assert not session.demande_de_veille(phrase), phrase


# ══════════════════════════════════════════════════════════════════════════
#  LA PROPOSITION — « je te l'ouvre ? » « oui »
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase", ["oui", "ouais", "vas-y", "d'accord", "ok", "je veux bien", "fais-le"]
)
def test_un_accord_declenche_la_proposition(phrase):
    session.proposer("ouvrir_fichier", {"chemin": "/h/impots.pdf"})

    assert session.accord(phrase) == ("ouvrir_fichier", {"chemin": "/h/impots.pdf"})


@pytest.mark.parametrize("phrase", ["non", "non merci", "pas la peine", "surtout pas"])
def test_un_refus_efface_la_proposition(phrase):
    session.proposer("ouvrir_fichier", {"chemin": "/h/impots.pdf"})

    assert session.accord(phrase) is None
    assert session.en_attente() is None, "un refus efface, il ne laisse pas trainer"


def test_un_oui_ne_vaut_qu_une_fois():
    """⚠️ SANS CELA, UN SECOND « OUI » REJOUERAIT L'ACTION.

    Ou pire : un « oui » qui repond a tout autre chose, deux tours plus tard,
    ouvrirait un fichier dont plus personne ne parle.
    """
    session.proposer("ouvrir_fichier", {"chemin": "/h/impots.pdf"})

    assert session.accord("oui") is not None
    assert session.accord("oui") is None


def test_un_oui_nu_ne_fait_rien_sans_proposition():
    """⚠️ C'EST CE QUI REND CETTE LISTE DE MOTS ACCEPTABLE.

    « oui », « ok », « vas-y » sont trop generiques pour declencher quoi que
    ce soit dans l'absolu. Ils ne valent que parce qu'une question vient
    d'etre posee.
    """
    assert session.accord("oui") is None
    assert session.accord("vas-y") is None


def test_une_phrase_qui_n_est_ni_oui_ni_non_laisse_la_proposition():
    """On peut repondre a cote sans perdre la proposition — « attends », « et
    le deuxieme ? ». Elle mourra avec la conversation, pas avant."""
    session.proposer("ouvrir_fichier", {"chemin": "/h/impots.pdf"})

    assert session.accord("et le deuxième ?") is None
    assert session.en_attente() is not None


def test_fermer_la_conversation_efface_la_proposition():
    session.proposer("ouvrir_fichier", {"chemin": "/h/impots.pdf"})
    session.fermer()

    assert session.en_attente() is None


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ UN CONGE NE REVEILLE JAMAIS
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        # Releve en conditions reelles, sur un simple bruit :
        #     [reveil] 1536 ms → « Oh! »  →  enchaine sur : « Au revoir. »
        #     Nova : « Au revoir. Le temps est calme… »
        # « au revoir » figure dans `wake.VARIANTES_DEBUT` : Whisper, ne
        # connaissant pas « Nova », le rend parfois ainsi.
        "Au revoir.",
        "c'est bon, tu peux t'éteindre",
        "c'est bon tu peux te mettre en veille",
        "éteins-toi",
        "j'ai fini",
        "merci Nova",
        "ok c'est bon",
        "c'est tout, merci",
    ],
)
def test_les_congés_reellement_prononces_sont_reconnus(phrase):
    assert session.demande_de_veille(phrase), phrase


def test_un_conge_ferme_meme_hors_conversation():
    """Dire au revoir ne peut pas etre une facon de dire bonjour."""
    assert not session.est_ouverte()

    assert session.demande_de_veille("au revoir")

    session.fermer()
    assert not session.est_ouverte()


@pytest.mark.parametrize(
    "phrase",
    [
        "merci de m'ouvrir ça",
        "merci beaucoup pour ton aide sur les impôts",
        "retrouve mes impôts",
        "ouvre le deuxième",
        "oui",
    ],
)
def test_ce_qui_n_est_toujours_pas_un_conge(phrase):
    assert not session.demande_de_veille(phrase), phrase
