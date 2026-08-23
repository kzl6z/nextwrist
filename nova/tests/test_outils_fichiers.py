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


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ LA REGRESSION DE LA CASQUETTE
# ══════════════════════════════════════════════════════════════════════════
def _sans_base(monkeypatch):
    """La base n'est pas lancee pendant les bancs : 30 s d'attente par appel."""
    from nova.documents import search as document_search
    from nova.memory import conversations, facts

    monkeypatch.setattr(document_search, "search", lambda *a, **k: [])
    monkeypatch.setattr(facts, "list_facts", lambda *a, **k: [])
    monkeypatch.setattr(conversations, "derniers_echanges", lambda *a, **k: [])


def test_une_recherche_de_fichier_sans_resultat_laisse_parler_les_images(
    tmp_path, monkeypatch
):
    """⚠️ « DANS MON PC » A SUFFI A ETOUFFER LE CATALOGUE D'IMAGES.

    Releve en conditions reelles, et c'etait une regression :

        « peux-tu me retrouver une photo dans mon PC ou je tiens une
          casquette blanche »

    « mon pc » declenche la recherche de fichiers. Aucun fichier ne s'appelle
    « casquette ». Mais le bloc « aucun fichier ne correspond » n'est pas
    vide — il pre-emptait donc le regard, qui connaissait cette photo par sa
    DESCRIPTION et l'avait deja trouvee la veille.

    Un echec ne pre-empte rien : ce qui a TROUVE parle.
    """
    from nova import orchestrator
    from nova.fichiers import trouver
    from nova.vision import regard

    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))
    _sans_base(monkeypatch)
    monkeypatch.setattr(
        regard, "bloc", lambda texte: "## Recherche d'image\n\ncasquette-blanche.JPG"
    )

    prompt, _ = orchestrator.build_system_prompt(
        "peux-tu me retrouver une photo dans mon PC où je tiens une casquette blanche"
    )

    assert "casquette-blanche.JPG" in prompt
    assert "AUCUN fichier" not in prompt


def test_un_fichier_trouve_l_emporte_toujours_sur_le_regard(tmp_path, monkeypatch):
    """L'inverse reste vrai : ce qui a trouve parle, et le regard se tait."""
    from nova import orchestrator
    from nova.fichiers import trouver
    from nova.vision import regard

    (tmp_path / "releve-compte-2024.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))
    _sans_base(monkeypatch)

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")
    monkeypatch.setattr(regard, "bloc", lambda texte: "## Ce que Nova voit\n\ncasquette")

    prompt, _ = orchestrator.build_system_prompt(
        "retrouve dans mes photos mon relevé de compte de 2024"
    )

    assert "releve-compte-2024.pdf" in prompt
    assert "casquette" not in prompt


def test_quand_personne_ne_trouve_le_message_d_echec_sort_quand_meme(
    tmp_path, monkeypatch
):
    """Le « je n'ai rien trouve » reste dit — en dernier recours, pas avant."""
    from nova import orchestrator
    from nova.fichiers import trouver
    from nova.vision import regard

    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))
    _sans_base(monkeypatch)
    monkeypatch.setattr(regard, "bloc", lambda texte: "")

    prompt, _ = orchestrator.build_system_prompt(
        "retrouve dans mes fichiers mon relevé de compte de 2024"
    )

    assert "AUCUN fichier" in prompt


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ « OUVRE CET AVIS D'IMPOSITION » CHERCHAIT UNE APPLICATION
# ══════════════════════════════════════════════════════════════════════════
def test_ouvrir_designe_le_fichier_qu_on_vient_de_trouver(tmp_path, monkeypatch):
    """Releve en conditions reelles, juste apres une recherche :

        « ouvre cet avis d'imposition de 2024 »
        → Je ne trouve pas d'application « cette envie d'imposition de
          2024 » sur cette machine.

    Le verbe « ouvre » ne connaissait que les applications et les images.
    """
    from nova.fichiers.trouver import fichier_en_tete_pour
    from nova.vision import focus

    papier = tmp_path / "avis-imposition-2024.pdf"
    papier.write_text("x")

    assert fichier_en_tete_pour("avis imposition") is None, "rien en tete, rien a ouvrir"

    focus.retenir(papier, origine="recherche de fichier", genre="fichier")

    assert fichier_en_tete_pour("avis d'imposition de 2024") == papier
    # Par synonyme : on a demande « mes impots », le fichier dit « imposition ».
    assert fichier_en_tete_pour("impots") == papier
    # Par le pronom seul : « ouvre-le » n'a rien a recouper.
    assert fichier_en_tete_pour("le") == papier


def test_ouvrir_une_application_n_est_jamais_detourne(tmp_path, monkeypatch):
    """⚠️ SANS RECOUVREMENT, UN FICHIER EN TETE DETOURNERAIT « OUVRE CHROME »
       PENDANT DIX MINUTES."""
    from nova.fichiers.trouver import fichier_en_tete_pour
    from nova.vision import focus

    papier = tmp_path / "avis-imposition-2024.pdf"
    papier.write_text("x")
    focus.retenir(papier, origine="recherche de fichier", genre="fichier")

    for nom in ("Google Chrome", "Roblox", "Spotify", "EcoleDirecte"):
        assert fichier_en_tete_pour(nom) is None, nom


def test_le_cablage_d_ouverture_passe_par_l_orchestrateur(tmp_path, monkeypatch):
    """⚠️ DEPUIS LA PHRASE PRONONCEE, PAS DEPUIS UNE `Action` FABRIQUEE.

    C'est la chaine reelle : reconnaissance d'intention, choix de l'action,
    puis confrontation au reel. Un banc qui construit l'`Action` lui-meme
    sauterait l'etage ou « ouvre » se transforme en `ouvrir_application` —
    c'est-a-dire exactement l'etage qui etait en cause.
    """
    from nova import orchestrator
    from nova.core import actions
    from nova.fichiers import trouver
    from nova.vision import focus
    from nova.voice import intentions

    papier = tmp_path / "avis-imposition-2024.pdf"
    papier.write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))
    focus.retenir(papier, origine="recherche de fichier", genre="fichier")

    intention = intentions.reconnaitre("ouvre cet avis d'imposition de 2024")
    action = actions.action_pour(intention.nom)
    assert action is not None, "« ouvre … » doit produire une action"

    retenue, arguments, interruption = orchestrator._confronter_au_reel(  # noqa: SLF001
        action, intention.cible, confirme=False
    )

    assert interruption is None, interruption
    assert retenue.outil == "ouvrir_fichier", retenue.outil
    assert arguments == {"chemin": str(papier)}


# ══════════════════════════════════════════════════════════════════════════
#  « OUVRE LE DEUXIEME »
# ══════════════════════════════════════════════════════════════════════════
def _trois_avis(tmp_path, monkeypatch):
    """Le dossier de la machine : trois avis qui se valent, aucun ouvert."""
    from nova.fichiers import trouver

    dossier = tmp_path / "Desktop" / "avis d impositions"
    dossier.mkdir(parents=True)
    for nom in ("impos 2024 1.pdf", "impos 2024 2.pdf", "impots 2024 3.pdf"):
        (dossier / nom).write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")
    return dossier


def test_la_liste_annoncee_est_numerotee(tmp_path, monkeypatch):
    """⚠️ SANS NUMEROS, « LE DEUXIEME » NE DESIGNE RIEN.

    Nova lit ce bloc a voix haute : on ne revient pas en arriere pour compter.
    Le rang doit avoir ete ENTENDU.
    """
    from nova.fichiers.trouver import bloc

    _trois_avis(tmp_path, monkeypatch)

    sortie = bloc("retrouve-moi mes avis d'imposition de 2024")

    assert "1. " in sortie and "2. " in sortie and "3. " in sortie
    # Et la consigne dit COMMENT choisir, pas seulement qu'on n'a pas choisi.
    assert "ouvre le deuxieme" in sortie


def test_ouvre_le_deuxieme_ouvre_le_deuxieme(tmp_path, monkeypatch):
    """LE BANC CENTRAL, depuis la phrase prononcee jusqu'a l'outil."""
    from nova import orchestrator
    from nova.core import actions
    from nova.fichiers.trouver import bloc
    from nova.voice import intentions

    dossier = _trois_avis(tmp_path, monkeypatch)
    sortie = bloc("retrouve-moi mes avis d'imposition de 2024")
    annonces = [
        ligne.split(". ", 1)[1].split(" (")[0]
        for ligne in sortie.splitlines()
        if ligne[:2] in ("1.", "2.", "3.")
    ]
    assert len(annonces) == 3, annonces

    for phrase, rang in [
        ("ouvre le premier", 1),
        ("ouvre le deuxième", 2),
        ("ouvre le troisième", 3),
        ("ouvre le dernier", 3),
        ("ouvre le 2", 2),
        # ⚠️ LE RANG L'EMPORTE SUR LE RECOUPEMENT DE MOTS.
        #
        # Cette phrase contient « avis » et « imposition », qui recoupent le
        # fichier retenu — le recoupement rendrait donc le PREMIER.
        ("ouvre le deuxième avis d'imposition", 2),
    ]:
        intention = intentions.reconnaitre(phrase)
        action = actions.action_pour(intention.nom)
        retenue, arguments, interruption = orchestrator._confronter_au_reel(  # noqa: SLF001
            action, intention.cible, confirme=False
        )
        assert interruption is None, (phrase, interruption)
        assert retenue.outil == "ouvrir_fichier", (phrase, retenue.outil)
        attendu = str(dossier / annonces[rang - 1])
        assert arguments == {"chemin": attendu}, phrase


def test_un_rang_qui_n_existe_pas_n_ouvre_rien(tmp_path, monkeypatch):
    """⚠️ ON NE RABAT PAS SUR LE PLUS PROCHE.

    « le cinquieme » quand il y en a trois est une meconnaissance, pas une
    approximation. Ouvrir le troisieme serait une reussite apparente sur un
    fichier que personne n'a demande.
    """
    from nova.fichiers.trouver import bloc, fichier_en_tete_pour

    _trois_avis(tmp_path, monkeypatch)
    bloc("retrouve-moi mes avis d'imposition de 2024")

    assert fichier_en_tete_pour("cinquième") is None


def test_un_rang_sans_liste_annoncee_n_ouvre_rien(tmp_path, monkeypatch):
    """Un rang ne veut rien dire hors d'une liste qu'on vient d'entendre."""
    from nova.fichiers.trouver import fichier_en_tete_pour
    from nova.vision import focus

    papier = tmp_path / "avis-imposition-2024.pdf"
    papier.write_text("x")
    focus.retenir(papier, origine="recherche de fichier", genre="fichier")

    assert fichier_en_tete_pour("deuxième") is None
    # Le fichier retenu reste atteignable par ses mots, comme avant.
    assert fichier_en_tete_pour("avis d'imposition") == papier


def test_le_rang_ne_detourne_pas_une_application(tmp_path, monkeypatch):
    """« ouvre Photoshop 2024 » contient un chiffre, pas un rang."""
    from nova.fichiers.trouver import rang_demande

    assert rang_demande("Photoshop 2024") is None
    assert rang_demande("Roblox") is None
    assert rang_demande("deuxième") == 2
