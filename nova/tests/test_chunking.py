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


# --- filtre de raisonnement ---------------------------------------------------

from nova.llm.client import FinDeJson, ThinkFilter  # noqa: E402


def _filtrer(fragments):
    f = ThinkFilter()
    return "".join(f.feed(p) for p in fragments) + f.flush()


def test_filtre_laisse_passer_un_texte_normal():
    assert _filtrer(["Bonjour ", "le ", "monde"]) == "Bonjour le monde"


def test_filtre_retire_un_bloc_de_raisonnement():
    assert _filtrer(["<think>bla bla</think>", "Bonjour !"]) == "Bonjour !"


def test_filtre_gere_une_balise_coupee_entre_deux_fragments():
    # Cas reel du flux : la balise arrive en morceaux.
    assert _filtrer(["<thi", "nk>reflexion</thi", "nk>", "Reponse"]) == "Reponse"


def test_filtre_ne_rend_rien_si_le_bloc_reste_ouvert():
    assert _filtrer(["<think>raisonnement interrompu"]) == ""


# ── Fin d'objet JSON ──────────────────────────────────────────────────────
# Le decodage contraint garantit un JSON valide, pas un arret a la fermeture :
# Ollama remplit ensuite jusqu'au plafond de jetons. On coupe donc nous-memes.


def _passer(fragments):
    """Fait passer des fragments dans le detecteur et rend (texte, termine)."""
    fin = FinDeJson()
    sortie = []
    for fragment in fragments:
        sortie.append(fin.feed(fragment))
        if fin.termine:
            break
    return "".join(sortie), fin.termine


def test_coupe_a_la_fermeture_de_lobjet():
    texte, termine = _passer(['{"response":"samedi"}', "\n\n\n\n\n     \n\n"])
    assert termine
    assert texte == '{"response":"samedi"}'


def test_laisse_passer_un_objet_imbrique_entier():
    objet = '{"response":"ok","memory":{"shouldRemember":true,"title":"Nova"}}'
    texte, termine = _passer([objet, "du remplissage"])
    assert termine
    assert texte == objet


def test_une_accolade_dans_une_chaine_ne_ferme_rien():
    objet = '{"response":"il a dit } puis {"}'
    texte, termine = _passer([objet, "apres"])
    assert termine
    assert texte == objet


def test_un_guillemet_echappe_ne_ferme_pas_la_chaine():
    objet = '{"response":"il a dit \\"bonjour\\" } encore"}'
    texte, termine = _passer([objet, "apres"])
    assert termine
    assert texte == objet


def test_fonctionne_a_cheval_sur_les_fragments():
    # Cas reel : le flux arrive jeton par jeton, pas objet par objet.
    texte, termine = _passer(['{"resp', 'onse":"sam', 'edi"', "}", "   \n\n"])
    assert termine
    assert texte == '{"response":"samedi"}'


def test_ne_coupe_pas_un_objet_incomplet():
    texte, termine = _passer(['{"response":"sam'])
    assert not termine
    assert texte == '{"response":"sam'
