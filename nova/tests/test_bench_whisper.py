"""La mesure de precision doit etre juste avant de servir a decider.

Un banc d'essai faux est pire qu'aucun banc : il donne une raison chiffree
de prendre la mauvaise decision. Celui-ci a decide du modele de
transcription — il merite d'etre verifie.
"""

import pytest

# `scripts` est sur le pythonpath des tests (pyproject.toml) : le banc d'essai
# est du code du projet, pas un script jetable, et il se teste comme tel.
from bench_whisper import Resultat, _mots, distance_mots

# ── Le decoupage en mots ──────────────────────────────────────────────────


def test_les_accents_ne_comptent_pas_comme_des_erreurs():
    """Whisper ecrit tantot « planetes », tantot « planètes ».

    Compter ca comme une faute noierait les vraies — celles qui changent le
    sens — sous du bruit typographique.
    """
    assert _mots("Les planètes") == _mots("Les planetes")


def test_la_ponctuation_ne_compte_pas():
    assert _mots("Qu'est-ce qu'un trou noir ?") == _mots("qu est ce qu un trou noir")


def test_la_casse_ne_compte_pas():
    assert _mots("La Terre") == _mots("la terre")


# ── La distance ───────────────────────────────────────────────────────────


def test_deux_phrases_identiques_sont_a_distance_zero():
    phrase = _mots("quel est le diametre de la Terre")
    assert distance_mots(phrase, phrase) == 0


def test_un_mot_faux_compte_pour_une_erreur():
    """« germetre » pour « diametre » est UNE erreur, pas cinq lettres.

    C'est tout l'interet de mesurer au niveau des mots : ce qui compte est
    combien de mots sont faux, pas de combien de lettres ils le sont.
    """
    attendu = _mots("quel est le diametre de la Terre")
    obtenu = _mots("quel est le germetre de la Terre")
    assert distance_mots(attendu, obtenu) == 1


def test_le_cas_reel_releve_en_conditions_reelles():
    """« quel est le diametre » -> « quelle est-il de germetre ».

    Quatre mots touches sur sept : la mesure doit refleter que la phrase est
    largement abimee, pas seulement effleuree.
    """
    attendu = _mots("quel est le diametre de la Terre")
    obtenu = _mots("quelle est-il de germetre de la terre")
    erreurs = distance_mots(attendu, obtenu)
    assert 2 <= erreurs <= 4, f"{erreurs} erreurs : la mesure a perdu le sens de l'echelle"


def test_un_mot_manquant_compte():
    assert distance_mots(_mots("un deux trois"), _mots("un trois")) == 1


def test_un_mot_en_trop_compte():
    assert distance_mots(_mots("un trois"), _mots("un deux trois")) == 1


def test_une_transcription_vide_coute_tous_les_mots():
    attendu = _mots("quel est le diametre de la Terre")
    assert distance_mots(attendu, []) == len(attendu)


def test_la_distance_est_symetrique():
    a, b = _mots("le chat dort"), _mots("le chien dort ici")
    assert distance_mots(a, b) == distance_mots(b, a)


# ── Le calcul de precision ────────────────────────────────────────────────


def test_une_transcription_parfaite_donne_cent_pour_cent():
    r = Resultat(modele="base", beam=1, mots_totaux=100, erreurs=0)
    assert r.precision == 1.0


def test_la_precision_ne_descend_jamais_sous_zero():
    """Plus d'erreurs que de mots est possible : le modele peut inventer.

    Sans borne, on afficherait « -40 % de mots justes », ce qui ne veut rien
    dire et fait douter du banc entier.
    """
    r = Resultat(modele="base", beam=1, mots_totaux=10, erreurs=14)
    assert r.precision == 0.0


def test_sans_mots_la_precision_ne_leve_pas():
    assert Resultat(modele="base", beam=1).precision == 0.0


def test_le_facteur_temps_reel_se_lit_comme_une_vitesse():
    """0,5x veut dire deux fois plus rapide que la parole."""
    r = Resultat(modele="base", beam=1, secondes=5.0, audio_secondes=10.0)
    assert r.temps_reel == pytest.approx(0.5)


def test_sans_audio_le_facteur_ne_leve_pas():
    assert Resultat(modele="base", beam=1, secondes=5.0).temps_reel == 0.0
