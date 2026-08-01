"""Tests du mot de reveil.

Fonctions pures, donc testables sans micro ni modele. C'est aussi le seul
endroit du projet ou une erreur se traduit par « Nova ne repond pas » sans
aucun message — d'ou les tests.
"""

from nova.voice.wake import commande_apres_reveil, contient_reveil, normaliser


def test_detecte_le_mot_seul():
    assert contient_reveil("Nova")
    assert contient_reveil("nova.")


def test_detecte_dans_une_phrase():
    assert contient_reveil("Dis-moi Nova, quelle heure est-il ?")


def test_tolere_les_erreurs_de_transcription():
    # Whisper transcrit rarement « Nova » parfaitement a l'oral.
    assert contient_reveil("no va")
    assert contient_reveil("Novak")


def test_ignore_un_texte_sans_reveil():
    assert not contient_reveil("bonjour comment vas-tu")
    assert not contient_reveil("")


def test_ne_declenche_pas_sur_un_mot_qui_contient_nova():
    # « innovation » contient « nova » : sans decoupage en mots, chaque phrase
    # sur l'innovation reveillerait Nova.
    assert not contient_reveil("je travaille sur l'innovation")
    assert not contient_reveil("une renovation")


def test_extrait_la_commande_qui_suit():
    assert commande_apres_reveil("Nova quelle heure est-il") == "quelle heure est-il"
    assert commande_apres_reveil("Nova") == ""


def test_normalisation_des_accents():
    assert normaliser("Éàç !") == "eac  "
