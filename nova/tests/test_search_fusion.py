"""Tests de la fusion de classements (RRF).

C'est le coeur de la recherche hybride : si cette fonction est fausse, Nova
repond a cote sans qu'aucune erreur n'apparaisse jamais. D'ou les tests.
"""

from nova.documents.ranking import reciprocal_rank_fusion


def test_un_seul_classement_preserve_l_ordre():
    scores = reciprocal_rank_fusion([[10, 20, 30]])
    assert sorted(scores, key=lambda i: scores[i], reverse=True) == [10, 20, 30]


def test_un_element_present_dans_les_deux_classements_remonte():
    # 20 est deuxieme partout ; 10 et 30 sont premiers d'un seul classement.
    # RRF doit faire gagner le consensus.
    scores = reciprocal_rank_fusion([[10, 20], [30, 20]])
    assert max(scores, key=lambda i: scores[i]) == 20


def test_classement_vide_sans_effet():
    assert reciprocal_rank_fusion([[], []]) == {}


def test_k_amortit_les_premiers_rangs():
    petit = reciprocal_rank_fusion([[1, 2]], k=1)
    grand = reciprocal_rank_fusion([[1, 2]], k=1000)
    # Avec un k eleve, l'ecart entre le premier et le second se resserre.
    assert (petit[1] - petit[2]) > (grand[1] - grand[2])
