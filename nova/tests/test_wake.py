"""Tests du mot de reveil.

Fonctions pures, donc testables sans micro ni modele. C'est aussi le seul
endroit du projet ou une erreur se traduit par « Nova ne repond pas » sans
aucun message — d'ou les tests.
"""

from nova.voice.wake import (
    commande_apres_reveil,
    contient_reveil,
    normaliser,
    reveil_franc,
)


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


# --- instant present ---------------------------------------------------------

from datetime import datetime  # noqa: E402

from nova.orchestrator import instant_present  # noqa: E402


def test_la_date_est_en_francais_quelle_que_soit_la_machine():
    # 1er aout 2026 tombe un samedi.
    assert instant_present(datetime(2026, 8, 1, 14, 30)) == "samedi 1 aout 2026, il est 14:30"


def test_minuit_est_correctement_formate():
    assert "00:05" in instant_present(datetime(2026, 1, 5, 0, 5))


# --- confusions reelles de Whisper -------------------------------------------
#
# Transcriptions relevees en conditions reelles, quand l'utilisateur disait
# « Nova, quelle heure est-il ». Le modele ne connaissant pas ce prenom, il le
# remplace par le mot francais le plus proche.


def test_accepte_les_confusions_en_debut_de_phrase():
    assert contient_reveil("Nouveau, quelle heure est-il ?")
    assert contient_reveil("Au revoir, quelle heure est-il ?")


def test_refuse_ces_memes_mots_ailleurs_dans_la_phrase():
    # Sinon toute phrase contenant « nouveau » reveillerait Nova.
    assert not contient_reveil("je commence un nouveau projet")
    assert not contient_reveil("bon je te dis au revoir")


def test_extrait_la_commande_malgre_la_confusion():
    assert commande_apres_reveil("Nouveau, quelle heure est-il ?") == "quelle heure est-il"
    assert commande_apres_reveil("Au revoir, quelle heure est-il ?") == "quelle heure est-il"


# ── Attaque rognee ────────────────────────────────────────────────────────
# L'enregistrement demarre sur un seuil sonore : la premiere consonne est
# deja passee. Les deux cas ci-dessous sont des transcriptions REELLES,
# relevees dans les logs de la machine, pour « Nova, quelle heure est-il ? ».


def test_tolere_une_attaque_rognee_en_debut_denonce():
    assert contient_reveil("Nous va qu'elle a rechelle.")
    assert contient_reveil("C'est au va qu'elle aurait-il ?")


def test_lattaque_rognee_ne_vaut_quen_debut_denonce():
    # « va » au milieu d'une phrase ne doit jamais reveiller Nova.
    assert not contient_reveil("On va au cinema ce soir")
    assert not contient_reveil("Il faut que je valide le devis")
    assert not contient_reveil("Ca va bien merci")
    assert not contient_reveil("Je commence un nouveau projet demain")


def test_une_question_seule_ne_reveille_pas():
    # Whisper perd parfois le mot entierement : mieux vaut ne pas repondre
    # que de repondre a une phrase qui ne s'adressait pas a Nova.
    assert not contient_reveil("Quelle heure est-il ?")
    assert not contient_reveil("Qu'est-ce que tu as fait ?")
    assert not contient_reveil("... ... ...")


def test_lattaque_rognee_retire_les_bons_mots():
    # « c'est » est UN mot pour l'utilisateur, deux apres normalisation :
    # le decoupage doit se faire sur le texte original.
    assert commande_apres_reveil("C'est au va ouvre le projet") == "ouvre le projet"


# ── Franchise de la detection ─────────────────────────────────────────────


def test_reveil_franc_distingue_la_tolerance():
    assert reveil_franc("Nova, quelle heure est-il ?")
    # Reconnu, mais devine : la question qui suit n'est pas fiable.
    assert contient_reveil("Nous va qu'elle a rechelle.")
    assert not reveil_franc("Nous va qu'elle a rechelle.")
