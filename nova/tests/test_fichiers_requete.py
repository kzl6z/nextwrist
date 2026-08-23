"""D'une phrase parlee a une recherche : les mots, l'annee, le type.

CE QUE CE BANC PROTEGE

La phrase fondatrice de la fonctionnalite, telle qu'elle a ete dite :

    « Nova, peux-tu me retrouver dans mes fichiers ou dans mes photos mon
      releve de compte ou de revenus qui date de deux mille vingt-quatre ? »

Elle contient tout ce qui peut mal tourner : de la politesse, deux mots
d'image qui ne designent pas une image, un synonyme (« revenus »), et une
annee ecrite EN LETTRES parce que c'est de la voix.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nova.fichiers.requete import Recherche, lire

MAINTENANT = datetime(2026, 8, 23)


# ══════════════════════════════════════════════════════════════════════════
#  L'ANNEE
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("phrase", "attendue"),
    [
        ("mon releve de compte de 2024", 2024),
        # ⚠️ WHISPER ECRIT LES ANNEES EN LETTRES QUAND ON LES PRONONCE.
        #
        # C'est la formulation de la demande fondatrice. Un motif qui
        # n'attrape que « 2024 » l'aurait ratee — et la recherche aurait
        # quand meme rendu des resultats, simplement sans filtre de date.
        # Une panne qui ressemble a un fonctionnement.
        ("mon releve qui date de deux mille vingt-quatre", 2024),
        ("mon contrat de deux mille dix", 2010),
        ("la facture de deux mille vingt", 2020),
        ("le document d'il y a deux ans", 2024),
        ("le document d'il y a 3 ans", 2023),
        ("ma facture de l'annee derniere", 2025),
        ("mes impots de cette annee", 2026),
        ("mon relevé de compte", None),
    ],
)
def test_l_annee_se_lit_en_chiffres_en_lettres_et_en_relatif(phrase, attendue):
    assert lire(phrase, aujourdhui=MAINTENANT).annee == attendue


# ══════════════════════════════════════════════════════════════════════════
#  LES MOTS
# ══════════════════════════════════════════════════════════════════════════
def test_la_politesse_ne_se_cherche_pas():
    """⚠️ LA LECON DU CATALOGUE D'IMAGES, APPLIQUEE AVANT DE LA REAPPRENDRE.

    Chaque mot parasite fait baisser un score qui est une PROPORTION. Sur les
    images, plus la phrase etait polie, moins la recherche marchait.
    """
    recherche = lire(
        "Nova, peux-tu me retrouver dans mes fichiers s'il te plait mon "
        "releve de compte",
        aujourdhui=MAINTENANT,
    )

    assert "releve" in recherche.mots
    assert "compte" in recherche.mots
    for parasite in ("nova", "peux", "retrouver", "fichiers", "plait"):
        assert parasite not in recherche.mots, parasite


def test_le_mot_qui_nomme_le_type_ne_se_cherche_pas():
    """« en PDF » filtre l'extension — il ne se cherche pas dans le titre."""
    recherche = lire("ma facture EDF en pdf", aujourdhui=MAINTENANT)

    assert "pdf" not in recherche.mots
    assert recherche.genres == ("pdf",)
    assert ".pdf" in recherche.extensions
    assert "edf" in recherche.mots


def test_les_synonymes_elargissent_sans_remplacer():
    """On dit « releve de compte », le fichier s'appelle « extrait_bancaire »."""
    recherche = lire("mon releve de compte", aujourdhui=MAINTENANT)

    assert recherche.mots == ("releve", "compte")
    assert "extrait" in recherche.elargis
    assert "bancaire" in recherche.elargis
    # Les mots d'origine restent en tete : ce sont eux qui comptent double
    # au classement.
    assert recherche.elargis[:2] == ("releve", "compte")


def test_un_nom_propre_ne_s_elargit_pas():
    """⚠️ LES NOMS PROPRES SONT LES MEILLEURS MOTS DE RECHERCHE.

    « EDF », « Kozlowski » : uniques, donc discriminants. Les noyer dans une
    famille de synonymes detruirait exactement ce qui les rend utiles.
    """
    recherche = lire("ma facture kozlowski", aujourdhui=MAINTENANT)

    assert "kozlowski" in recherche.elargis
    # « facture » amene sa famille, « kozlowski » reste seul.
    assert "quittance" in recherche.elargis
    familles_de_kozlowski = [m for m in recherche.elargis if m.startswith("kozl")]
    assert familles_de_kozlowski == ["kozlowski"]


def test_la_phrase_fondatrice_en_entier():
    """LE BANC CENTRAL : la demande telle qu'elle a ete formulee."""
    recherche = lire(
        "Nova, peux-tu me retrouver dans mes fichiers ou dans mes photos mon "
        "releve de compte ou de revenus qui date de deux mille vingt-quatre ?",
        aujourdhui=MAINTENANT,
    )

    assert recherche.annee == 2024
    assert "releve" in recherche.mots
    assert "compte" in recherche.mots
    assert "revenus" in recherche.mots
    # « photos » nomme un TYPE, pas le fichier cherche.
    assert "photos" not in recherche.mots
    assert "image" in recherche.genres
    # Les deux familles sont ouvertes : bancaire ET salaire.
    assert "bancaire" in recherche.elargis
    assert "salaire" in recherche.elargis


def test_une_phrase_sans_rien_a_chercher_est_fausse():
    """Une `Recherche` vide ne doit pas partir interroger le disque."""
    assert not lire("bonjour Nova", aujourdhui=MAINTENANT)
    assert not lire("", aujourdhui=MAINTENANT)
    assert lire("mon releve", aujourdhui=MAINTENANT)
    # Une annee seule suffit : « mes documents de 2024 » est une recherche.
    assert Recherche(annee=2024)
