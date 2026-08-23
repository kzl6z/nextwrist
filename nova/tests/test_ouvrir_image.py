"""« Ouvre » ne connaissait qu'une seule chose a ouvrir : une application.

LE DEFAUT, RELEVE EN CONDITIONS REELLES

    « ouvre-moi la derniere image que j'ai transferee sur ce PC »
    → Je ne trouve pas d'application « derniere image que j'ai transferee
      sur ce PC » sur cette machine.

Exact, et inutile : le message decrivait ce que Nova avait CHERCHE, pas ce
qu'on lui avait demande. Le verbe « ouvre » est capte par la reconnaissance
d'intention, qui confronte sa cible au catalogue des applications installees
— ou « la derniere image » n'avait aucune chance de figurer.

⚠️ CE BANC PROTEGE SURTOUT CE QUI MARCHAIT DEJA.

La correction la plus simple aurait ete de detecter l'image AVANT le
catalogue. Elle aurait casse « ouvre Photos » : l'application Photos de
macOS porte precisement le mot qui designe une image. C'est le DETERMINANT
qui tranche — « LA photo » contre « Photos » — et se fier a la grammaire
d'une transcription vocale serait un pari.

D'ou un REPLI : le catalogue d'abord, l'image seulement si rien d'installe
ne correspond. Un repli n'enleve rien a ce qui fonctionnait ; il remplace un
echec par une reussite. La moitie des bancs ci-dessous verifie ce non-effet.
"""

from __future__ import annotations

import pytest

from nova.vision.regard import designe_une_image


# ══════════════════════════════════════════════════════════════════════════
#  DESIGNER UNE IMAGE — sans confondre avec une application
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "cible",
    [
        # ⚠️ AVEC LES ACCENTS, ET C'EST LE SUJET.
        #
        # Tous les cas de ce banc etaient ecrits sans accents — comme le
        # motif. Ils passaient donc tous, et le repli ne se declenchait
        # JAMAIS a la voix : Whisper transcrit « dernière », correctement.
        # Un banc ecrit dans le meme angle mort que le code ne teste rien.
        "dernière image que j'ai transférée sur mon PC",
        "la dernière photo",
        "cette capture d'écran",
        "ce cliché",
        # ⚠️ L'ELISION NE MET JAMAIS D'ESPACE.
        #
        # `l'\s+` ne peut pas correspondre a « l'image » — la forme la plus
        # naturelle en francais, et celle que Whisper produit. Releve en
        # conditions reelles : « peux-tu ouvrir l'image … » repartait vers le
        # catalogue des applications. Aucun cas de ce banc n'utilisait
        # l'elision, alors que c'est la forme courante.
        "l'image",
        "l'image à l'eau. pengé sur pégé",   # transcription reelle, massacree
        "ta capture d'écran",
        "derniere image que j'ai transferee sur ce PC",
        "la derniere photo",
        "cette image",
        "ma capture d'ecran",
        "mes photos",
        "la photo",
        "IMG_7826-2.png",
        "~/Downloads/casquette.jpg",
        "photos/piece.png",
    ],
)
def test_une_cible_qui_designe_un_fichier(cible):
    assert designe_une_image(cible), cible


@pytest.mark.parametrize(
    "cible",
    [
        # ⚠️ DES APPLICATIONS macOS REELLES, ET C'EST TOUT LE PIEGE.
        #
        # « Photos » et « Photo Booth » portent le mot qui designe une image.
        # Sans determinant, un nom d'image devient un nom propre.
        "Photos",
        "Photo Booth",
        "Aperçu",
        "Roblox",
        "Google Chrome",
        "Capture",          # l'utilitaire macOS de capture d'ecran
        "",
        # ⚠️ ARTICLE INDEFINI : AUCUN FICHIER PRECIS N'EST DESIGNE.
        #
        # Ce cas a d'abord ete ecrit du mauvais cote — je l'attendais parmi
        # les designations de fichier. Le banc a eu raison contre moi :
        # « un cliché » ne designe rien de precis, et le confondre avec
        # « ce cliché » ouvrirait un fichier au hasard sur une phrase qui
        # n'en nommait aucun.
        "un cliché",
        "une photo",
    ],
)
def test_une_cible_qui_designe_une_application(cible):
    assert not designe_une_image(cible), cible


def test_un_adjectif_intercale_ne_casse_pas_la_designation():
    """« la DERNIERE photo », « cette PETITE image » : le determinant est
    separe de l'objet, et c'est la regle plutot que l'exception."""
    assert designe_une_image("la toute derniere photo")
    assert designe_une_image("cette petite image")


# ══════════════════════════════════════════════════════════════════════════
#  L'AIGUILLAGE — catalogue d'abord, image en repli
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def catalogue(monkeypatch):
    """Un catalogue macOS realiste. Sans lui, `installees()` rend un tuple
    vide et TOUTE cible ressort « inverifiable » — le repli ne serait jamais
    exerce, et le banc passerait sans rien verifier."""
    from nova.outils import applications

    installees = ("Roblox", "Photos", "Photo Booth", "Google Chrome", "Finder")
    monkeypatch.setattr(applications, "installees", lambda: installees)
    monkeypatch.setattr(
        applications,
        "resoudre",
        lambda c: next((a for a in installees if a.lower() == (c or "").strip().lower()), ""),
    )
    return installees


def _aiguiller(phrase: str):
    """Ce que Nova ferait de cette phrase : (nom d'outil, arguments)."""
    from nova import orchestrator
    from nova.core import actions
    from nova.voice import intentions

    intention = intentions.reconnaitre(phrase)
    action = actions.action_pour(intention.nom)
    assert action is not None, f"« {phrase} » n'a produit aucune action"
    retenue, arguments, interruption = orchestrator._confronter_au_reel(  # noqa: SLF001
        action, intention.cible, confirme=False
    )
    if interruption is not None:
        return interruption.etat, interruption.message
    return retenue.outil, arguments


def test_ouvrir_la_derniere_image_va_a_l_outil_image(catalogue):
    """LE BANC CENTRAL : la phrase exacte qui echouait, ACCENTS COMPRIS."""
    outil, arguments = _aiguiller(
        "peux-tu ouvrir la dernière image que j'ai transférée sur mon PC ?"
    )

    assert outil == "ouvrir_image"
    # Aucun chemin nomme : l'outil prendra la plus recente.
    assert arguments == {"chemin": ""}


def test_une_transcription_massacree_ouvre_quand_meme_la_plus_recente(catalogue):
    """⚠️ WHISPER MASSACRE, ET NOVA DOIT QUAND MEME FAIRE QUELQUE CHOSE D'UTILE.

    Releve tel quel : « peux-tu ouvrir alo.png sur PC » est devenu « peut-tu
    ouvrir l'image a l'eau. pengé sur pégé ». Le nom du fichier est perdu, et
    aucun code ne le retrouvera.

    Mais la DEMANDE reste lisible : quelqu'un veut ouvrir une image. Ouvrir la
    plus recente en la NOMMANT vaut mieux que « je ne trouve pas
    d'application » — la personne voit tout de suite si c'est la bonne, et
    corrige d'un mot. Refuser aurait ete correct et inutile.
    """
    outil, arguments = _aiguiller("peut-tu ouvrir l'image à l'eau. pengé sur pégé")

    assert outil == "ouvrir_image"
    assert arguments == {"chemin": ""}, "aucun chemin exploitable : la plus recente"


def test_un_nom_de_fichier_est_transmis_tel_quel(catalogue):
    outil, arguments = _aiguiller("ouvre IMG_7826-2.png")

    assert outil == "ouvrir_image"
    assert arguments == {"chemin": "IMG_7826-2.png"}


def test_ouvrir_par_contenu_exige_une_tournure_explicite(catalogue, monkeypatch):
    """⚠️ TOLERANT POUR REPONDRE, STRICT POUR OUVRIR.

    Le repli qui prend « tout ce qui suit le mot image » rend la recherche
    robuste aux transcriptions massacrees — indispensable pour REPONDRE, ou
    Nova nomme le fichier retenu et ou l'on corrige d'un mot.

    Appliqué a l'OUVERTURE, il a casse deux cas d'un coup : « la derniere
    image que j'ai transferee » et « l'image a l'eau. penge sur pege »
    partaient chercher un contenu introuvable, et Nova REFUSAIT d'ouvrir
    alors qu'ouvrir la plus recente etait la bonne reponse.

    Seule une tournure explicite — « ou il y a », « avec », « qui montre » —
    vaut donc une recherche au catalogue.
    """
    from nova.vision import regard

    trouvees: list[str] = []
    monkeypatch.setattr(
        regard, "retrouver", lambda quoi, limite=3: trouvees.append(quoi) or []
    )

    # Une provenance, pas un contenu : on ouvre la plus recente.
    outil, arguments = _aiguiller("ouvre la dernière image que j'ai transférée")
    assert (outil, arguments) == ("ouvrir_image", {"chemin": ""})
    assert trouvees == [], "aucune recherche au catalogue"

    # Une tournure explicite : on cherche.
    _aiguiller("ouvre l'image où il y a une casquette")
    assert trouvees == ["une casquette"]


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("ouvre Roblox", "Roblox"),
        ("ouvre Photos", "Photos"),
        ("ouvre Chrome", "Google Chrome"),
    ],
)
def test_ouvrir_une_application_n_est_pas_touche(catalogue, phrase, attendu):
    """⚠️ LE NON-EFFET EST LA MOITIE DE LA CORRECTION.

    « ouvre Photos » vise l'application Photos de macOS. Detecter l'image
    avant le catalogue aurait casse ce cas — et il marchait depuis longtemps.
    """
    outil, arguments = _aiguiller(phrase)

    assert outil == "ouvrir_application"
    assert arguments == {"cible": attendu}


def test_une_application_installee_gagne_meme_si_son_nom_designe_une_image(monkeypatch):
    """⚠️ LE SEUL BANC QUI TESTE REELLEMENT L'ORDRE, ET IL A MANQUE.

    Les autres passaient AUSSI en pre-emptant — verifie en inversant le code.
    Ils protegeaient le motif (« Photos » sans determinant n'est pas une
    image), pas la decision de consulter le catalogue d'abord.

    Il fallait donc une application reellement installee dont le nom RESSEMBLE
    a une designation d'image. « Mes Photos » en est une : le determinant y
    est, et pourtant c'est un nom propre.

    Un banc qui passe avec et sans la correction ne teste pas la correction.
    """
    from nova.outils import applications

    installees = ("Mes Photos", "Roblox")
    monkeypatch.setattr(applications, "installees", lambda: installees)
    monkeypatch.setattr(
        applications,
        "resoudre",
        lambda c: next((a for a in installees if a.lower() == (c or "").strip().lower()), ""),
    )

    assert designe_une_image("Mes Photos"), "le motif seul se laisse prendre"

    outil, arguments = _aiguiller("ouvre Mes Photos")

    assert outil == "ouvrir_application", "le catalogue reel doit l'emporter"
    assert arguments == {"cible": "Mes Photos"}


def test_ouvre_la_photo_ouvre_l_image_en_tete_pas_l_application(catalogue, tmp_path):
    """⚠️ CE BANC EXISTE PARCE QUE SON JUMEAU NE SUFFISAIT PAS.

    `test_ouvre_la_photo_designe_l_image_en_tete` verifie `image_en_tete_pour`
    — l'AIDE. Retirer le branchement dans l'orchestrateur le laissait passer :
    encore une fois, je testais la piece et pas le cablage.

    Releve en conditions reelles : Nova venait de trouver IMG_8156.JPG, on lui
    dit « ouvre la photo », et elle a ouvert l'APPLICATION Photos de macOS.
    Le determinant qui aurait tranche est retire en amont par
    `intentions.BRUIT_CIBLE` : « ouvre LA photo » et « ouvre Photos » arrivent
    identiques. Seul le contexte peut departager.
    """
    from nova.vision import focus

    image = tmp_path / "IMG_8156.JPG"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    focus.oublier()
    try:
        # Sans image en tete, « Photos » reste l'application.
        assert _aiguiller("ouvre Photos") == ("ouvrir_application", {"cible": "Photos"})

        focus.retenir(image, origine="recherche")
        outil, arguments = _aiguiller("ouvre la photo")

        assert outil == "ouvrir_image"
        assert arguments == {"chemin": str(image)}
    finally:
        focus.oublier()


def test_une_application_reelle_reste_prioritaire_meme_avec_une_image_en_tete(
    catalogue, tmp_path
):
    """« ouvre Roblox » pendant qu'on parle d'une image ouvre bien Roblox."""
    from nova.vision import focus

    image = tmp_path / "IMG_8156.JPG"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    focus.retenir(image, origine="recherche")
    try:
        assert _aiguiller("ouvre Roblox") == ("ouvrir_application", {"cible": "Roblox"})
    finally:
        focus.oublier()


def test_une_application_inconnue_qui_n_est_pas_une_image_echoue_comme_avant(catalogue):
    """Le repli ne transforme pas tous les echecs en ouverture d'image."""
    etat, message = _aiguiller("ouvre Trucmachin")

    assert etat in ("echouee", "a_confirmer")
    assert "image" not in message.lower()


# ══════════════════════════════════════════════════════════════════════════
#  L'OUTIL — la borne, et ce qu'il refuse
# ══════════════════════════════════════════════════════════════════════════
def test_l_outil_est_enregistre_et_declare_son_risque(tmp_path):
    """REVERSIBLE : une fenetre s'ouvre, on la ferme, il ne reste rien. Ce
    n'est pas une lecture — quelque chose se passe a l'ecran."""
    from nova.core import contrats
    from nova.outils import registre_outils
    from nova.outils.vision import enregistrer_outils_vision

    enregistrer_outils_vision(registre_outils, tmp_path)
    outil = registre_outils.exiger("ouvrir_image")

    assert outil.niveau == contrats.REVERSIBLE
    assert outil.capacite == "action"


def test_l_outil_borne_le_chemin_comme_le_regard(tmp_path, monkeypatch):
    """⚠️ DEUX REGLES DIFFERENTES POUR LE MEME DOSSIER SERAIENT UNE INVITATION
    A SE TROMPER.

    Ouvrir n'est pas lire, mais rien ne justifie que le chemin soit moins
    borne ici que dans `decrire_image` : `open` sur un chemin non verifie
    ouvrirait n'importe quel fichier de la machine.
    """
    from nova.outils.vision import OuvrirImage
    from nova.vision.images import ImageIllisible

    permis = tmp_path / "Downloads"
    permis.mkdir()
    dehors = tmp_path / "prive"
    dehors.mkdir()
    (dehors / "secret.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr("sys.platform", "darwin")

    with pytest.raises(ImageIllisible) as refus:
        OuvrirImage(permis).executer(str(dehors / "secret.png"))

    assert "sort des dossiers" in str(refus.value)


def test_hors_macos_l_outil_le_dit(tmp_path, monkeypatch):
    from nova.outils.systeme import ActionImpossible
    from nova.outils.vision import OuvrirImage

    monkeypatch.setattr("sys.platform", "linux")

    with pytest.raises(ActionImpossible) as refus:
        OuvrirImage(tmp_path).executer("x.png")

    assert "macOS" in str(refus.value)


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ « OUVRE CETTE PHOTO » OUVRAIT UNE CAPTURE D'ECRAN
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        # Releve en conditions reelles. Nova venait de trouver IMG_8156.JPG,
        # on lui dit « ouvre cette photo », et elle a ouvert
        # « Capture d'ecran 2026-08-23 a 23.26.12.png ».
        "ouvre cette Photos",
        "ouvre cette photo",
        "ouvre cette image",
        "ouvre la photo",
        "ouvre mes photos",
        # ⚠️ LE TIRET SURVIT AU DEPOUILLEMENT CENTRAL, ET C'EST VOULU.
        #
        # `intentions.BRUIT_CIBLE` retire des MOTS ENTIERS ; la cible arrive
        # comme « -la ». On ne corrige pas ca en amont : le tiret distingue
        # l'enclitique (« analyse-la ») de l'article (« analyse la
        # situation »), et le detruire casserait la reprise d'image.
        "ouvre-la",
    ],
)
def test_un_demonstratif_ne_fait_pas_perdre_l_image_en_tete(phrase, tmp_path):
    from nova.vision import focus
    from nova.vision.regard import image_en_tete_pour
    from nova.voice import intentions

    image = tmp_path / "IMG_8156.JPG"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    cible = intentions.reconnaitre(phrase).cible
    assert image_en_tete_pour(cible) is None, "sans image en tete, l'application gagne"

    focus.retenir(image, description="une main tenant une casquette", origine="recherche")
    try:
        assert image_en_tete_pour(cible) == image, phrase
    finally:
        focus.oublier()


@pytest.mark.parametrize("phrase", ["ouvre Roblox", "ouvre Google Chrome", "ouvre Spotify"])
def test_une_application_reste_une_application_meme_avec_une_image_en_tete(
    phrase, tmp_path
):
    """Le repli n'enleve jamais rien : une application installee gagne."""
    from nova.vision import focus
    from nova.vision.regard import image_en_tete_pour
    from nova.voice import intentions

    image = tmp_path / "IMG_8156.JPG"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    focus.retenir(image, origine="recherche")
    try:
        assert image_en_tete_pour(intentions.reconnaitre(phrase).cible) is None, phrase
    finally:
        focus.oublier()
