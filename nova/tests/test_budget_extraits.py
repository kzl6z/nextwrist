"""Budget en caracteres des extraits documentaires.

Meme defaut que la memoire (R13), meme cause, trouve au meme endroit :
borner le NOMBRE ne borne pas la TAILLE, et le temps de lecture d'un modele
local est proportionnel a la taille du prompt.

Mesure en conditions reelles, pour « Dis bonjour en une phrase » :

    identite 1495 + memoire 260 + instant 183 + documents 4825
    -> prompt 6805 car. -> premier mot 10,4 s

Les documents pesaient 71 % du prompt, sur une demande qui n'en appelait
aucun.
"""

from nova.memory.models import SearchHit
from nova.orchestrator import _format_sources


def _extrait(titre: str, contenu: str) -> SearchHit:
    return SearchHit(
        chunk_id=1,
        document_title=titre,
        document_path=f"/{titre}.md",
        heading="section",
        content=contenu,
        score=1.0,
    )


def test_garde_tout_quand_ca_tient():
    hits = [_extrait("a", "court"), _extrait("b", "aussi court")]
    rendu = _format_sources(hits, budget=2000)
    assert "court" in rendu and "aussi court" in rendu


def test_respecte_le_budget():
    hits = [_extrait(f"doc{i}", "x" * 1000) for i in range(6)]
    rendu = _format_sources(hits, budget=2000)
    assert len(rendu) <= 2000 + 10   # marge des separateurs
    assert rendu.count("---") < 6


def test_garde_les_plus_pertinents_dabord():
    # Les extraits arrivent deja classes : couper par la fin sacrifie les
    # moins utiles, ce qui est exactement ce qu'on veut.
    hits = [_extrait("pertinent", "a" * 900), _extrait("moins", "b" * 900),
            _extrait("marginal", "c" * 900)]
    rendu = _format_sources(hits, budget=2000)
    assert "pertinent" in rendu
    assert "marginal" not in rendu


def test_un_extrait_enorme_ne_fait_pas_taire_les_suivants():
    hits = [_extrait("enorme", "x" * 50_000), _extrait("utile", "contenu utile")]
    rendu = _format_sources(hits, budget=2000)
    assert "contenu utile" in rendu
    assert "enorme" not in rendu


def test_aucun_extrait_ne_produit_rien():
    assert _format_sources([], budget=2000) == ""
