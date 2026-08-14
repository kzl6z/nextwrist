"""L'enregistreur des phrases de reference.

CE QUI EST TESTE, ET CE QUI NE PEUT PAS L'ETRE

La capture micro demande un micro : elle est isolee dans `Micro`, et aucun
test ne la couvre. Tout le reste — ecriture WAV, appariement audio/texte,
numerotation — se teste normalement, et c'est la que sont les fautes qui
rendraient la mesure fausse sans le dire.

Le pire defaut possible ici serait un .wav et un .txt qui ne correspondent
pas : le banc mesurerait alors un ecart entre une phrase et une AUTRE, et
condamnerait un modele qui n'a rien fait de mal.
"""

import wave

import pytest

from enregistrer_voix import PHRASES, TAUX, duree_secondes, ecrire_wav, prochain_numero


def pcm(secondes: float) -> bytes:
    """Du silence de la duree demandee, en PCM 16 bits mono."""
    return b"\0\0" * int(TAUX * secondes)


# ── L'ecriture WAV ────────────────────────────────────────────────────────


def test_le_wav_ecrit_est_relisible(tmp_path):
    chemin = tmp_path / "01.wav"
    ecrire_wav(chemin, pcm(1.0))

    with wave.open(str(chemin), "rb") as f:
        assert f.getnchannels() == 1, "Whisper attend du mono"
        assert f.getsampwidth() == 2, "16 bits"
        assert f.getframerate() == TAUX
        assert f.getnframes() == TAUX


def test_le_dossier_est_cree_au_besoin(tmp_path):
    chemin = tmp_path / "pas" / "encore" / "la" / "01.wav"
    ecrire_wav(chemin, pcm(0.5))
    assert chemin.exists()


def test_la_duree_se_calcule_juste():
    assert duree_secondes(pcm(2.0)) == pytest.approx(2.0)
    assert duree_secondes(b"") == 0.0


# ── La numerotation ───────────────────────────────────────────────────────


def test_la_numerotation_commence_a_un(tmp_path, monkeypatch):
    import enregistrer_voix

    monkeypatch.setattr(enregistrer_voix, "DOSSIER", tmp_path)
    assert prochain_numero() == 1


def test_une_seance_reprend_ou_elle_s_est_arretee(tmp_path, monkeypatch):
    """On doit pouvoir en faire cinq aujourd'hui et cinq demain.

    Sans ca, relancer le script ecraserait les enregistrements existants —
    et on s'en apercevrait seulement en voyant le banc mesurer trois phrases
    au lieu de dix.
    """
    import enregistrer_voix

    monkeypatch.setattr(enregistrer_voix, "DOSSIER", tmp_path)
    for numero in (1, 2, 3):
        ecrire_wav(tmp_path / f"{numero:02d}.wav", pcm(0.5))
    assert prochain_numero() == 4


def test_un_fichier_mal_nomme_ne_casse_pas_la_numerotation(tmp_path, monkeypatch):
    import enregistrer_voix

    monkeypatch.setattr(enregistrer_voix, "DOSSIER", tmp_path)
    ecrire_wav(tmp_path / "01.wav", pcm(0.5))
    ecrire_wav(tmp_path / "essai-du-soir.wav", pcm(0.5))
    assert prochain_numero() == 2


# ── Les phrases de reference ──────────────────────────────────────────────


def test_il_y_a_assez_de_phrases_pour_trancher():
    """En dessous de huit, un mot rate deplace trop le pourcentage."""
    assert len(PHRASES) >= 8


def test_les_phrases_couvrent_les_echecs_constates():
    """Mesurer sur des phrases faciles ne dirait rien de ce qui ne va pas."""
    ensemble = " ".join(PHRASES).lower()
    for attendu in ("diamètre", "planètes", "trou noir", "aznavour"):
        assert attendu in ensemble, f"« {attendu} » manque : c'est un echec releve en reel"


def test_les_phrases_couvrent_aussi_ce_qui_marche():
    """Un changement de modele ne doit pas casser ce qui fonctionne deja."""
    ensemble = " ".join(PHRASES).lower()
    assert "quelle heure" in ensemble
    assert "quel jour" in ensemble


def test_aucune_phrase_en_double():
    """Deux fois la meme phrase pese double dans la moyenne sans rien apporter."""
    assert len(set(PHRASES)) == len(PHRASES)
