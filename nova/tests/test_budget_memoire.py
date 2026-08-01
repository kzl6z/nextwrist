"""Budget en caracteres du bloc de memoire.

Sur un modele local, le temps avant le premier mot est proportionnel a la
taille du prompt. Mesure sur l'iMac M1 : 6573 caracteres → 21,4 s, soit
~3,3 ms par caractere.

Sans borne, Nova ralentit a mesure qu'elle apprend — le pire defaut possible
pour un systeme dont l'accumulation est la raison d'etre.
"""

from nova.memory.facts import tenir_dans_le_budget


def _cout(contenus):
    return sum(len(c) + 3 for c in contenus)


def test_garde_tout_quand_ca_tient():
    faits = ["Hugo travaille sur Nova", "Hugo est debutant en developpement"]
    assert tenir_dans_le_budget(faits, 1200) == faits


def test_respecte_le_budget():
    faits = ["x" * 100] * 50
    gardes = tenir_dans_le_budget(faits, 1200)
    assert _cout(gardes) <= 1200
    assert len(gardes) < len(faits)


def test_garde_les_plus_recents_dabord():
    # `list_facts` rend les faits du plus recent au plus ancien : le budget
    # doit donc consommer la liste dans l'ordre recu.
    faits = ["recent", "moyen", "ancien"]
    assert tenir_dans_le_budget(faits, 20) == ["recent", "moyen"]


def test_un_fait_enorme_ne_fait_pas_taire_les_suivants():
    # Sinon un seul fait mal saisi supprimerait toute la memoire du prompt,
    # sans le moindre message.
    faits = ["court", "x" * 5000, "aussi court"]
    assert tenir_dans_le_budget(faits, 1200) == ["court", "aussi court"]


def test_budget_nul_ou_liste_vide():
    assert tenir_dans_le_budget([], 1200) == []
    assert tenir_dans_le_budget(["quelque chose"], 0) == []
