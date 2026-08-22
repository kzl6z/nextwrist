"""Suivre une image d'une phrase a l'autre.

CE QUE CE BANC PROTEGE

    — « trouve-moi l'image ou je code l'interface »
      « capture-code.png — je viens de l'ouvrir. »
    — « analyse-la »
      ← quelle image ?

Sans memoire de ce qui vient d'etre designe, « la » ne renvoyait a rien :
Nova retombait sur la plus recente du dossier, c'est-a-dire presque toujours
une AUTRE image que celle qu'elle venait de trouver et d'ouvrir.

⚠️ ET LA REPONSE ETAIT JUSTE.

Juste sur une image que personne n'avait demandee. C'est la forme d'erreur la
plus couteuse : rien ne signale qu'on parle d'autre chose, ni dans les
journaux ni dans la reponse.

⚠️ CE BANC PROTEGE AUSSI LE CONTRAIRE.

Une image retenue le reste dix minutes. Si elle s'imposait a toute phrase
contenant « la » — un article, le mot le plus frequent du francais — elle
detournerait toute la conversation qui suit. D'ou l'exigence d'un pronom
ENCLITIQUE ou d'un demonstratif seul.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova.vision import focus

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db4000000004945" "4e44ae426082"
)


@pytest.fixture(autouse=True)
def sans_retenue():
    """⚠️ LA RETENUE EST UN ETAT DE MODULE. ELLE FUIT ENTRE LES BANCS.

    Le meme piege que `_derniere_activite` dans l'indexation : un banc qui
    retient une image la laisse en place pour tous les suivants, qui passent
    alors pour la mauvaise raison.
    """
    focus.oublier()
    yield
    focus.oublier()


@pytest.fixture
def image(tmp_path):
    cible = tmp_path / "capture-code.png"
    cible.write_bytes(PNG)
    return cible


# ══════════════════════════════════════════════════════════════════════════
#  LA RETENUE
# ══════════════════════════════════════════════════════════════════════════
def test_rien_n_est_retenu_au_depart():
    assert focus.derniere() is None


def test_une_image_retenue_se_retrouve(image):
    focus.retenir(image, description="un ecran de code", origine="recherche")

    retenue = focus.derniere()

    assert retenue is not None
    assert retenue.chemin == image
    assert retenue.origine == "recherche"


def test_une_retenue_expire(image, monkeypatch):
    """⚠️ AU BOUT DE DIX MINUTES, « LA » DESIGNE AUTRE CHOSE.

    Dans la tete de celui qui parle, en tout cas — et se tromper en silence
    coute plus cher que redemander.
    """
    focus.retenir(image)
    monkeypatch.setattr(focus, "DUREE_S", -1.0)

    assert focus.derniere() is None


def test_une_image_disparue_n_est_plus_retenue(image):
    """Le fichier a pu etre deplace entre-temps. Le verifier ici evite un
    echec plus loin, sur un chemin qui semblera sorti de nulle part."""
    focus.retenir(image)
    image.unlink()

    assert focus.derniere() is None


# ══════════════════════════════════════════════════════════════════════════
#  LA REPRISE — « analyse-la »
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase", ["analyse-la", "décris-la", "regarde-la", "montre-la"]
)
def test_un_pronom_enclitique_reprend_l_image_retenue(image, phrase):
    from nova.vision.regard import parle_d_une_image

    assert not parle_d_une_image(phrase), "sans image en tete, rien ne se declenche"

    focus.retenir(image)

    assert parle_d_une_image(phrase), "avec une image en tete, le pronom suffit"


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ « LA » EST AUSSI UN ARTICLE — LE MOT LE PLUS FREQUENT DU FRANCAIS.
        #
        # L'accepter ferait basculer vers l'image retenue toute phrase qui le
        # contient, pendant les dix minutes ou une image est en memoire.
        "regarde la voiture qui passe",
        "analyse la situation",
        "quelle heure est-il",
        "parle-moi de Mars",
    ],
)
def test_un_article_ne_reprend_pas(image, phrase):
    focus.retenir(image)

    from nova.vision.regard import parle_d_une_image

    assert not parle_d_une_image(phrase), phrase


def test_nommer_une_autre_image_l_emporte_sur_la_retenue(image, tmp_path, monkeypatch):
    """« decris la derniere image » designe le dossier, pas ce qu'on tenait."""
    from nova.vision import images as vimg
    from nova.vision.regard import _reprise_d_image

    focus.retenir(image)
    monkeypatch.setattr(vimg, "dossiers_surveilles", lambda: (tmp_path,))

    assert not _reprise_d_image("décris la dernière image")


# ══════════════════════════════════════════════════════════════════════════
#  L'OUVERTURE AUTOMATIQUE
# ══════════════════════════════════════════════════════════════════════════
def test_une_correspondance_nette_ouvre_l_image():
    from nova.vision.catalogue import Entree
    from nova.vision.regard import _ouvrir_si_evident

    ouvertes: list[str] = []
    trouvees = [
        (Entree("/a.png", "a.png", 1.0, 1, "une porsche rouge"), 1.0),
        (Entree("/b.png", "b.png", 1.0, 1, "un document"), 0.2),
    ]

    import nova.outils as outils

    original = outils.executer_outil
    outils.executer_outil = lambda nom, **kw: ouvertes.append(kw["chemin"])
    try:
        assert _ouvrir_si_evident(trouvees)
    finally:
        outils.executer_outil = original

    assert ouvertes == ["/a.png"]


def test_deux_candidats_a_egalite_n_ouvrent_rien():
    """⚠️ MEME GARDE-FOU QUE POUR LES APPLICATIONS.

    Une ressemblance parfaite avec deux fichiers n'en designe aucun. En
    ouvrir un au hasard serait une reussite apparente — plus difficile a
    deboguer qu'un echec.
    """
    from nova.vision.catalogue import Entree
    from nova.vision.regard import _ouvrir_si_evident

    trouvees = [
        (Entree("/a.png", "a.png", 1.0, 1, "une capture d'ecran"), 0.60),
        (Entree("/b.png", "b.png", 1.0, 1, "une capture d'ecran"), 0.55),
    ]

    assert not _ouvrir_si_evident(trouvees)


def test_une_ouverture_impossible_n_empeche_pas_de_repondre():
    """Une image qu'on n'a pas su ouvrir ne doit pas empecher Nova de DIRE
    qu'elle l'a trouvee."""
    import nova.outils as outils
    from nova.vision.catalogue import Entree
    from nova.vision.regard import _ouvrir_si_evident

    original = outils.executer_outil

    def casse(nom, **kw):
        raise RuntimeError("macOS seulement")

    outils.executer_outil = casse
    try:
        assert not _ouvrir_si_evident(
            [(Entree("/a.png", "a.png", 1.0, 1, "une porsche"), 1.0)]
        )
    finally:
        outils.executer_outil = original


# ══════════════════════════════════════════════════════════════════════════
#  LA CONVERSATION COMPLETE
# ══════════════════════════════════════════════════════════════════════════
def test_trouver_puis_analyser_designe_la_meme_image(tmp_path, monkeypatch):
    """LE BANC CENTRAL : la sequence que l'utilisateur a decrite.

        « trouve-moi l'image ou je code l'interface »   → capture-code.png
        « analyse-la »                                  → capture-code.png
    """
    from nova.vision import Observation, moteur, regard
    from nova.vision import catalogue as cat
    from nova.vision import images as vimg

    for nom in ("capture-code.png", "recente.png"):
        (tmp_path / nom).write_bytes(PNG)

    catalogue = cat.Catalogue(tmp_path / "cat.json")
    for nom, description in [
        ("capture-code.png", "un ecran affichant l'interface d'une application"),
        ("recente.png", "un document avec du texte"),
    ]:
        etat = (tmp_path / nom).stat()
        catalogue.ajouter(
            cat.Entree(
                str(tmp_path / nom), nom, etat.st_mtime, etat.st_size, description,
                origine="en",
            )
        )
    catalogue.enregistrer()

    monkeypatch.setattr(cat, "fichier_par_defaut", lambda: tmp_path / "cat.json")
    monkeypatch.setattr(vimg, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))

    class MoteurDeBanc:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            return Observation(source=Path(cible), description=f"vue de {Path(cible).name}")

    monkeypatch.setattr(moteur, "MoteurOllama", MoteurDeBanc)

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    trouve = regard.bloc("trouve-moi l'image où je code l'interface de mon application")
    assert "capture-code.png" in trouve

    analyse = regard.bloc("analyse-la")

    assert "capture-code.png" in analyse, "« la » doit designer ce qu'on vient de trouver"
    assert "recente.png" not in analyse, "surtout pas la plus recente du dossier"


def test_une_nouvelle_recherche_par_pronom_change_de_sujet(tmp_path, monkeypatch):
    """« et celle avec la porsche » ne contient aucun mot d'image — et c'est
    une formulation parfaitement naturelle une fois la conversation lancee."""
    from nova.vision import catalogue as cat
    from nova.vision import images as vimg
    from nova.vision import moteur, regard

    for nom in ("capture-code.png", "porsche.png"):
        (tmp_path / nom).write_bytes(PNG)
    catalogue = cat.Catalogue(tmp_path / "cat.json")
    for nom, description in [
        ("capture-code.png", "un ecran affichant une interface"),
        ("porsche.png", "une voiture de sport rouge garee dans une rue"),
    ]:
        etat = (tmp_path / nom).stat()
        catalogue.ajouter(
            cat.Entree(
                str(tmp_path / nom), nom, etat.st_mtime, etat.st_size, description,
                origine="en",
            )
        )
    catalogue.enregistrer()

    monkeypatch.setattr(cat, "fichier_par_defaut", lambda: tmp_path / "cat.json")
    monkeypatch.setattr(vimg, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    focus.retenir(tmp_path / "capture-code.png", origine="recherche")
    suite = regard.bloc("et celle avec la porsche")

    assert "porsche.png" in suite
