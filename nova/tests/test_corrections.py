"""Homophones /sɛ/ : « sais », « c'est », « ces », « ses », « s'est ».

Releve en conditions reelles :

    « que sais-tu de moi ? »  ->  « que c'est-tu de moi ? »

La regle qu'on s'impose : ne corriger QUE des formes agrammaticales. Les
tests negatifs sont donc plus importants que les positifs — un correcteur
qui casse des phrases justes est pire que pas de correcteur du tout.
"""

import pytest

from nova.voice.corrections import corriger


@pytest.mark.parametrize(
    ("entree", "attendu"),
    [
        ("que c'est-tu de moi ?", "que sais-tu de moi ?"),
        ("Que ces-tu de moi ?", "Que sais-tu de moi ?"),
        ("que ses-tu de mes projets", "que sais-tu de mes projets"),
        ("que sait-tu de moi", "que sais-tu de moi"),
        ("que s'est-tu de moi", "que sais-tu de moi"),
        ("que c'est tu de moi", "que sais-tu de moi"),
        ("je c'est que tu viens", "je sais que tu viens"),
        ("tu ces bien que non", "tu sais bien que non"),
        ("qu'est-ce que tu c'est de lui", "qu'est-ce que tu sais de lui"),
    ],
)
def test_corrige_les_formes_impossibles(entree, attendu):
    corrige, changements = corriger(entree)
    assert corrige == attendu
    assert changements, "une correction doit toujours etre signalee"


@pytest.mark.parametrize(
    "phrase",
    [
        # Toutes ces phrases sont correctes : y toucher serait une regression.
        "c'est tout ce que je voulais dire",
        "ces tulipes sont magnifiques",
        "ses tuiles ont ete refaites l'an dernier",
        "il s'est tu pendant toute la reunion",
        "c'est ta voiture qui est garee dehors",
        "je sais deja tout ca",
        "tu sais ce que j'en pense",
        "ces temps-ci je travaille beaucoup",
        "c'est un bon debut",
        "",
    ],
)
def test_ne_touche_pas_aux_phrases_correctes(phrase):
    corrige, changements = corriger(phrase)
    assert corrige == phrase
    assert changements == []


def test_le_passe_compose_de_se_taire_survit():
    # « s'est tu » est correct, « s'est-tu » ne l'est pas. Un caractere de
    # difference, deux traitements opposes.
    assert corriger("il s'est tu")[0] == "il s'est tu"
    assert corriger("que s'est-tu de moi")[0] == "que sais-tu de moi"


def test_les_changements_sont_rapportes():
    _, changements = corriger("que c'est-tu de moi")
    assert changements == ["c'est-tu"]
