"""Tests du decoupage.

On teste en priorite les fonctions PURES : pas de base, pas de reseau, donc
des tests rapides et fiables. C'est la meilleure depense d'effort de test du
projet — le decoupage est le maillon qui degrade silencieusement la recherche.
"""

from nova.documents.chunking import chunk_text, split_sections

DOC = """Intro sans titre.

# Projet Nova

Premier paragraphe du projet.

Second paragraphe du projet.

## Budget

Le budget est de mille euros.
"""


def test_split_sections_conserve_le_preambule():
    sections = split_sections(DOC)
    assert sections[0][0] is None
    assert "Intro sans titre" in sections[0][1]


def test_split_sections_detecte_les_titres():
    titres = [titre for titre, _ in split_sections(DOC)]
    assert "Projet Nova" in titres
    assert "Budget" in titres


def test_chunk_text_attache_le_titre_de_section():
    chunks = chunk_text(DOC, size=200, overlap=20)
    budget = [c for c in chunks if "mille euros" in c.content]
    assert budget and budget[0].heading == "Budget"


def test_chunk_text_respecte_la_taille_approximative():
    texte = "\n\n".join(f"Paragraphe numero {i}. " * 12 for i in range(40))
    chunks = chunk_text(texte, size=500, overlap=50)
    assert len(chunks) > 1
    # taille + recouvrement + une marge : jamais de morceau demesure
    assert all(len(c.content) <= 500 + 50 + 20 for c in chunks)


def test_les_ordinaux_sont_continus():
    chunks = chunk_text(DOC, size=100, overlap=10)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_recouvrement_superieur_a_la_taille_est_refuse():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("abc", size=100, overlap=100)
