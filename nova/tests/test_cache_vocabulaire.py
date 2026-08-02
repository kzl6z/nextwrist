"""Le vocabulaire personnel est lu une fois, pas a chaque phrase.

CE QUE CES TESTS PROTEGENT

Chaque phrase dictee declenchait DEUX lectures de la memoire avant meme que
Whisper ne commence : une pour l'amorce de transcription, une pour le lexique
de correction. Sur une base lente ou indisponible, c'est du temps d'attente
pur, paye a chaque mot prononce — exactement le genre de cout invisible qui
rend un assistant « lent » sans qu'aucune ligne ne paraisse coupable.

Le cache a une contrepartie qu'il faut tenir : un nom qui vient d'entrer en
memoire doit etre ENTENDU tout de suite. D'ou le dernier test.
"""

import time

import pytest

from nova import orchestrator


class FaitFictif:
    def __init__(self, contenu: str) -> None:
        self.content = contenu


@pytest.fixture
def memoire_comptee(monkeypatch):
    """Remplace la memoire par un compteur de lectures."""
    compte = {"lectures": 0, "contenu": ["Hugo travaille sur Ollama et Electron"]}

    def fausse_lecture(status=None, category=None):
        compte["lectures"] += 1
        return [FaitFictif(c) for c in compte["contenu"]]

    monkeypatch.setattr(orchestrator.facts, "list_facts", fausse_lecture)
    orchestrator.oublier_le_vocabulaire()
    yield compte
    orchestrator.oublier_le_vocabulaire()


def test_les_deux_etages_vocaux_partagent_une_seule_lecture(memoire_comptee):
    orchestrator.amorce_dictee()
    orchestrator.lexique_personnel()
    assert memoire_comptee["lectures"] == 1


def test_les_phrases_suivantes_ne_relisent_rien(memoire_comptee):
    for _ in range(5):
        orchestrator.amorce_dictee()
        orchestrator.lexique_personnel()
    assert memoire_comptee["lectures"] == 1


def test_le_contenu_reste_correct(memoire_comptee):
    lexique = orchestrator.lexique_personnel()
    assert "Ollama" in lexique
    assert "Electron" in lexique
    # Le cache ne doit pas figer une reference partagee : deux appels donnent
    # deux lexiques independants, sinon une correction apprise dans l'un
    # apparaitrait dans l'autre.
    autre = orchestrator.lexique_personnel()
    assert autre is not lexique


def test_un_fait_nouveau_est_entendu_des_la_phrase_suivante(memoire_comptee):
    orchestrator.lexique_personnel()
    memoire_comptee["contenu"].append("Mon assistant s appelle Sentinel")

    # Sans invalidation, le nouveau nom attendrait la fin du cache.
    assert "Sentinel" not in orchestrator.lexique_personnel()

    orchestrator.oublier_le_vocabulaire()
    assert "Sentinel" in orchestrator.lexique_personnel()


def test_une_memoire_en_panne_ne_rend_pas_nova_muette(monkeypatch):
    def memoire_cassee(status=None, category=None):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(orchestrator.facts, "list_facts", memoire_cassee)
    orchestrator.oublier_le_vocabulaire()
    try:
        # Degrade, jamais casse : on perd les noms propres, pas la parole.
        assert isinstance(orchestrator.amorce_dictee(), str)
        assert len(orchestrator.lexique_personnel()) >= 0
    finally:
        orchestrator.oublier_le_vocabulaire()


def test_le_cache_expire_tout_seul(memoire_comptee, monkeypatch):
    monkeypatch.setattr(orchestrator, "DUREE_CACHE_VOCABULAIRE", 0.05)
    orchestrator.lexique_personnel()
    assert memoire_comptee["lectures"] == 1
    time.sleep(0.06)
    orchestrator.lexique_personnel()
    assert memoire_comptee["lectures"] == 2
