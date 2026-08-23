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


# ── Les formats acceptes ──────────────────────────────────────────────────
#
# Le banc n'imposait que le .wav. Or Dictaphone exporte en .m4a, QuickTime
# aussi — et le decodeur les lit tous, puisque c'est le meme que celui de
# Whisper. Refuser un format obligeait a convertir pour rien, donc a ajouter
# une etape ou l'on peut se tromper.


def test_les_formats_courants_sont_acceptes(tmp_path, monkeypatch):
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    for nom in ("01.wav", "02.m4a", "03.mp3", "04.aiff"):
        (tmp_path / nom).touch()
    assert len(bench_whisper.audios()) == 4


def test_les_fichiers_qui_ne_sont_pas_de_l_audio_sont_ignores(tmp_path, monkeypatch):
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    (tmp_path / "01.wav").touch()
    (tmp_path / "01.txt").touch()
    (tmp_path / "notes.md").touch()
    assert [f.name for f in bench_whisper.audios()] == ["01.wav"]


def test_l_ordre_suit_le_nom_du_fichier(tmp_path, monkeypatch):
    """L'association texte/audio se fait par l'ORDRE : il doit etre stable.

    Un tri par date de modification, par exemple, changerait l'ordre a
    chaque copie du dossier — et decalerait toutes les references d'un cran
    sans que rien ne le signale.
    """
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    for nom in ("03.wav", "01.wav", "02.wav"):
        (tmp_path / nom).touch()
    assert [f.stem for f in bench_whisper.audios()] == ["01", "02", "03"]


def test_un_dossier_absent_ne_leve_pas(tmp_path, monkeypatch):
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path / "pas-la")
    assert bench_whisper.audios() == []


def test_un_audio_sans_texte_est_ignore(tmp_path, monkeypatch):
    """Mieux vaut mesurer sur huit phrases sures que sur douze dont quatre
    comparees a une reference devinee."""
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    (tmp_path / "01.wav").touch()
    (tmp_path / "01.txt").write_text("Quel est le diametre de la Terre ?")
    (tmp_path / "02.wav").touch()          # sans .txt
    assert len(bench_whisper.echantillons()) == 1


# ── L'association automatique ─────────────────────────────────────────────


def test_l_association_ecrit_les_textes_dans_l_ordre(tmp_path, monkeypatch, capsys):
    import bench_whisper
    from enregistrer_voix import PHRASES

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    for nom in ("01.m4a", "02.m4a", "03.m4a"):
        (tmp_path / nom).touch()

    assert bench_whisper.associer_les_textes() == 0
    for numero, phrase in enumerate(PHRASES[:3], 1):
        assert (tmp_path / f"{numero:02d}.txt").read_text(encoding="utf-8") == phrase


def test_l_association_n_ecrase_jamais_un_texte_existant(tmp_path, monkeypatch):
    """Une correction faite a la main doit survivre a une seconde execution."""
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    (tmp_path / "01.m4a").touch()
    (tmp_path / "01.txt").write_text("ce que j'ai VRAIMENT dit", encoding="utf-8")

    bench_whisper.associer_les_textes()
    assert (tmp_path / "01.txt").read_text(encoding="utf-8") == "ce que j'ai VRAIMENT dit"


def test_l_association_sans_fichier_le_dit(tmp_path, monkeypatch):
    import bench_whisper

    monkeypatch.setattr(bench_whisper, "DOSSIER", tmp_path)
    assert bench_whisper.associer_les_textes() == 1


# ── Le choix des configurations mesurees ──────────────────────────────────
def test_on_peut_restreindre_les_modeles_mesures(monkeypatch):
    """⚠️ MESURER `medium` COUTE 1,5 Go ET UNE LONGUE ATTENTE.

    La question posee est « base ou small ». Y repondre ne doit pas obliger a
    mesurer un modele qui ne tiendra pas sur 8 Go a cote du reste.
    """
    from bench_whisper import configurations

    monkeypatch.setenv("MODELES", "base,small")

    assert {m for m, _ in configurations()} == {"base", "small"}


def test_sans_variable_on_mesure_tout(monkeypatch):
    from bench_whisper import CONFIGURATIONS, configurations

    monkeypatch.delenv("MODELES", raising=False)

    assert configurations() == CONFIGURATIONS


def test_une_valeur_inconnue_ne_vide_pas_la_mesure(monkeypatch):
    """Un nom mal tape rendrait une liste vide, donc une mesure sans resultat
    et sans explication. On retombe sur tout plutot que sur rien."""
    from bench_whisper import CONFIGURATIONS, configurations

    monkeypatch.setenv("MODELES", "smal")

    assert configurations() == CONFIGURATIONS


def test_les_phrases_qui_echouent_aujourd_hui_sont_mesurees():
    """⚠️ UNE MESURE SUR LES ANCIENNES PHRASES REPONDRAIT A L'ANCIENNE
       QUESTION.

    Les phrases de reference dataient d'un probleme d'astronomie, resolu
    depuis. Celles qui cassent maintenant sont celles de la recherche de
    fichiers — « impots » entendu « empeaux », « casquette » entendu
    « cascade ».
    """
    from enregistrer_voix import PHRASES

    plat = " ".join(PHRASES).lower()
    for mot in ("impôts", "imposition", "carte d'identité", "casquette", "fichier"):
        assert mot in plat, mot


def test_la_commande_soufflee_est_celle_qu_on_veut_voir_tapee():
    """⚠️ UN OUTIL QUI SOUFFLE UNE COMMANDE DOIT SOUFFLER LA BONNE.

    `enregistrer_voix` finissait par « uv run python scripts/bench_whisper.py »,
    sans `MODELES`. Suivi tel quel, ce conseil fait telecharger `medium` —
    1,5 Go et une longue attente pour un modele qui ne tiendra pas sur 8 Go a
    cote du reste. L'outil contredisait la consigne.
    """
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent
    for fichier in ("scripts/enregistrer_voix.py", "scripts/bench_whisper.py"):
        texte = (racine / fichier).read_text()
        for ligne in texte.splitlines():
            # On ne regarde que les lignes qui PROPOSENT de lancer la mesure,
            # pas celles qui parlent du fichier ou passent « --associer ».
            if "bench_whisper.py" not in ligne or "--associer" in ligne:
                continue
            if "uv run python scripts/bench_whisper.py" not in ligne:
                continue
            assert "MODELES" in ligne, f"{fichier} : {ligne.strip()}"


# ── La ventilation par theme ──────────────────────────────────────────────
def test_chaque_phrase_de_reference_a_un_theme():
    """⚠️ UNE PHRASE SANS THEME DISPARAIT DE LA VENTILATION.

    Elle compterait dans la moyenne et nulle part ailleurs — donc elle
    pourrait faire pencher la decision sans qu'on voie ou.
    """
    from enregistrer_voix import PHRASES, THEMES

    assert [p for p in PHRASES if p not in THEMES] == []


def test_le_theme_survit_a_la_ponctuation():
    """Le .txt ecrit sur le disque peut differer de la constante d'une
    apostrophe. Un theme perdu pour une virgule ferait disparaitre une ligne
    du tableau sans rien dire."""
    from enregistrer_voix import theme_de

    assert theme_de("Ouvre ce fichier.") == "fichiers"
    assert theme_de("ouvre ce fichier") == "fichiers"
    assert theme_de("  OUVRE, CE FICHIER !  ") == "fichiers"
    assert theme_de("une phrase que personne n'a enregistree") == "autre"


def test_la_precision_par_theme_se_calcule_separement():
    """⚠️ C'EST CE CHIFFRE QUI DECIDE, PAS LA MOYENNE.

    Mesure faite sur la machine : `small` en beam 5 rend 80 % de mots justes
    AU TOTAL et 100 % sur les six phrases de fichiers. Les phrases
    d'astronomie tirent la moyenne vers le bas alors qu'elles repondent a un
    probleme resolu depuis.
    """
    from bench_whisper import Resultat

    r = Resultat("small", 5, themes={"fichiers": [46, 0], "connaissance": [40, 10]})

    assert r.precision_du_theme("fichiers") == 1.0
    assert r.precision_du_theme("connaissance") == 0.75
    assert r.precision_du_theme("absent") is None


def test_un_theme_sans_mot_ne_divise_pas_par_zero():
    from bench_whisper import Resultat

    assert Resultat("base", 1, themes={"vide": [0, 0]}).precision_du_theme("vide") is None


def test_une_precision_par_theme_ne_descend_jamais_sous_zero():
    """Whisper peut rendre PLUS de mots que la phrase n'en contient — une
    repetition en boucle. Le taux d'erreur depasse alors 100 %, et une
    precision negative dans un tableau ne veut rien dire."""
    from bench_whisper import Resultat

    r = Resultat("base", 1, themes={"fichiers": [10, 25]})

    assert r.precision_du_theme("fichiers") == 0.0
