"""La borne d'`ouvrir_fichier`, et l'arbitrage image / fichier.

⚠️ CE BANC EXISTE PARCE QUE CETTE FONCTIONNALITE VOIT TOUT LE DISQUE.

Retrouver un fichier ne rend qu'un nom. L'OUVRIR est une action, et `open`
sur un chemin non verifie ouvre n'importe quoi — un script, une application,
un fichier de clef. C'est le seul endroit du module ou une erreur se paie.
"""

from __future__ import annotations

import pytest

from nova.outils.fichiers import FichierRefuse, borner


@pytest.fixture
def maison(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "releve.pdf").write_text("x")
    return tmp_path


def test_un_fichier_de_la_maison_s_ouvre(maison):
    cible = borner(str(maison / "Documents" / "releve.pdf"), (maison,))

    assert cible.name == "releve.pdf"


def test_un_chemin_hors_des_racines_est_refuse(maison, tmp_path_factory):
    ailleurs = tmp_path_factory.mktemp("ailleurs")
    (ailleurs / "secret.pdf").write_text("x")

    with pytest.raises(FichierRefuse):
        borner(str(ailleurs / "secret.pdf"), (maison,))


def test_la_remontee_par_deux_points_est_refusee(maison, tmp_path_factory):
    """⚠️ COMPARER DES CHAINES NE SUFFIRAIT PAS.

    `<maison>/Documents/../../ailleurs/x` COMMENCE bien par `<maison>`. C'est
    le meme piege que `LireFichier` et `vision/images.py:resoudre` : on resout
    reellement avant de comparer, sinon la borne est decorative.
    """
    ailleurs = tmp_path_factory.mktemp("dehors")
    (ailleurs / "vole.pdf").write_text("x")
    detour = maison / "Documents" / ".." / ".." / ailleurs.name / "vole.pdf"

    with pytest.raises(FichierRefuse):
        borner(str(detour), (maison,))


def test_un_fichier_sensible_de_la_maison_est_refuse(maison):
    """Etre dans la racine ne suffit pas : la seconde condition tient seule."""
    (maison / ".env").write_text("CLE=1")

    with pytest.raises(FichierRefuse):
        borner(str(maison / ".env"), (maison,))


def test_un_fichier_absent_est_refuse_avec_son_nom(maison):
    with pytest.raises(FichierRefuse, match="absent.pdf"):
        borner(str(maison / "Documents" / "absent.pdf"), (maison,))


def test_sans_racine_configuree_on_refuse_tout(maison):
    """Une borne vide interdit tout — jamais l'inverse."""
    with pytest.raises(FichierRefuse):
        borner(str(maison / "Documents" / "releve.pdf"), ())


def test_les_deux_outils_sont_enregistres():
    from nova.core import contrats
    from nova.core.registre import Registre
    from nova.outils.fichiers import enregistrer_outils_fichiers

    registre = Registre("outil")
    noms = enregistrer_outils_fichiers(registre)

    assert set(noms) == {"rechercher_fichier", "ouvrir_fichier"}
    # ⚠️ LE NIVEAU DIT LA VERITE : chercher LIT, ouvrir AGIT.
    assert registre.exiger("rechercher_fichier").niveau == contrats.LECTURE
    assert registre.exiger("ouvrir_fichier").niveau == contrats.REVERSIBLE
    # Enregistrer deux fois ne double pas.
    assert enregistrer_outils_fichiers(registre) == ()


# ══════════════════════════════════════════════════════════════════════════
#  L'ARBITRAGE — IMAGE OU FICHIER
# ══════════════════════════════════════════════════════════════════════════
def test_une_recherche_de_papier_ne_part_pas_dans_le_catalogue_d_images():
    """⚠️ « DANS MES PHOTOS MON RELEVE DE COMPTE » CONTIENT LE MOT « PHOTOS ».

    C'est la phrase fondatrice, et elle est piegee : le catalogue d'images la
    prendrait pour lui et chercherait une casquette. Le mot « releve » est un
    signal bien plus specifique que « photos ».
    """
    from nova.fichiers.trouver import demande_de_fichier

    phrase = (
        "peux-tu me retrouver dans mes fichiers ou dans mes photos mon "
        "releve de compte de 2024"
    )

    assert demande_de_fichier(phrase)


def test_une_recherche_d_image_par_son_contenu_reste_aux_images():
    """« l'image avec une casquette » decrit un CONTENU : c'est le catalogue
    d'images qui repond, et la recherche de fichiers doit s'abstenir."""
    from nova.fichiers.trouver import demande_de_fichier
    from nova.vision.regard import demande_de_retrouver

    phrase = "retrouve-moi l'image avec une casquette tenue dans une main"

    assert not demande_de_fichier(phrase)
    assert demande_de_retrouver(phrase)


def test_le_prompt_ne_porte_jamais_les_deux_recherches(tmp_path, monkeypatch):
    """⚠️ DEUX RECHERCHES CONCURRENTES DANS UN PROMPT EN FONT CHOISIR UNE AU
       HASARD.

    Ce banc passe par `build_system_prompt`, donc par le vrai branchement :
    verifier les deux declencheurs separement ne protegerait rien du tout.
    """
    from nova import orchestrator
    from nova.documents import search as document_search
    from nova.fichiers import trouver
    from nova.memory import conversations, facts

    (tmp_path / "releve-compte-2024.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    # La base n'est pas lancee pendant les bancs. Sans ces doubles, le
    # montage du prompt attend le pool pendant 30 s par appel — soit une
    # minute pour un banc qui ne parle ni de memoire ni de documents.
    monkeypatch.setattr(document_search, "search", lambda *a, **k: [])
    monkeypatch.setattr(facts, "list_facts", lambda *a, **k: [])
    monkeypatch.setattr(conversations, "derniers_echanges", lambda *a, **k: [])

    appels: list[str] = []

    def regard_qui_compte(texte):
        appels.append(texte)
        return "## Ce que Nova voit\n\nune casquette"

    from nova.vision import regard

    monkeypatch.setattr(regard, "bloc", regard_qui_compte)

    prompt, _ = orchestrator.build_system_prompt(
        "retrouve dans mes photos mon releve de compte de 2024"
    )

    assert "releve-compte-2024.pdf" in prompt
    assert "casquette" not in prompt
    assert appels == [], "le regard ne doit meme pas etre consulte"
