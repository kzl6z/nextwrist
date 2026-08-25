"""Ce qui doit etre remis a zero entre deux bancs, pour tous les bancs.

⚠️ UN ETAT DE MODULE FUIT D'UN BANC A L'AUTRE, ET LE PIEGE EST QU'IL FAIT
   PASSER LES BANCS — PAS ECHOUER.

Releve ici meme : `test_vision_regard.py` retenait une image et ne l'oubliait
pas. Le banc suivant, `test_le_regard_traverse_le_vrai_moteur`, partait alors
regarder un fichier du `tmp_path` du banc precedent — hors des dossiers
autorises. Il tombait pour une raison qui n'avait rien a voir avec ce qu'il
protege, et seulement dans la suite complete : seul, il passait.

Chaque fichier de bancs peut poser sa propre remise a zero, et
`test_vision_focus.py` le faisait. Mais compter sur le fait que chaque fichier
y pense, c'est attendre du prochain qu'il connaisse un piege qui ne se voit
pas. Ici, c'est acquis pour tout le monde.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def sans_image_retenue():
    """« L'image dont on parle » ne survit pas a un banc.

    Elle vit dix minutes en memoire vive (`vision/focus.py`) — bien assez pour
    traverser toute une suite de bancs.
    """
    from nova.vision import focus

    focus.oublier()
    yield
    focus.oublier()


@pytest.fixture(autouse=True)
def sans_conversation_ouverte():
    """⚠️ UNE CONVERSATION OUVERTE DURE 45 SECONDES — DONC TOUTE UNE SUITE.

    Le meme piege que la retenue d'image, en plus visible : tant qu'elle est
    ouverte, `/v1/audio/wake` repond `true` a n'importe quel son. Un banc qui
    reveille Nova faisait donc passer pour un reveil tout ce que les bancs
    suivants lui envoyaient — releve tel quel, sur un banc dont le nom disait
    « sans mot de reveil ».

    La proposition en attente est remise a zero avec, pour la meme raison :
    un « oui » d'un banc ne doit pas declencher l'action d'un autre.
    """
    from nova.voice import session

    session.oublier()
    yield
    session.oublier()
