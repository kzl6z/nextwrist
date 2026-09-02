"""Piloter le contexte de travail a la voix.

⚠️ RECONNAITRE UN ORDRE EXPLICITE N'EST PAS SIMULER LA COMPREHENSION.

La consigne est nette : pas de regle « si la phrase dit "augmente ca"
alors … ». Ce module ne fait rien de tel. Il reconnait des ORDRES, que l'on
prononce pour piloter Nova — exactement la meme categorie que « souviens-toi
que… ».

Deduire seule qu'une phrase de conversation contient une decision serait
l'autre chose, celle qu'on ne fait pas : au bout d'un an, un contexte devine
et faux vaut moins que pas de contexte du tout.
"""

from __future__ import annotations

import pytest

from nova.contexte.commandes import lire


# ══════════════════════════════════════════════════════════════════════════
#  LES SIX ORDRES
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("phrase", "genre", "contenu"),
    [
        ("ouvre le projet moteur", "ouvrir", "moteur"),
        ("on travaille sur le projet NOVA", "ouvrir", "NOVA"),
        ("lance le projet prototype", "ouvrir", "prototype"),
        ("revenons au projet NOVA", "basculer", "NOVA"),
        ("reprenons le projet moteur", "basculer", "moteur"),
        ("on va essayer de gagner 15 % de puissance", "objectif", "gagner 15 % de puissance"),
        ("l'objectif c'est de finir en juin", "objectif", "de finir en juin"),
        ("ajoute une tâche revoir le refroidissement", "tache", "revoir le refroidissement"),
        ("il faudra revoir le refroidissement", "tache", "revoir le refroidissement"),
        ("on a décidé d'augmenter le débit", "decision", "augmenter le débit"),
        ("on part sur la version locale", "decision", "la version locale"),
    ],
)
def test_un_ordre_de_contexte_se_reconnait(phrase, genre, contenu):
    ordre = lire(phrase)

    assert ordre is not None, phrase
    assert ordre.genre == genre
    assert ordre.contenu == contenu


def test_la_confidentialite_se_dit_de_plusieurs_facons():
    for phrase in (
        "je veux garder ça pour moi",
        "c'est personnel",
        "ne le partage pas",
        "ça reste entre nous",
    ):
        ordre = lire(phrase)
        assert ordre is not None and ordre.genre == "confidentiel", phrase


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ CE QUI N'EST PAS UN ORDRE — LA GARDE QUI REND LE RESTE ACCEPTABLE
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ UNE PHRASE QUI PARLE D'UN PROJET N'ORDONNE PAS DE L'OUVRIR.
        #
        # La premiere version rendait le verbe FACULTATIF — une alternative
        # vide dans le motif. Toute phrase contenant « projet X » basculait
        # donc le contexte :
        #
        #     « c'est quoi le projet moteur ? »  → ouvrait le projet
        #     « le projet moteur avance bien »   → ouvrait « moteur avance bien »
        #
        # Trois questions, trois changements de sujet. Un assistant qui change
        # de contexte parce qu'on a prononce un nom est pire qu'un assistant
        # qui n'en change jamais : on ne sait plus ou l'on est.
        "c'est quoi le projet moteur ?",
        "le projet moteur avance bien",
        "parle-moi du projet moteur",
        "j'aime bien ce projet",
        # Ce qui appartient a d'autres etages, et doit y rester.
        "ouvre Chrome",
        "quelle heure est-il",
        "retrouve mes impôts de 2024",
        "souviens-toi que mon projet s'appelle NOVA",
        "",
    ],
)
def test_ce_qui_n_est_pas_un_ordre_de_contexte(phrase):
    assert lire(phrase) is None, phrase


# ══════════════════════════════════════════════════════════════════════════
#  « CA » SE RESOUT PAR LA PHRASE D'AVANT
# ══════════════════════════════════════════════════════════════════════════
def test_ajoute_ca_prend_le_propos_precedent():
    """⚠️ « ajoute ca aux prochaines etapes » NE PORTE PAS SON CONTENU.

    Dans une conversation, « ca » designe ce qu'on vient de dire. Sans cette
    memoire d'une phrase, l'ordre est compris et vide.
    """
    ordre = lire(
        "ajoute ça aux prochaines étapes",
        propos_precedent="revoir le système de refroidissement",
    )

    assert ordre is not None
    assert ordre.genre == "tache"
    assert ordre.contenu == "revoir le système de refroidissement"


def test_ajoute_ca_sans_rien_avant_ne_note_rien():
    """⚠️ NOTER UNE CHAINE VIDE — OU PIRE, INVENTER UN INTITULE — FERAIT UNE
    TACHE QUE PERSONNE N'A DEMANDEE ET QUE PERSONNE NE RECONNAITRA."""
    assert lire("ajoute ça aux prochaines étapes", propos_precedent="") is None


# ══════════════════════════════════════════════════════════════════════════
#  LA RAISON, ET LE TEXTE TEL QU'IL A ETE DIT
# ══════════════════════════════════════════════════════════════════════════
def test_une_decision_capte_sa_raison_dans_la_meme_phrase():
    ordre = lire(
        "on a décidé d'augmenter le débit parce que c'est le levier le moins coûteux"
    )

    assert ordre.contenu == "augmenter le débit"
    assert ordre.pourquoi == "c'est le levier le moins coûteux"


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("ouvre le projet NOVA", "NOVA"),
        ("revenons au projet Prototype-Moteur", "Prototype-Moteur"),
    ],
)
def test_la_casse_et_les_accents_survivent(phrase, attendu):
    """⚠️ LE CONTENU EST STOCKE EN BASE, ET PRONONCE A VOIX HAUTE.

    La premiere version rendait le texte APLATI :

        « ouvre le projet NOVA »   → « C'est ouvert : nova. »
        « augmenter le débit »     → « augmenter le debit »

    Le nom perdait sa casse et « débit » son accent — dans la base, et dans la
    bouche de Nova, qui le prononce alors de travers.

    L'aplatissement preserve maintenant les POSITIONS : un caractere entre, un
    caractere sort. Le contenu se relit dans le texte d'origine.
    """
    assert lire(phrase).contenu == attendu


def test_un_accent_survit_dans_une_decision():
    assert lire("on a décidé d'augmenter le débit").contenu == "augmenter le débit"


def test_un_pourcentage_survit_dans_un_objectif():
    assert lire("on va essayer de gagner 15 %").contenu == "gagner 15 %"
