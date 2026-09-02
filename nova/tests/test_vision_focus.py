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


# ⚠️ LA RETENUE EST UN ETAT DE MODULE, ET ELLE FUIT ENTRE LES BANCS.
#
# Le meme piege que `_derniere_activite` dans l'indexation : un banc qui
# retient une image la laisse en place pour tous les suivants, qui passent —
# ou tombent — pour la mauvaise raison. La remise a zero vit desormais dans
# `conftest.py`, ou elle vaut pour TOUS les fichiers de bancs : celui-ci
# n'etait pas le seul a retenir une image, seulement le seul a y penser.


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
#  ⚠️ « OUVRE LA PHOTO » — LE DETERMINANT EST DETRUIT EN AMONT
# ══════════════════════════════════════════════════════════════════════════
def test_deux_fichiers_identiques_ne_bloquent_pas_l_ouverture():
    """⚠️ DEUX EXEMPLAIRES DE LA MEME PHOTO NE SONT PAS UNE AMBIGUITE.

    Releve sur la machine : `alo.JPG` et `IMG_8156.JPG` sont la meme image,
    donc la meme description, donc deux scores a 100 %. La marge n'etait
    jamais atteinte et Nova n'ouvrait rien — alors que n'importe laquelle des
    deux etait la bonne reponse.
    """
    from nova.vision.catalogue import Entree
    from nova.vision.regard import _ouvrir_si_evident

    meme = "une main tient une casquette blanche sur une table"
    ouvertes: list[str] = []
    trouvees = [
        (Entree("/img.JPG", "img.JPG", 2.0, 1, meme), 1.0),
        (Entree("/alo.JPG", "alo.JPG", 1.0, 1, meme), 1.0),
        (Entree("/doc.png", "doc.png", 1.0, 1, "un document"), 0.1),
    ]

    import nova.outils as outils

    original = outils.executer_outil
    outils.executer_outil = lambda nom, **kw: ouvertes.append(kw["chemin"])
    try:
        assert _ouvrir_si_evident(trouvees)
    finally:
        outils.executer_outil = original

    assert ouvertes == ["/img.JPG"]


def test_ouvre_la_photo_designe_l_image_en_tete(image):
    """⚠️ LE DETERMINANT N'EXISTE DEJA PLUS A CET ETAGE.

    `intentions.BRUIT_CIBLE` retire « la » — c'est ce qui fait marcher
    « ouvre l'application Chrome ». Consequence : « ouvre LA photo » et
    « ouvre Photos » arrivent tous deux comme « photo ».

    Releve en conditions reelles : Nova venait de trouver IMG_8156.JPG, on
    lui dit « ouvre la photo », et elle a ouvert l'APPLICATION Photos de
    macOS. Correct du point de vue du catalogue, absurde du point de vue de
    la conversation. Le contexte tranche ou la grammaire ne le peut plus.
    """
    from nova.vision.regard import image_en_tete_pour

    assert image_en_tete_pour("photo") is None, "sans image en tete, l'application gagne"
    assert image_en_tete_pour("Photos") is None

    focus.retenir(image)

    assert image_en_tete_pour("photo") == image
    assert image_en_tete_pour("Photos") == image


def test_un_nom_d_application_reel_n_est_jamais_detourne(image):
    """Seuls les mots qui ne designent QU'une image comptent. « Roblox » ou
    « Chrome » restent des applications, image en tete ou non."""
    from nova.vision.regard import image_en_tete_pour

    focus.retenir(image)

    for nom in ("Roblox", "Google Chrome", "Photo Booth", "Aperçu", "Finder"):
        assert image_en_tete_pour(nom) is None, nom


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

    regard.bloc("trouve-moi l'image où je code l'interface de mon application")
    # Nova ne nomme plus l'image trouvee : la preuve est dans la retenue,
    # celle que « analyse-la » va justement consulter.
    retenue = focus.derniere("image")
    assert retenue is not None and retenue.chemin.name == "capture-code.png"

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
    regard.bloc("et celle avec la porsche")

    # Nova ne nomme plus l'image : c'est la retenue qui dit de quoi on parle
    # maintenant — et c'est elle que la phrase suivante consultera.
    retenue = focus.derniere("image")
    assert retenue is not None and retenue.chemin.name == "porsche.png"


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ TRANSCRIPTION REELLE, TELLE QUE WHISPER L'A RENDUE.
        #
        # Releve sur la machine : Nova venait de trouver et d'OUVRIR la bonne
        # image, on lui dit « decris-moi la photo », et elle a decrit une
        # autre image — celle du dessus de la pile.
        "décri-moi la Photos",
        "décris-moi la photo",
        "tu peux me décrire cette image",
        "c'est quoi cette photo",
        "analyse l'image",
    ],
)
def test_decris_moi_la_photo_designe_celle_qu_on_vient_d_ouvrir(
    tmp_path, monkeypatch, phrase
):
    """⚠️ LE PRONOM N'EST PAS LA SEULE FACON DE REPRENDRE.

    « analyse-LA » etait couvert. « decris-moi LA PHOTO » ne l'etait pas : le
    determinant est separe du pronom, et `_PRONOM_IMAGE` n'exige un enclitique
    que pour ecarter l'article « la ». Ici le mot d'image est bien present —
    il ne designe simplement rien de plus precis que ce dont on vient de
    parler.

    Meme defaut que « ouvre la photo » → application Photos, corrige a l'etage
    de l'OUVERTURE et jamais applique a celui du REGARD.
    """
    from nova.vision import Observation, moteur, regard
    from nova.vision import images as vimg

    ancienne = tmp_path / "casquette.JPG"
    ancienne.write_bytes(PNG)
    recente = tmp_path / "courriel.png"
    recente.write_bytes(PNG)

    monkeypatch.setattr(vimg, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))

    class MoteurDeBanc:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            return Observation(
                source=Path(cible), description=f"vue de {Path(cible).name}"
            )

    monkeypatch.setattr(moteur, "MoteurOllama", MoteurDeBanc)

    focus.retenir(ancienne, description="une main tient une casquette", origine="recherche")

    vu = regard.bloc(phrase)

    assert "casquette.JPG" in vu, phrase
    assert "courriel.png" not in vu, "surtout pas la plus recente du dossier"


@pytest.mark.parametrize(
    "phrase",
    [
        "décris la dernière image que j'ai transférée",
        "analyse la nouvelle photo",
        "c'est quoi la photo que je viens de recevoir",
    ],
)
def test_designer_le_dossier_l_emporte_sur_l_image_retenue(tmp_path, monkeypatch, phrase):
    """⚠️ LE MEME DEFAUT, DANS L'AUTRE SENS.

    Elargir la reprise a « la photo » risquait de faire capter par l'image
    retenue toute phrase qui la mentionne, pendant les dix minutes ou elle
    reste en memoire. « la DERNIERE image » designe le dossier : ces mots-la
    l'emportent sur ce qu'on tient en main.
    """
    from nova.vision import Observation, moteur, regard
    from nova.vision import images as vimg

    ancienne = tmp_path / "casquette.JPG"
    ancienne.write_bytes(PNG)
    recente = tmp_path / "courriel.png"
    recente.write_bytes(PNG)

    monkeypatch.setattr(vimg, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))

    class MoteurDeBanc:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            return Observation(
                source=Path(cible), description=f"vue de {Path(cible).name}"
            )

    monkeypatch.setattr(moteur, "MoteurOllama", MoteurDeBanc)

    focus.retenir(ancienne, description="une main tient une casquette", origine="recherche")

    vu = regard.bloc(phrase)

    assert "courriel.png" in vu, phrase


# ══════════════════════════════════════════════════════════════════════════
#  TROIS FACONS DE DESIGNER LA MEME PHOTO — DEUX PARTAIENT AU CATALOGUE
#
#  Releve en conditions reelles, juste apres que Nova ait annonce deux photos
#  de casquette :
#
#      « ouvre la premiere »
#      → « "premiere" peut designer "Grapher", "Print Center" ou
#         "Preview". Laquelle ? »
#
#      « ouvre la photo ou je tiens une casquette »
#      → « Je ne trouve pas d'application "Photos ou je tiens une
#         casquette" sur cette machine. »
#
#  Deux reponses exactes du point de vue du catalogue d'applications, et
#  absurdes du point de vue de la conversation : Nova venait de nommer ces
#  photos elle-meme.
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def deux_photos_annoncees(tmp_path):
    """L'etat exact ou la conversation se trouvait : deux photos retenues."""
    from nova.vision import focus

    premiere = tmp_path / "IMG_8156.JPG"
    seconde = tmp_path / "IMG_9001.JPG"
    for fichier in (premiere, seconde):
        fichier.write_bytes(PNG)
    focus.retenir(
        premiere,
        description="une main tenant une casquette blanche",
        origine="recherche",
        genre="image",
        demande="une casquette blanche",
        liste=(premiere, seconde),
    )
    return premiere, seconde


def test_le_rang_designe_la_photo_et_non_une_application(deux_photos_annoncees):
    """⚠️ LE RANG ETAIT COMPRIS, PUIS JETE.

    `rang_demande` rendait bien 1 pour « la premiere ». Mais seul le resolveur
    de FICHIERS le consultait, et il ne regarde qu'une retenue de genre
    « fichier » : apres une recherche d'IMAGE la reponse etait toujours
    `None`, et la cible partait au catalogue des applications.
    """
    from nova.vision.regard import image_en_tete_pour

    premiere, seconde = deux_photos_annoncees

    assert image_en_tete_pour("première") == premiere
    assert image_en_tete_pour("deuxième") == seconde
    assert image_en_tete_pour("dernière") == seconde


def test_un_rang_hors_liste_ne_rabat_pas_sur_la_plus_proche(deux_photos_annoncees):
    """Meme regle que cote fichiers : « la cinquieme » quand il y en a deux
    est une meconnaissance, pas une approximation. Ouvrir la deuxieme serait
    une reussite apparente sur une photo que personne n'a demandee."""
    from nova.vision.regard import image_en_tete_pour

    assert image_en_tete_pour("troisième") is None


def test_les_mots_de_la_demande_designent_la_photo(deux_photos_annoncees):
    """⚠️ ON COMPARAIT AU NOM DU FICHIER, QUI N'EST JAMAIS CE QU'ON DIT.

    « la photo ou je tiens une casquette » n'a aucun mot commun avec
    « IMG_8156.JPG », et ne peut pas en avoir : la personne n'a jamais entendu
    ce nom. Ce qu'elle redit, c'est SA PROPRE DEMANDE — celle qui a servi a
    trouver la photo. La retenue la garde desormais.
    """
    from nova.vision.regard import image_en_tete_pour

    premiere, _ = deux_photos_annoncees

    assert image_en_tete_pour("photo où je tiens une casquette") == premiere
    assert image_en_tete_pour("casquette blanche") == premiere


def test_un_vrai_nom_d_application_va_toujours_au_catalogue(deux_photos_annoncees):
    """⚠️ LA GARDE QUI REND TOUT LE RESTE ACCEPTABLE.

    Rendre l'image retenue des qu'il y en a une detournerait « ouvre Chrome »
    pendant dix minutes. Il faut que la cible recoupe REELLEMENT ce dont on
    vient de parler.
    """
    from nova.vision.regard import image_en_tete_pour

    assert image_en_tete_pour("Chrome") is None
    assert image_en_tete_pour("Safari") is None
    assert image_en_tete_pour("Photos") is not None, "« Photos » seul reste ambigu"


def test_sans_photo_retenue_le_rang_ne_designe_rien(tmp_path):
    """Hors d'une conversation sur une image, « la premiere » ne veut rien
    dire — et doit suivre son cours normal vers le catalogue."""
    from nova.vision.regard import image_en_tete_pour

    assert image_en_tete_pour("première") is None
