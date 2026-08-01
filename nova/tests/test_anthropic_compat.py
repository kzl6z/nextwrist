"""Tests du protocole Anthropic.

On ne teste pas la qualite des reponses mais la CONFORMITE du format : un client
Anthropic attend une sequence d'evenements precise, et en sauter un le fait
echouer silencieusement. C'est typiquement ce qui se casse a une mise a jour.
"""

from nova.api.anthropic_compat import _mode, _texte


def test_texte_accepte_une_chaine():
    assert _texte("bonjour") == "bonjour"


def test_texte_accepte_des_blocs():
    blocs = [{"type": "text", "text": "premier"}, {"type": "text", "text": "second"}]
    assert _texte(blocs) == "premier\nsecond"


def test_texte_ignore_les_blocs_non_textuels():
    # Une interface peut envoyer des images ou des appels d'outils : on les
    # ignore plutot que d'echouer, pour ne pas casser la conversation.
    blocs = [{"type": "image", "source": {}}, {"type": "text", "text": "seul texte"}]
    assert _texte(blocs) == "seul texte"


def test_texte_survit_a_un_contenu_vide():
    assert _texte(None) == ""


def test_le_mode_est_deduit_du_nom_du_modele():
    assert _mode("nova") == "normal"
    assert _mode("nova-critique") == "critique"
