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


@pytest.fixture(autouse=True)
def moteur_de_fichiers_identique_partout(monkeypatch):
    """⚠️ LES BANCS DE FICHIERS NE MESURAIENT PAS LA MEME CHOSE SELON LA MACHINE.

    `moteur()` choisit Spotlight des que `/usr/bin/mdfind` existe. Sur un Mac,
    il existe : VINGT-HUIT bancs lancaient donc le vrai Spotlight contre un
    `tmp_path` — un dossier de `/var/folders` que l'index ne connait pas. Ils
    ne trouvaient rien, et ils tombaient.

    Sur la machine de developpement, sous Linux, `mdfind` n'existe pas, le
    parcours a la main prenait le relais, et les vingt-huit passaient.

    Releve tel quel : `git pull && make test` sur le Mac, une colonne de F que
    je n'avais aucun moyen de voir ici.

    ⚠️ ET C'EST LE PIRE SENS POUR UN BANC : IL PASSAIT LA OU IL NE PROTEGEAIT
       RIEN, ET IL TOMBAIT LA OU LE CODE EST BON.

    Ce que ces bancs protegent, c'est la traduction du francais, le
    classement, et le cablage jusqu'a l'outil. Le moteur qui va chercher n'est
    pas leur sujet : on le fixe, pour qu'ils mesurent la meme chose partout.

    ⚠️ CE N'EST PAS UNE FACON DE NE PAS TESTER SPOTLIGHT.

    `Spotlight.chercher` a ses propres bancs, qui remplacent `_lancer` — sa
    seule sortie vers le systeme — et verifient les deux passes sans jamais
    dependre de l'index de la machine.
    """
    from nova.fichiers import moteurs

    monkeypatch.setattr(moteurs.Spotlight, "disponible", staticmethod(lambda: False))
