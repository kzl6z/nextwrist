"""Outils, espaces de travail, vision : les briques du noyau.

Le point commun de ces trois familles : elles se declarent dans un registre,
et on doit pouvoir en ajouter une sans toucher a un fichier existant. C'est
la definition operatoire de « extensible ».
"""

from pathlib import Path

import pytest

from nova.core.contrats import Demande
from nova.espaces import choisir_espace, registre_espaces
from nova.outils import LireFichier, registre_outils
from nova.vision import MoteurVision, PasEncoreImplemente, disponible


# ── Outils ────────────────────────────────────────────────────────────────


def test_l_horloge_lit_l_heure_au_lieu_de_l_inventer():
    from datetime import datetime

    horloge = registre_outils.exiger("horloge")
    resultat = horloge.executer(datetime(2026, 8, 2, 14, 30))
    assert resultat["heure"] == "14:30"
    assert resultat["jour"] == "dimanche"
    assert "aout" in resultat["date"]


def test_lire_fichier_reste_dans_le_dossier_de_travail(tmp_path):
    # LA verification qui compte. Sans elle, n'importe quelle demande — ou
    # n'importe quel document que Nova vient de lire — peut atteindre
    # ~/.ssh/id_rsa.
    (tmp_path / "note.txt").write_text("bonjour", encoding="utf-8")
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("mot de passe", encoding="utf-8")

    outil = LireFichier(tmp_path)
    assert outil.executer("note.txt") == "bonjour"

    for evasion in ("../secret.txt", "../../etc/passwd", "./../secret.txt"):
        with pytest.raises(PermissionError):
            outil.executer(evasion)


def test_comparer_les_chaines_n_aurait_pas_suffi(tmp_path):
    # « data/../../.ssh » commence bien par « data/ » : c'est pourquoi le
    # chemin est resolu reellement avant d'etre compare.
    (tmp_path / "sous").mkdir()
    piege = tmp_path / "sous" / ".." / ".." / "ailleurs.txt"
    piege.parent.parent.mkdir(exist_ok=True)
    piege.resolve().write_text("x", encoding="utf-8")
    with pytest.raises(PermissionError):
        LireFichier(tmp_path / "sous").executer("../ailleurs.txt")


def test_un_fichier_absent_le_dit_clairement(tmp_path):
    with pytest.raises(FileNotFoundError, match="n'existe pas"):
        LireFichier(tmp_path).executer("absent.txt")


def test_un_fichier_trop_gros_renvoie_vers_l_ingestion(tmp_path):
    gros = tmp_path / "gros.txt"
    gros.write_text("a" * (LireFichier.TAILLE_MAX + 1), encoding="utf-8")
    with pytest.raises(ValueError, match="ingest"):
        LireFichier(tmp_path).executer("gros.txt")


def test_ajouter_un_outil_ne_demande_de_toucher_a_rien():
    from nova.core.registre import Registre

    registre = Registre("outil")

    @registre.enregistrer
    class Imprimante:
        nom = "imprimante"
        description = "Envoie un document a l'imprimante"
        capacite = "action"

        def executer(self, chemin):
            return f"imprime {chemin}"

    assert registre.exiger("imprimante").executer("a.pdf") == "imprime a.pdf"


# ── Espaces de travail ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("je pars a Tokyo, il me faut un vol", "voyage"),
        ("prepare une soutenance avec des diapos", "presentation"),
        ("il y a un bug dans mon script", "code"),
        ("analyse ces donnees statistiques", "analyse"),
        ("reconnais ce qu'il y a sur cette photo", "vision"),
        ("j'ai un devoir a rendre, il faut que j'apprenne", "etude"),
    ],
)
def test_chaque_espace_reconnait_son_domaine(phrase, attendu):
    espace = choisir_espace(Demande(phrase))
    assert espace is not None and espace.nom == attendu


def test_une_phrase_banale_ne_releve_d_aucun_espace():
    # `None` est une reponse legitime et frequente. Forcer un rattachement
    # peuplerait les espaces de conversations sans rapport.
    for phrase in ("bonjour", "merci", "quelle heure est-il", "oui"):
        assert choisir_espace(Demande(phrase)) is None, phrase


def test_tous_les_espaces_sont_decrits():
    for espace in registre_espaces.tout():
        assert espace.description and espace.capacites


# ── Vision ────────────────────────────────────────────────────────────────


def test_la_vision_dit_qu_elle_n_est_pas_disponible():
    # Un module qui pretend faire quelque chose et ne le fait pas est pire
    # que son absence : on l'appelle, il rend une valeur vide, et on cherche
    # le bug ailleurs.
    assert disponible() is False


def test_chaque_fonction_de_vision_explique_ce_qui_manque():
    moteur = MoteurVision()
    appels = (
        lambda: moteur.decrire(Path("a.png")),
        lambda: moteur.detecter(Path("a.png")),
        lambda: moteur.analyser_video(Path("a.mp4")),
        lambda: moteur.identifier_composants(Path("a.png")),
        lambda: moteur.documenter("condensateur"),
        lambda: moteur.preparer_reconstruction((Path("a.png"),)),
    )
    for appel in appels:
        with pytest.raises(PasEncoreImplemente) as erreur:
            appel()
        # Le message doit dire ce qu'il faudrait, pas seulement « non ».
        assert len(str(erreur.value)) > 40
