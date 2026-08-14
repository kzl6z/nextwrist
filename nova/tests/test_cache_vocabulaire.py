"""Le vocabulaire personnel ne fait jamais attendre la parole de Nova.

CE QUE CES TESTS PROTEGENT

Deux defauts successifs, tous deux sur le meme chemin.

  1. Chaque phrase dictee declenchait DEUX lectures de la memoire avant meme
     que Whisper ne commence : une pour l'amorce de transcription, une pour le
     lexique de correction. Un cache commun les a ramenees a une.

  2. Cette lecture unique restait BLOQUANTE. Tant que la base repond en dix
     millisecondes, personne ne le voit. Mesure avec une base injoignable :
     30 secondes avant la premiere transcription — pour un enrichissement
     facultatif. Le chemin vocal ne doit jamais attendre la base.

La regle qui en decoule : on rend ce qu'on a, et on relit EN FOND. Le pire
cas devient « Nova entend un peu moins bien les noms propres pendant une
minute », au lieu de « Nova ne repond pas ».
"""

import time

import pytest

from nova import orchestrator


class FaitFictif:
    def __init__(self, contenu: str) -> None:
        self.content = contenu


def attendre_la_relecture(delai: float = 3.0) -> None:
    """Attend qu'une relecture de fond se termine.

    Les tests ont besoin de determinisme ; la production a besoin de ne pas
    attendre. Cette attente vit donc ici, dans les tests, et nulle part
    ailleurs.
    """
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        if orchestrator._vocabulaire_cache is not None:
            return
        time.sleep(0.01)
    raise AssertionError("la relecture de fond ne s'est jamais terminee")


@pytest.fixture
def memoire_comptee(monkeypatch):
    """Remplace la memoire par un compteur de lectures."""
    compte = {"lectures": 0, "contenu": ["Hugo travaille sur Ollama et Electron"]}

    def fausse_lecture(status=None, category=None):
        compte["lectures"] += 1
        return [FaitFictif(c) for c in compte["contenu"]]

    monkeypatch.setattr(orchestrator.facts, "list_facts", fausse_lecture)
    orchestrator._vocabulaire_cache = None
    yield compte
    orchestrator._vocabulaire_cache = None


# ── Le chemin vocal ne bloque jamais ──────────────────────────────────────


def test_le_chemin_vocal_ne_bloque_jamais_sur_la_base(monkeypatch):
    """Le defaut exact : une base lente faisait attendre la parole.

    On simule une base qui met deux secondes. Les deux appels du chemin
    vocal doivent rendre la main immediatement.
    """

    def base_lente(status=None, category=None):
        time.sleep(2.0)
        return [FaitFictif("Hugo travaille sur Ollama")]

    monkeypatch.setattr(orchestrator.facts, "list_facts", base_lente)
    orchestrator._vocabulaire_cache = None

    depart = time.monotonic()
    orchestrator.amorce_dictee()
    orchestrator.lexique_personnel()
    ecoule = time.monotonic() - depart

    assert ecoule < 0.5, f"le chemin vocal a attendu {ecoule:.2f} s la base de donnees"


def test_la_relecture_de_fond_finit_par_arriver(memoire_comptee):
    """Non bloquant ne veut pas dire jamais lu."""
    orchestrator.lexique_personnel()          # declenche la lecture de fond
    attendre_la_relecture()
    assert "Ollama" in orchestrator.lexique_personnel()


# ── Le cache tient toujours son role ──────────────────────────────────────


def test_les_deux_etages_vocaux_partagent_une_seule_lecture(memoire_comptee):
    orchestrator.rafraichir_le_vocabulaire()   # amorcage, comme au demarrage
    assert memoire_comptee["lectures"] == 1

    orchestrator.amorce_dictee()
    orchestrator.lexique_personnel()
    assert memoire_comptee["lectures"] == 1, "le cache doit servir les deux etages"


def test_les_phrases_suivantes_ne_relisent_rien(memoire_comptee):
    orchestrator.rafraichir_le_vocabulaire()
    for _ in range(5):
        orchestrator.amorce_dictee()
        orchestrator.lexique_personnel()
    assert memoire_comptee["lectures"] == 1


def test_le_contenu_reste_correct(memoire_comptee):
    orchestrator.rafraichir_le_vocabulaire()
    lexique = orchestrator.lexique_personnel()
    assert "Ollama" in lexique
    assert "Electron" in lexique
    # Le cache ne doit pas figer une reference partagee : deux appels donnent
    # deux lexiques independants, sinon une correction apprise dans l'un
    # apparaitrait dans l'autre.
    assert orchestrator.lexique_personnel() is not lexique


def test_le_cache_expire_tout_seul(memoire_comptee, monkeypatch):
    monkeypatch.setattr(orchestrator, "DUREE_CACHE_VOCABULAIRE", 0.05)
    orchestrator.rafraichir_le_vocabulaire()
    assert memoire_comptee["lectures"] == 1

    time.sleep(0.06)
    orchestrator.lexique_personnel()      # constate la peremption, relit en fond
    limite = time.monotonic() + 3.0
    while memoire_comptee["lectures"] < 2 and time.monotonic() < limite:
        time.sleep(0.01)
    assert memoire_comptee["lectures"] == 2


# ── Un fait nouveau doit etre entendu vite ────────────────────────────────


def test_un_fait_nouveau_declenche_une_relecture_immediate(memoire_comptee):
    """Confirmer un fait relance la lecture tout de suite, pas a la prochaine phrase.

    Entre le moment ou tu confirmes un fait et celui ou tu prononces le nom
    qu'il contient, il s'ecoule des secondes : largement de quoi relire sans
    que personne n'attende.
    """
    orchestrator.rafraichir_le_vocabulaire()
    memoire_comptee["contenu"].append("Mon assistant s appelle Sentinel")

    orchestrator.oublier_le_vocabulaire()
    attendre_la_relecture()
    assert "Sentinel" in orchestrator.lexique_personnel()


# ── La panne reste une degradation, jamais un arret ───────────────────────


def test_une_memoire_en_panne_ne_rend_pas_nova_muette(monkeypatch):
    def memoire_cassee(status=None, category=None):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(orchestrator.facts, "list_facts", memoire_cassee)
    orchestrator._vocabulaire_cache = None
    try:
        assert isinstance(orchestrator.amorce_dictee(), str)
        assert len(orchestrator.lexique_personnel()) >= 0
        # Et la relecture directe ne leve pas davantage.
        assert orchestrator.rafraichir_le_vocabulaire() == ()
    finally:
        orchestrator._vocabulaire_cache = None


def test_dix_appels_simultanes_ne_lancent_pas_dix_lectures(memoire_comptee):
    """Sans garde, une rafale de requetes ouvrirait dix connexions a la base."""
    orchestrator._vocabulaire_cache = None
    for _ in range(10):
        orchestrator.lexique_personnel()
    attendre_la_relecture()
    time.sleep(0.05)
    assert memoire_comptee["lectures"] <= 2, (
        f"{memoire_comptee['lectures']} lectures pour dix appels rapproches"
    )
