"""Ranger dans le dossier du projet ce que Nova vient d'annoncer.

    « retrouve-moi les photos ou je tiens une casquette blanche »
    « J'ai trouve 3 photos. Laquelle veux-tu ? »
    « mets-les dans le dossier du projet »
    « Je deplace 3 fichiers dans le dossier centrale nucleaire ? »
    « oui »

⚠️ C'EST LA SEULE ACTION DE NOVA OU L'ON PEUT PERDRE SANS SAVOIR QUOI.

Le fichier n'est pas detruit, il est ailleurs. En pratique on ne retrouve pas
ce qu'on ne sait pas nommer : trois photos rangees au mauvais endroit sont
perdues, et la difference avec « detruites » n'interesse que les
informaticiens.

La moitie de ces bancs ne verifie donc pas que ca range, mais que ca se
DEFAIT — et que rien ne bouge sans un oui.
"""

from __future__ import annotations

import pytest

from nova.fichiers import creer, ranger

psycopg = pytest.importorskip("psycopg")


def _schema_pret() -> bool:
    from nova.settings import get_settings

    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return (
                conn.execute("SELECT to_regclass('public.deplacements')").fetchone()[0]
                is not None
            )
    except Exception:  # noqa: BLE001
        return False


besoin_de_base = pytest.mark.skipif(
    not _schema_pret(),
    reason="base absente ou migration 006 non appliquee — lance `uv run nova db migrate`",
)


# ══════════════════════════════════════════════════════════════════════════
#  RECONNAITRE — l'article fait toute la difference
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "phrase",
    [
        "mets-les dans le dossier",
        "mets-les dans le dossier du projet",
        "range-les dans le projet",
        "déplace-les dans le dossier",
        "classe tout ça dans le dossier",
        "mets ça dedans",
        "ajoute-les dans le dossier",
    ],
)
def test_les_demandes_de_rangement_sont_reconnues(phrase):
    assert ranger.demande_de_ranger(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ L'ARTICLE INDEFINI ANNONCE CE QUI N'EXISTE PAS ENCORE.
        #
        # « dans UN dossier Photos » demande d'en CREER un. Accepter
        # l'indefini ici volerait sa phrase a `fichiers/creer.py`, et Nova
        # repondrait qu'elle ne sait pas ou ranger quand on lui demandait de
        # creer.
        "range tout dans un dossier Photos",
        "crée un dossier Impôts sur mon bureau",
        # Un seul signal ne suffit pas.
        "mets-moi de la musique",
        "qu'est-ce qu'il y a dans le dossier",
        "ouvre le deuxième",
        "",
    ],
)
def test_ces_phrases_ne_rangent_rien(phrase):
    assert not ranger.demande_de_ranger(phrase), phrase


def test_ranger_et_creer_ne_se_marchent_pas_dessus():
    """⚠️ LES DEUX FAMILLES PORTENT UN VERBE ET LE MOT « DOSSIER ».

    Seul l'article les separe. Si les deux revendiquaient la meme phrase,
    l'ordre des branchements deciderait en silence.
    """
    ranger_ci = "mets-les dans le dossier du projet"
    creer_ci = "range tout dans un dossier Photos"

    assert ranger.demande_de_ranger(ranger_ci)
    assert creer.demande_de_dossier(ranger_ci) is None, "creer doit s'abstenir"

    assert not ranger.demande_de_ranger(creer_ci)
    assert creer.demande_de_dossier(creer_ci) is not None, "creer doit prendre"


@pytest.mark.parametrize(
    "phrase",
    [
        "remets-les où ils étaient",
        "remets-les à leur place",
        "annule le déplacement",
        "remets tout comme avant",
    ],
)
def test_les_demandes_d_annulation_sont_reconnues(phrase):
    assert ranger.demande_d_annuler(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    ["mets-les dans le dossier", "ouvre le deuxième", "quelle heure est-il", ""],
)
def test_ces_phrases_n_annulent_rien(phrase):
    assert not ranger.demande_d_annuler(phrase), phrase


# ══════════════════════════════════════════════════════════════════════════
#  DE BOUT EN BOUT
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def bureau(tmp_path, monkeypatch):
    faux = tmp_path / "Desktop"
    faux.mkdir()
    monkeypatch.setattr(creer, "dossiers_ou_creer", lambda: (faux.resolve(),))
    return faux.resolve()


@pytest.fixture(autouse=True)
def outils_inscrits():
    from nova.outils import registre_outils
    from nova.outils.fichiers import enregistrer_outils_fichiers

    avant = dict(registre_outils._entrees)
    enregistrer_outils_fichiers(registre_outils)
    yield
    registre_outils._entrees = avant


@pytest.fixture
def projet_ecrit(bureau):
    """Un projet a nous, avec son dossier deja sur le Bureau."""
    from nova.contexte import actif
    from nova.db import connection
    from nova.outils.fichiers import EcrireProjet

    with connection() as conn:
        conn.execute("UPDATE projets SET actif = false WHERE actif")
    projet = actif.ouvrir("essai rangement")
    EcrireProjet().executer()
    yield projet
    with connection() as conn:
        conn.execute("DELETE FROM deplacements WHERE projet_id = %s", (projet.id,))
        conn.execute("DELETE FROM projets WHERE id = %s", (projet.id,))


@pytest.fixture
def trois_photos(tmp_path):
    """Trois photos annoncees, dans un dossier a part du Bureau."""
    from nova.vision import focus

    source = tmp_path / "Pictures"
    source.mkdir()
    chemins = []
    for i in range(3):
        photo = source / f"casquette-{i}.png"
        photo.write_bytes(b"\x89PNG" + bytes([i]))
        chemins.append(photo)
    focus.retenir(
        chemins[0], description="une casquette blanche",
        origine="recherche", liste=tuple(chemins), demande="une casquette blanche",
    )
    yield tuple(chemins)
    focus.oublier()


def _dire(texte: str, *, confirme: bool = False) -> dict:
    from fastapi.testclient import TestClient

    from nova.api.app import app

    reponse = TestClient(app).post(
        "/v1/action", json={"texte": texte, "confirme": confirme}
    )
    assert reponse.status_code == 200
    return reponse.json()


@besoin_de_base
def test_ranger_demande_avant_de_deplacer(bureau, projet_ecrit, trois_photos):
    """⚠️ RIEN NE BOUGE SANS UN OUI, ET LA QUESTION DIT COMBIEN.

    Accepter sans savoir ce qui va se passer, c'est accepter au hasard — et
    le portillon ne protege plus rien.
    """
    demande = _dire("mets-les dans le dossier du projet")

    assert demande["etat"] == "a_confirmer"
    assert "3" in demande["message"], "la question doit dire combien de fichiers"
    assert "essai rangement" in demande["message"], "et vers où"
    assert all(photo.exists() for photo in trois_photos), "déplacé sans confirmation"

    fait = _dire("mets-les dans le dossier du projet", confirme=True)

    assert fait["etat"] == "executee", fait["message"]
    dossier = bureau / "essai rangement"
    assert sorted(p.name for p in dossier.glob("*.png")) == [
        "casquette-0.png", "casquette-1.png", "casquette-2.png",
    ]
    assert not any(photo.exists() for photo in trois_photos), "les originaux sont restés"


@besoin_de_base
def test_le_rangement_se_defait(bureau, projet_ecrit, trois_photos):
    """⚠️ C'EST CE QUI FAIT PASSER L'ACTION DE IRREVERSIBLE A CONSEQUENT.

    Sans retour possible, deplacer serait la seule action de Nova qu'aucune
    confirmation ne rendrait acceptable — le bareme n'a pas de niveau
    au-dessus.
    """
    _dire("mets-les dans le dossier du projet", confirme=True)
    assert not trois_photos[0].exists()

    demande = _dire("remets-les où ils étaient")
    assert demande["etat"] == "a_confirmer"
    assert "3" in demande["message"]

    fait = _dire("remets-les où ils étaient", confirme=True)

    assert fait["etat"] == "executee", fait["message"]
    assert all(photo.exists() for photo in trois_photos), "les fichiers ne sont pas revenus"
    assert list((bureau / "essai rangement").glob("*.png")) == []


@besoin_de_base
def test_l_origine_est_enregistree(bureau, projet_ecrit, trois_photos):
    """Sans la trace, « remets-les où ils étaient » n'aurait aucune reponse."""
    _dire("mets-les dans le dossier du projet", confirme=True)

    faits = ranger.a_defaire(projet_ecrit.id)

    assert len(faits) == 3
    assert {f.venait_de for f in faits} == set(trois_photos)


@besoin_de_base
def test_un_nom_deja_pris_n_est_jamais_ecrase(bureau, projet_ecrit, trois_photos):
    """⚠️ DEUX PHOTOS DU MEME NOM VENUES DE DEUX DOSSIERS.

    `shutil.move` ecraserait la premiere sans rien dire, et le fichier serait
    detruit pour de bon — la seule facon, dans tout ce module, de perdre
    vraiment quelque chose.
    """
    dossier = bureau / "essai rangement"
    (dossier / "casquette-0.png").write_bytes(b"celle qui etait deja la")

    fait = _dire("mets-les dans le dossier du projet", confirme=True)

    assert (dossier / "casquette-0.png").read_bytes() == b"celle qui etait deja la"
    assert trois_photos[0].exists(), "l'original a été déplacé sur un nom déjà pris"
    assert "laissé 1" in fait["message"], "Nova doit dire ce qu'elle n'a pas rangé"


@besoin_de_base
def test_sans_rien_d_annonce_nova_ne_range_rien(bureau, projet_ecrit):
    """⚠️ ON NE DEPLACE QUE CE QUE NOVA VIENT D'ANNONCER.

    C'est la borne la plus importante : un outil qui accepterait un chemin
    libre pourrait ranger n'importe quoi.
    """
    from nova.vision import focus

    focus.oublier()

    fait = _dire("mets-les dans le dossier du projet")

    assert fait["etat"] == "echouee"
    assert list((bureau / "essai rangement").glob("*.png")) == []


@besoin_de_base
def test_sans_dossier_de_projet_nova_dit_quoi_faire(bureau, trois_photos):
    """Ranger dans un dossier qui n'existe pas creerait un dossier que
    personne n'a demande, en ayant l'air d'obeir."""
    from nova.contexte import actif
    from nova.db import connection

    with connection() as conn:
        conn.execute("UPDATE projets SET actif = false WHERE actif")
    projet = actif.ouvrir("projet sans dossier")
    try:
        fait = _dire("mets-les dans le dossier du projet", confirme=True)

        assert fait["etat"] == "echouee"
        assert "créer" in fait["message"]
        assert all(photo.exists() for photo in trois_photos)
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM projets WHERE id = %s", (projet.id,))


@besoin_de_base
def test_le_niveau_exige_une_confirmation():
    from nova.core import contrats
    from nova.outils.fichiers import RangerDansLeProjet, RemettreOuIlsEtaient

    assert RangerDansLeProjet.niveau == contrats.CONSEQUENT
    assert RemettreOuIlsEtaient.niveau == contrats.CONSEQUENT
    assert contrats.exige_confirmation(RangerDansLeProjet.niveau)


@besoin_de_base
def test_annuler_deux_fois_ne_refait_pas_le_chemin_a_l_envers(
    bureau, projet_ecrit, trois_photos
):
    """Un deplacement defait est marque : le redemander ne doit rien rejouer."""
    _dire("mets-les dans le dossier du projet", confirme=True)
    _dire("remets-les où ils étaient", confirme=True)

    fait = _dire("remets-les où ils étaient", confirme=True)

    assert fait["etat"] == "echouee"
    assert all(photo.exists() for photo in trois_photos)
