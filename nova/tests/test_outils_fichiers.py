"""La borne d'`ouvrir_fichier`, et l'arbitrage image / fichier.

⚠️ CE BANC EXISTE PARCE QUE CETTE FONCTIONNALITE VOIT TOUT LE DISQUE.

Retrouver un fichier ne rend qu'un nom. L'OUVRIR est une action, et `open`
sur un chemin non verifie ouvre n'importe quoi — un script, une application,
un fichier de clef. C'est le seul endroit du module ou une erreur se paie.
"""

from __future__ import annotations

import pathlib

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


def test_les_outils_de_fichiers_sont_enregistres():
    from nova.core import contrats
    from nova.core.registre import Registre
    from nova.outils.fichiers import enregistrer_outils_fichiers

    registre = Registre("outil")
    noms = enregistrer_outils_fichiers(registre)

    assert set(noms) == {"rechercher_fichier", "ouvrir_fichier", "creer_dossier"}
    # ⚠️ LE NIVEAU DIT LA VERITE : chercher LIT, les deux autres AGISSENT.
    assert registre.exiger("rechercher_fichier").niveau == contrats.LECTURE
    assert registre.exiger("ouvrir_fichier").niveau == contrats.REVERSIBLE
    # Creer un dossier se defait en le supprimant : le bareme le nommait deja
    # dans REVERSIBLE, avant que cet outil n'existe.
    assert registre.exiger("creer_dossier").niveau == contrats.REVERSIBLE
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

    # ⚠️ LE BLOC NE PORTE PLUS LE NOM DU FICHIER — IL PORTE SON TITRE.
    #
    # Nova ne cite plus les documents qu'elle trouve. Ce qui se prouve ici
    # n'est pas ce qu'elle dit, mais LEQUEL DES DEUX BLOCS est parti.
    assert "## Recherche de fichier" in prompt
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

    assert "## Recherche de fichier" in prompt
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


def test_le_compte_est_annonce_et_le_rang_explique(tmp_path, monkeypatch):
    """⚠️ NOVA NE RECITE PLUS LES NOMS, ELLE DIT COMBIEN.

    Demande textuelle : « j'aimerais qu'elle arrete de citer les documents,
    je veux juste qu'elle me dise qu'elle a trouve ».

    Le rang garde son sens PARCE QUE le compte est dit : « j'en ai trouve
    trois » suffit a rendre « le deuxieme » prononcable. Et si l'on veut les
    noms, on les demande — c'est `bloc_du_nom` qui repond.
    """
    from nova.fichiers.trouver import bloc, liste_en_tete

    _trois_avis(tmp_path, monkeypatch)

    sortie = bloc("retrouve-moi mes avis d'imposition de 2024")

    assert "3 documents" in sortie
    # Et la consigne dit COMMENT choisir, pas seulement qu'on n'a pas choisi.
    assert "Lequel veux-tu" in sortie
    for nom in ("impos 2024 1.pdf", "impos 2024 2.pdf", "impots 2024 3.pdf"):
        assert nom not in sortie, f"{nom} est prononce alors qu'on ne l'a pas demande"
    # L'ordre, lui, est retenu : c'est ce qui donne un sens au rang.
    assert len(liste_en_tete()) == 3


def test_ouvre_le_deuxieme_ouvre_le_deuxieme(tmp_path, monkeypatch):
    """LE BANC CENTRAL, depuis la phrase prononcee jusqu'a l'outil."""
    from nova import orchestrator
    from nova.core import actions
    from nova.fichiers.trouver import bloc, liste_en_tete
    from nova.voice import intentions

    dossier = _trois_avis(tmp_path, monkeypatch)
    bloc("retrouve-moi mes avis d'imposition de 2024")
    # ⚠️ L'ORDRE VIENT DE LA LISTE RETENUE, PLUS DU TEXTE PRONONCE.
    #
    # Nova ne nomme plus les fichiers ; le rang continue pourtant de designer
    # le meme, parce que la retenue garde l'ordre du classement.
    annonces = [chemin.name for chemin in liste_en_tete()]
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


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ « OUVRE-MOI CETTE PHOTO » LANCAIT L'APPLICATION PHOTOS
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        # Releve en conditions reelles, juste apres une recherche REUSSIE :
        # Nova venait de nommer « CNI BERANGERE RECTO-1.png », on lui dit
        # « ouvre-moi cette photo », et elle a ouvert l'application Photos.
        "ouvre-moi cette Photos",
        "ouvre cette photo",
        "ouvre ce fichier",
        "ouvre ce document",
        "ouvre ce papier",
        "ouvre-le",
    ],
)
def test_un_mot_de_contenant_designe_le_fichier_trouve(phrase, tmp_path):
    """Le mot est retire des mots cherches — l'un nomme un TYPE, l'autre un
    CONTENANT — et il ne restait donc rien a recouper avec le fichier retenu.
    La cible partait au catalogue des applications, ou « Photos » existe."""
    from nova.fichiers.trouver import fichier_en_tete_pour
    from nova.vision import focus
    from nova.voice import intentions

    papier = tmp_path / "CNI BERANGERE RECTO-1.png"
    papier.write_text("x")
    cible = intentions.reconnaitre(phrase).cible

    assert fichier_en_tete_pour(cible) is None, "sans rien en tete, l'appli gagne"

    focus.retenir(papier, origine="recherche de fichier", genre="fichier")
    try:
        assert fichier_en_tete_pour(cible) == papier, phrase
    finally:
        focus.oublier()


@pytest.mark.parametrize("phrase", ["ouvre Roblox", "ouvre Google Chrome", "ouvre Spotify"])
def test_une_application_garde_la_main_meme_avec_un_fichier_en_tete(phrase, tmp_path):
    from nova.fichiers.trouver import fichier_en_tete_pour
    from nova.vision import focus
    from nova.voice import intentions

    papier = tmp_path / "CNI BERANGERE RECTO-1.png"
    papier.write_text("x")
    focus.retenir(papier, origine="recherche de fichier", genre="fichier")
    try:
        assert fichier_en_tete_pour(intentions.reconnaitre(phrase).cible) is None, phrase
    finally:
        focus.oublier()


def test_le_cablage_complet_ouvre_le_fichier_trouve(tmp_path, monkeypatch):
    """Depuis la phrase prononcee jusqu'a l'outil, sans fabriquer d'Action."""
    from nova import orchestrator
    from nova.core import actions
    from nova.fichiers import trouver
    from nova.vision import focus
    from nova.voice import intentions

    dossier = tmp_path / "Desktop" / "pdf2png" / "CNI BERANGERE RECTO"
    dossier.mkdir(parents=True)
    papier = dossier / "CNI BERANGERE RECTO-1.png"
    papier.write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))
    focus.retenir(papier, origine="recherche de fichier", genre="fichier")

    intention = intentions.reconnaitre("ouvre-moi cette photo")
    action = actions.action_pour(intention.nom)
    retenue, arguments, interruption = orchestrator._confronter_au_reel(  # noqa: SLF001
        action, intention.cible, confirme=False
    )

    assert interruption is None, interruption
    assert retenue.outil == "ouvrir_fichier", retenue.outil
    assert arguments == {"chemin": str(papier)}


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ « EMPEAUX » POUR « IMPOTS » — LA SECONDE LECTURE
# ══════════════════════════════════════════════════════════════════════════
def test_un_mot_massacre_est_rattrape_mais_toujours_annonce(tmp_path, monkeypatch):
    """Releve sur la machine :

        dit      « dans mon PC, j'ai mes IMPOTS de 2024 »
        entendu  « dans mon PC, j'ai mes EMPEAUX de 24004 »

    ⚠️ ET LE RAPPROCHEMENT NE PEUT PAS ETRE SILENCIEUX.

    Mesure faite sur la table des papiers, face a « impots » : « empeaux »
    vaut 0,67 et « porsche » vaut 0,67 aussi. Aucun seuil ne passe entre les
    deux. Ce sont donc les RESULTATS qui valident l'hypothese, et Nova dit
    toujours ce qu'elle a compris.
    """
    from nova.fichiers import trouver

    dossier = tmp_path / "Desktop" / "avis d impositions"
    dossier.mkdir(parents=True)
    (dossier / "impots 2024 3.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    sortie = trouver.bloc("dans mon PC, j'ai mes empeaux, peux-tu me les retrouver")

    assert [c.name for c in trouver.liste_en_tete()] == ["impots 2024 3.pdf"], (
        "la seconde lecture doit trouver le fichier"
    )
    assert "empeaux" in sortie, "Nova doit dire ce qu'elle a entendu"
    assert "COMMENCE ta reponse" in sortie, "et le dire EN PREMIER"


def test_la_seconde_lecture_ne_sert_qu_en_dernier_recours(tmp_path, monkeypatch):
    """Une recherche qui aboutit ne doit jamais etre reinterpretee."""
    from nova.fichiers import trouver

    dossier = tmp_path / "Documents"
    dossier.mkdir()
    (dossier / "impots-2024.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    recherche, classes = trouver.chercher("retrouve mes impôts de 2024")

    assert classes, "le fichier est trouve du premier coup"
    assert recherche.entendu == (), "aucun rapprochement ne doit avoir eu lieu"


def test_une_hypothese_qui_ne_trouve_rien_laisse_les_mots_d_origine(
    tmp_path, monkeypatch
):
    """Le message d'echec doit parler des mots REELLEMENT prononces."""
    from nova.fichiers import trouver

    (tmp_path / "vacances.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    recherche, classes = trouver.chercher(
        "dans mon PC, j'ai mes empeaux, peux-tu me les retrouver"
    )

    assert classes == []
    assert recherche.entendu == ()
    assert "empeaux" in recherche.mots


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ NOVA LISAIT MA CONSIGNE A VOIX HAUTE
# ══════════════════════════════════════════════════════════════════════════
def test_la_consigne_vient_avant_les_donnees(tmp_path, monkeypatch):
    """Releve en conditions reelles :

        « La carte est dans ~/Desktop/pdf2png/CNI BERANGERE RECTO-1.png,
          modifiee le 21 juillet 2026. Tu n'as pas lu ces fichiers. Leur
          contenu, les montants, les noms qui y figurent, le nombre de
          pages : rien de tout cela ne doit figurer dans ta reponse. »

    Un modele de trois milliards de parametres CONTINUE ce qu'il vient de
    lire. Terminer le bloc sur une instruction, c'est lui demander de la
    recopier ; terminer sur la liste des fichiers, c'est lui demander d'en
    parler.
    """
    from nova.fichiers import trouver

    dossier = tmp_path / "Documents"
    dossier.mkdir()
    (dossier / "impots-2024.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    sortie = trouver.bloc("retrouve mes impôts de 2024")

    # ⚠️ LA LECON A ETE POUSSEE PLUS LOIN : IL N'Y A PLUS DE DONNEES DU TOUT.
    #
    # La version precedente mettait la consigne avant la liste des fichiers,
    # pour que le modele finisse sur les noms plutot que sur mes phrases. Il
    # les recitait donc — ce qui etait le but, et n'est plus voulu.
    #
    # La seule consigne qu'un petit modele ne peut pas enfreindre est celle
    # qui porte sur une donnee qu'il n'a pas. Le bloc de recherche ne porte
    # plus aucun nom de fichier.
    assert "<<<" not in sortie, "le bloc de recherche ne porte plus de donnees"
    assert "impots-2024.pdf" not in sortie

    # ⚠️ MAIS `bloc_du_nom`, LUI, EN PORTE — ET L'ORDRE Y RESTE LA REGLE.
    #
    # C'est le seul bloc qui donne encore un nom, et donc le seul ou la lecon
    # d'origine s'applique encore.
    nom = trouver.bloc_du_nom("c'est quoi le nom du premier ?")
    assert nom.rstrip().endswith(">>>"), (
        "le bloc doit finir sur la donnee, pas sur une instruction"
    )
    assert nom.index("Ta reponse") < nom.index("<<<"), (
        "la consigne vient AVANT les donnees"
    )


def test_plusieurs_fichiers_se_comptent_sans_se_nommer(tmp_path, monkeypatch):
    """⚠️ ELLE N'EN NOMMAIT QU'UN SUR TROIS. MAINTENANT ELLE N'EN NOMME AUCUN.

    Etape par etape : la consigne disait d'abord « nomme le fichier : {le
    meilleur} », et les deux autres restaient invisibles. Elle a ensuite dit
    de les nommer tous les trois, et Nova a recite onze secondes de noms de
    fichiers voisins dont on ne retient rien a l'oreille.

    Le compte est la seule chose utile a entendre. Les noms se demandent.
    """
    from nova.fichiers import trouver

    dossier = tmp_path / "Desktop" / "avis d impositions"
    dossier.mkdir(parents=True)
    for nom in ("impos 2024 1.pdf", "impos 2024 2.pdf", "impots 2024 3.pdf"):
        (dossier / nom).write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    sortie = trouver.bloc("retrouve mes impôts de 2024")

    assert "3 documents" in sortie
    # ⚠️ LA QUESTION EXACTE, PAS UNE CONSIGNE A COMPOSER.
    #
    # « demande lequel ouvrir, par son rang » contenait le verbe
    # « ouvrir », et un petit modele le CONJUGUE plutot que de poser la
    # question : « Ouverture : la premiere. » — une ouverture annoncee
    # qui n'a pas eu lieu.
    assert "Lequel veux-tu" in sortie, "et comment en choisir un"
    for nom in ("impos 2024 1.pdf", "impos 2024 2.pdf", "impots 2024 3.pdf"):
        assert nom not in sortie, nom


def test_un_seul_fichier_se_propose_sans_se_nommer(tmp_path, monkeypatch):
    from nova.fichiers import trouver

    dossier = tmp_path / "Documents"
    dossier.mkdir()
    (dossier / "impots-2024.pdf").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    sortie = trouver.bloc("retrouve mes impôts de 2024")

    assert "impots-2024.pdf" not in sortie, "elle ne cite plus les documents"
    assert "Je te l'ouvre ?" in sortie, "une seule trouvaille se PROPOSE"


@pytest.mark.parametrize(
    "phrase",
    [
        # Releve en conditions reelles, juste apres que Nova ait nomme un
        # second fichier : « Je ne trouve pas d'application "celui-ci
        # aussi" ». « celui » etait reconnu, « ci » et « aussi » non.
        "ouvre celui-ci aussi",
        "ouvre celui-ci",
        "ouvre celui-là",
        "ouvre-le aussi",
        "ouvre celle-ci également",
    ],
)
def test_celui_ci_designe_le_fichier_dont_on_vient_de_parler(phrase, tmp_path):
    from nova.fichiers.trouver import fichier_en_tete_pour
    from nova.vision import focus
    from nova.voice import intentions

    papier = tmp_path / "impos 2024 2.pdf"
    papier.write_text("x")
    cible = intentions.reconnaitre(phrase).cible

    assert fichier_en_tete_pour(cible) is None, "sans rien en tete, rien a ouvrir"

    focus.retenir(papier, origine="recherche de fichier", genre="fichier")
    try:
        assert fichier_en_tete_pour(cible) == papier, phrase
    finally:
        focus.oublier()


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ « JE TE L'OUVRE ? » — « OUI »
# ══════════════════════════════════════════════════════════════════════════
def test_un_oui_ouvre_le_fichier_propose(tmp_path, monkeypatch):
    """LE BANC CENTRAL de la conversation : depuis la recherche jusqu'a
    l'ouverture, en deux tours et sans repeter « Nova ».

    Il passe par le point d'entree `/v1/action`, celui que l'application
    appelle vraiment — verifier `session.accord` seul ne protegerait que la
    piece, pas son montage.
    """
    from fastapi.testclient import TestClient

    from nova.api.app import app
    from nova.fichiers import trouver

    dossier = tmp_path / "Documents"
    dossier.mkdir()
    papier = dossier / "impots 2024.pdf"
    papier.write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"]) or "ok"
    )

    sortie = trouver.bloc("retrouve mes impôts de 2024")
    assert "Je te l'ouvre ?" in sortie
    assert ouvertes == [], "rien n'est ouvert tant qu'on n'a pas dit oui"

    reponse = TestClient(app).post("/v1/action", json={"texte": "oui"})

    assert reponse.status_code == 200
    assert reponse.json()["intention"] == "proposition_acceptee"
    assert ouvertes == [str(papier)]


def test_un_oui_sans_proposition_ne_declenche_rien(monkeypatch):
    """⚠️ HORS D'UNE PROPOSITION, « OUI » REPART VERS LE MODELE.

    C'est la seule raison pour laquelle on peut se permettre une liste de
    mots aussi courte et aussi generique.
    """
    from fastapi.testclient import TestClient

    from nova.api.app import app

    reponse = TestClient(app).post("/v1/action", json={"texte": "oui"})

    assert reponse.json()["intention"] != "proposition_acceptee"


def test_une_proposition_acceptee_passe_par_le_portillon(monkeypatch):
    """⚠️ UN « OUI » N'EST PAS UN LAISSEZ-PASSER.

    Le bareme de risque s'applique : « oui » repond a « je te l'ouvre ? »,
    pas a une question qu'on n'a pas posee. Une action qui exige une
    confirmation explicite doit continuer de la demander.
    """
    import nova.outils as outils
    from nova import orchestrator
    from nova.outils import ConfirmationRequise

    def exige_confirmation(nom, **kw):
        raise ConfirmationRequise(nom, 3, kw)

    monkeypatch.setattr(outils, "executer_outil", exige_confirmation)

    resultat = orchestrator.executer_outil_propose("eteindre_ordinateur", {})

    assert resultat.etat == "a_confirmer"


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ « OUVRE LES 3 » CHERCHAIT UNE APPLICATION « TROIS »
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "ouvre les 3",
        "ouvre les trois",
        "ouvre tout",
        "ouvre-les tous",
        # ⚠️ CELLES-CI NE DECLENCHAIENT RIEN, ET C'EST LA PLUS NATURELLE.
        #
        # Releve en conditions reelles. Le branchement vivait a l'interieur du
        # cas `ouvrir_application`, donc APRES la reconnaissance d'intention.
        # Ici le verbe est en dernier : la cible est ce qui le SUIT, elle etait
        # donc vide, l'intention n'etait pas reconnue, et le branchement ne
        # pouvait par construction jamais s'executer.
        "peux-tu tous les ouvrir",
        "tu peux tous les ouvrir",
        "tous les ouvrir",
    ],
)
def test_ouvrir_toute_la_liste_annoncee(phrase, tmp_path, monkeypatch):
    """Annoncer trois documents invite a dire « les trois » : c'est la suite
    naturelle de la phrase que Nova vient de prononcer."""
    from fastapi.testclient import TestClient

    from nova.api.app import app
    from nova.fichiers import trouver

    dossier = tmp_path / "Desktop" / "avis d impositions"
    dossier.mkdir(parents=True)
    noms = ["impos 2024 1.pdf", "impos 2024 2.pdf", "impots 2024 3.pdf"]
    for nom in noms:
        (dossier / nom).write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"]) or "ok"
    )

    trouver.bloc("retrouve mes impôts de 2024")
    assert ouvertes == [], "trois candidats a egalite n'en ouvrent aucun"

    reponse = TestClient(app).post("/v1/action", json={"texte": phrase})

    assert reponse.json()["intention"] == "ouvrir_tout", phrase
    assert sorted(pathlib.Path(c).name for c in ouvertes) == sorted(noms)


def test_ouvrir_tout_sans_liste_annoncee_reste_une_application(monkeypatch):
    """Hors d'une liste annoncee, « ouvre tout » ne designe rien."""
    from fastapi.testclient import TestClient

    from nova.api.app import app

    reponse = TestClient(app).post("/v1/action", json={"texte": "ouvre les 3"})

    assert reponse.json()["intention"] != "ouvrir_tout"


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ « TOUT DE SUITE » N'EST PAS UNE TOTALITE.
        #
        # La phrase contient « ouvre » et « tout ». Ouvrir la liste entiere
        # serait l'exemple type de la reussite apparente.
        "ouvre tout de suite Chrome",
        "ouvre-moi ça tout de suite",
        # ⚠️ « MONTRE » NE DIT PAS D'OUVRIR.
        #
        # C'est une demande de description, pas l'ordre d'ouvrir quatre
        # fenetres.
        "montre-moi toutes les photos",
        # Un rang n'est pas une totalite.
        "ouvre le deuxième",
        "ouvre le dernier",
        "ouvre Chrome",
    ],
)
def test_ce_qui_n_ouvre_pas_toute_la_liste(phrase):
    """⚠️ LA PHRASE ENTIERE EST UN FILET PLUS LARGE — IL FAUT DONC LE BORNER.

    Lire le verbe et la totalite n'importe ou dans la phrase rattrape « peux-tu
    tous les ouvrir ». Cela rattraperait aussi « ouvre tout de suite Chrome »
    si l'on n'y prenait pas garde.
    """
    from nova.fichiers.trouver import demande_tout_ouvrir

    assert not demande_tout_ouvrir(phrase), phrase


def test_un_echec_sur_un_fichier_n_arrete_pas_les_autres(monkeypatch):
    """Trois avis, le deuxieme deplace entre-temps : ouvrir le premier puis
    abandonner serait le pire des deux mondes."""
    import nova.outils as outils
    from nova import orchestrator

    def capricieux(nom, **kw):
        if "2" in kw["chemin"]:
            raise OSError("disparu")
        return "ok"

    monkeypatch.setattr(outils, "executer_outil", capricieux)

    resultat = orchestrator.ouvrir_toute_la_liste(["/a/1.pdf", "/a/2.pdf", "/a/3.pdf"])

    assert resultat.etat == "executee"
    assert "2 fichiers sur 3" in resultat.message


def test_nova_dit_les_mots_de_la_demande_pas_le_nom_du_fichier(tmp_path, monkeypatch):
    """⚠️ « CNI BERANGERE RECTO-1.png » EST ILLISIBLE A VOIX HAUTE.

    Demande textuelle : « qu'elle arrete de donner le nom du dossier, elle
    peut l'appeler carte d'identite ».
    """
    from fastapi.testclient import TestClient

    from nova.api.app import app
    from nova.fichiers import trouver

    dossier = tmp_path / "Desktop" / "pdf2png" / "CNI BERANGERE RECTO"
    dossier.mkdir(parents=True)
    (dossier / "CNI BERANGERE RECTO-1.png").write_text("x")
    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "peu importe")

    trouver.bloc("retrouve ma carte d'identité")
    reponse = TestClient(app).post("/v1/action", json={"texte": "oui"}).json()

    assert "carte identite" in reponse["message"]
    assert "CNI BERANGERE" not in reponse["message"]
    assert ".png" not in reponse["message"]


# ══════════════════════════════════════════════════════════════════════════
#  « C'EST QUOI LE NOM DU TROISIEME ? »
#
#  ⚠️ NOVA NE CITE PLUS LES DOCUMENTS. C'EST LA CONTREPARTIE.
#
#  Demande textuelle : « j'aimerais qu'elle arrete de citer les documents, je
#  veux juste qu'elle me dise qu'elle a trouve, et que si je lui demande de me
#  citer le nom du troisieme par exemple elle me le cite ».
#
#  Ce qu'elle disait avant, en onze secondes de synthese vocale :
#
#      « J'ai trouve 4 fichiers : impots 2024 3.pdf, impos 2024 2.pdf, impos
#        2024 1.pdf et Avis d'imposition.pdf. Le meilleur est le premier, il
#        faut le deuxieme. Qu'en penses-tu ? »
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "c'est quoi le nom du troisième",
        "donne-moi le nom du deuxième",
        "cite-moi le nom du premier",
        "comment s'appelle le troisième",
        "quel est le nom du dernier",
        "redis-moi les noms",
        "rappelle-moi le nom du 2",
    ],
)
def test_une_demande_de_nom_se_reconnait(phrase):
    from nova.fichiers.trouver import demande_le_nom

    assert demande_le_nom(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ LE MOT « NOM » SEUL APPARAIT AU MILIEU D'UNE RECHERCHE.
        #
        # « retrouve le contrat au nom de Dupont » EST une recherche. La
        # prendre pour une question sur un nom repondrait a cote, et sans
        # jamais toucher au disque.
        "retrouve le contrat au nom de Dupont",
        "cherche la facture au nom de ma mère",
        # Ni verbe de citation, ni tournure interrogative.
        "ouvre le deuxième",
        "retrouve mes impôts de 2024",
        "quelle heure est-il",
        "",
    ],
)
def test_ce_qui_ne_demande_pas_un_nom(phrase):
    from nova.fichiers.trouver import demande_le_nom

    assert not demande_le_nom(phrase), phrase


def test_le_nom_du_troisieme_se_donne_sur_demande(tmp_path, monkeypatch):
    """LE BANC CENTRAL, par l'orchestrateur — pas par la fonction d'aide.

    ⚠️ ET IL N'EN DONNE QU'UN.

    Donner les trois au modele en lui demandant de n'en citer qu'un, c'est la
    correction facile qui n'aurait pas tenu : un modele de trois milliards de
    parametres CONTINUE ce qu'il vient de lire. On ne lui confie que le nom
    demande — les deux autres ne quittent jamais la memoire de Nova.
    """
    from nova import orchestrator
    from nova.fichiers import trouver

    _trois_avis(tmp_path, monkeypatch)
    _sans_base(monkeypatch)
    trouver.bloc("retrouve-moi mes avis d'imposition de 2024")
    troisieme = trouver.liste_en_tete()[2].name
    autres = [c.name for c in trouver.liste_en_tete()[:2]]

    prompt, _ = orchestrator.build_system_prompt("c'est quoi le nom du troisième ?")

    assert troisieme in prompt
    for nom in autres:
        assert nom not in prompt, f"{nom} n'a pas ete demande"


def test_un_nom_reclame_sans_rang_les_numerote_tous(tmp_path, monkeypatch):
    """« cite-moi les noms » : la liste entiere, et rien d'autre ne la declenche."""
    from nova.fichiers import trouver

    _trois_avis(tmp_path, monkeypatch)
    trouver.bloc("retrouve-moi mes avis d'imposition de 2024")

    sortie = trouver.bloc_du_nom("cite-moi les noms")

    for rang, chemin in enumerate(trouver.liste_en_tete(), start=1):
        assert f"{rang}. {chemin.name}" in sortie


def test_un_rang_hors_liste_ne_donne_aucun_nom(tmp_path, monkeypatch):
    """⚠️ MEME REGLE QUE POUR L'OUVERTURE : ON NE RABAT PAS SUR LE PLUS PROCHE.

    Rendre le troisieme quand on demande le cinquieme serait une reponse
    fausse ayant l'air d'une reponse juste.
    """
    from nova.fichiers import trouver

    _trois_avis(tmp_path, monkeypatch)
    trouver.bloc("retrouve-moi mes avis d'imposition de 2024")

    sortie = trouver.bloc_du_nom("c'est quoi le nom du cinquième ?")

    assert "que 3" in sortie
    for chemin in trouver.liste_en_tete():
        assert chemin.name not in sortie


def test_sans_recherche_prealable_aucun_nom_n_est_donne():
    """Le bloc ne coute rien et ne dit rien quand il n'y a rien a nommer."""
    from nova.fichiers.trouver import bloc_du_nom

    assert bloc_du_nom("c'est quoi le nom du troisième ?") == ""


# ══════════════════════════════════════════════════════════════════════════
#  « FERME LES QUATRE FICHIERS » CHERCHAIT UNE APPLICATION
#
#  Releve en conditions reelles, juste apres que Nova ait ouvert quatre
#  fichiers a la demande :
#
#      « Ferme les quatre fichiers. »
#      → « Je ne trouve pas d'application "quatre fichiers" sur cette
#         machine. »
#
#  Exact du point de vue du catalogue, absurde du point de vue de la
#  conversation : elle venait de les ouvrir.
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    ["ferme les quatre fichiers", "ferme les fichiers", "referme-les tous", "ferme les 3"],
)
def test_une_demande_de_fermeture_de_fichiers_se_reconnait(phrase):
    from nova.fichiers.trouver import demande_tout_fermer

    assert demande_tout_fermer(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ LA GARDE : UN VRAI NOM D'APPLICATION SUIT SON COURS.
        "ferme Chrome",
        "ferme Safari",
        "quitte Aperçu",
        "ferme la fenêtre",
        "ouvre les 3",
    ],
)
def test_ce_qui_n_est_pas_une_fermeture_de_fichiers(phrase):
    from nova.fichiers.trouver import demande_tout_fermer

    assert not demande_tout_fermer(phrase), phrase


def test_nova_dit_qu_elle_ne_sait_pas_fermer_un_fichier(tmp_path, monkeypatch):
    """⚠️ ELLE NE DEVINE PAS L'APPLICATION, ET C'EST LE POINT.

    `open` confie le fichier au systeme, qui choisit l'application. Fermer
    « celle qui doit etre la » serait un pari — sur une action qui peut
    detruire du travail non enregistre.

    Deviner ici serait exactement la reussite apparente que ce projet refuse
    partout ailleurs. Elle repond ce qui est vrai, et donne la phrase qui
    marche.
    """
    from fastapi.testclient import TestClient

    from nova.api.app import app
    from nova.fichiers import trouver

    _trois_avis(tmp_path, monkeypatch)
    trouver.bloc("retrouve mes impôts de 2024")

    reponse = TestClient(app).post(
        "/v1/action", json={"texte": "ferme les trois fichiers"}
    ).json()

    assert reponse["intention"] == "fermer_fichiers"
    assert "application" not in reponse["message"] or "Je ne sais pas fermer" in (
        reponse["message"]
    )
    assert "ferme Aperçu" in reponse["message"], "elle dit la phrase qui marche"


def test_sans_fichier_annonce_ferme_suit_son_cours_normal(monkeypatch):
    """Hors d'une liste annoncee, « ferme les fichiers » ne designe rien de
    particulier et doit repartir vers le catalogue comme avant."""
    from fastapi.testclient import TestClient

    from nova.api.app import app

    reponse = TestClient(app).post(
        "/v1/action", json={"texte": "ferme les fichiers"}
    ).json()

    assert reponse["intention"] != "fermer_fichiers"
