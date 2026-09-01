"""Retrouver une image par ce qu'elle montre.

CE QUE CE BANC PROTEGE

    « Nova, sur mon PC j'ai une image ou il y a une casquette tenue dans une
      main. Est-ce que tu peux me la retrouver ? »

Trois choses doivent tenir ensemble pour que cette phrase marche, et chacune
a sa propre facon de casser :

    LE CATALOGUE      regarder chaque image UNE fois, et s'en souvenir
    LA RECHERCHE      comparer une question francaise a ces souvenirs
    LE DECLENCHEUR    distinguer « retrouve celle ou… » de « decris celle-ci »

⚠️ ET UNE QUATRIEME, QUI NE SE VOIT PAS : LE COUT.

Regarder quarante images a la demande prend deux minutes. Tout ce module
existe pour que la recherche ne coute rien au moment ou on la fait — donc
aucun banc ici ne doit avoir besoin d'un modele.
"""

from __future__ import annotations

import json
import time

import pytest

from nova.vision.catalogue import (
    SEUIL_PERTINENCE,
    Catalogue,
    Entree,
    indexer,
    mots,
)

#: Ce que moondream rend vraiment : de l'anglais.
ANGLAIS = {
    "IMG_7826-2.png": "a hand holding a white baseball cap with 'alo' on it",
    "facture-edf.png": "a document with tables of numbers",
    "capture.png": "a computer screen showing a code editor",
}
FRANCAIS = {
    ANGLAIS["IMG_7826-2.png"]: "une main tenant une casquette blanche",
    ANGLAIS["facture-edf.png"]: "un document avec des tableaux de chiffres",
    ANGLAIS["capture.png"]: "un ecran d'ordinateur affichant un editeur de code",
}


@pytest.fixture
def images(tmp_path):
    for nom in ANGLAIS:
        (tmp_path / nom).write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


@pytest.fixture
def rempli(images, tmp_path):
    """Un catalogue deja indexe, sans qu'aucun modele n'ait tourne."""
    catalogue = Catalogue(tmp_path / "cat.json")
    indexer(
        sorted(images.glob("*.png")),
        catalogue,
        decrire=lambda p: ANGLAIS[p.name],
        traduire=lambda ds: [FRANCAIS[d] for d in ds],
    )
    return catalogue


# ══════════════════════════════════════════════════════════════════════════
#  LA RECHERCHE
# ══════════════════════════════════════════════════════════════════════════
def test_une_question_francaise_trouve_une_description_anglaise(rempli):
    """⚠️ LE POINT QUI DECIDE DE TOUT LE MODULE.

    moondream decrit en anglais. Sans traduction a l'indexation, chercher
    « casquette » dans « a white baseball cap » ne donne rien — et la
    fonctionnalite entiere ne sert a rien pour quelqu'un qui parle francais.
    """
    trouvees = rempli.chercher("une casquette tenue dans une main")

    assert trouvees, "la traduction a l'indexation doit rendre la recherche possible"
    assert trouvees[0][0].nom == "IMG_7826-2.png"
    assert trouvees[0][1] >= SEUIL_PERTINENCE


def test_le_nom_du_fichier_compte_aussi(rempli):
    """« IMG_7826 » ne dit rien, « facture-edf.png » dit tout — et aucun
    modele de vision ne devinera le mot « facture » sur un tableau de
    chiffres."""
    trouvees = rempli.chercher("ma facture d'electricite")

    assert trouvees[0][0].nom == "facture-edf.png"


def test_ce_qui_n_est_pas_la_n_est_pas_invente(rempli):
    """⚠️ RENDRE LA MOINS MAUVAISE SERAIT PIRE QUE NE RIEN RENDRE.

    Nova ouvrirait alors une image que personne n'a demandee, en annoncant
    l'avoir trouvee. Une reussite apparente est plus difficile a deboguer
    qu'un echec.
    """
    trouvees = [t for t in rempli.chercher("un chat roux") if t[1] >= SEUIL_PERTINENCE]

    assert trouvees == []


def test_le_score_est_une_proportion_pas_un_compte(tmp_path):
    """⚠️ COMPTER FERAIT GAGNER LES DESCRIPTIONS BAVARDES.

    Plus un modele est prolixe, plus il attrape de mots au hasard. On mesure
    la part des mots de la QUESTION qui sont presents — une description de
    cent mots n'a donc aucun avantage sur une de dix.
    """
    catalogue = Catalogue(tmp_path / "cat.json")
    catalogue.ajouter(
        Entree("/a.png", "a.png", 1.0, 1, "une casquette blanche")
    )
    catalogue.ajouter(
        Entree(
            "/b.png", "b.png", 2.0, 1,
            "une scene de rue avec des voitures des arbres des passants des "
            "immeubles un ciel bleu des nuages une casquette et un velo",
        )
    )

    trouvees = dict((e.nom, s) for e, s in catalogue.chercher("une casquette blanche"))

    assert trouvees["a.png"] > trouvees["b.png"], "la description courte et juste gagne"


def test_les_verbes_de_la_demande_ne_font_pas_baisser_le_score():
    """⚠️ PLUS LA PHRASE ETAIT POLIE, MOINS LA RECHERCHE MARCHAIT.

    Le score est une proportion : chaque mot de la question absent des
    descriptions le fait baisser. « retrouver » n'apparaitra jamais dans une
    description d'image.
    """
    assert mots("est-ce que tu peux me retrouver une casquette blanche") == [
        "casquette",
        "blanche",
    ]


# ══════════════════════════════════════════════════════════════════════════
#  L'INDEXATION
# ══════════════════════════════════════════════════════════════════════════
def test_une_image_deja_connue_n_est_pas_regardee_deux_fois(rempli, images):
    vues: list[str] = []

    ajoutees = indexer(
        sorted(images.glob("*.png")),
        rempli,
        decrire=lambda p: vues.append(p.name) or "x",
    )

    assert ajoutees == 0
    assert vues == [], "aucune image ne doit etre regardee de nouveau"


def test_une_image_modifiee_est_regardee_de_nouveau(rempli, images):
    cible = images / "capture.png"
    cible.write_bytes(b"\x89PNG\r\n\x1a\nmodifie")

    assert not rempli.a_jour(cible)


def test_une_image_illisible_ne_fait_pas_tomber_l_indexation(images, tmp_path):
    """⚠️ UNE TACHE DE FOND QUI S'ARRETE A LA PREMIERE ANOMALIE NE FINIT
    JAMAIS SON TRAVAIL — et personne ne le voit, puisqu'elle est de fond."""
    catalogue = Catalogue(tmp_path / "cat.json")

    def decrire(chemin):
        if chemin.name == "facture-edf.png":
            raise OSError("fichier corrompu")
        return ANGLAIS[chemin.name]

    ajoutees = indexer(sorted(images.glob("*.png")), catalogue, decrire=decrire)

    assert ajoutees == 2, "les deux autres doivent quand meme etre indexees"


def test_une_traduction_incoherente_est_refusee(images, tmp_path):
    """⚠️ LE PIRE DEFAUT POSSIBLE ICI : ATTRIBUER LA DESCRIPTION D'UNE IMAGE
    A UNE AUTRE.

    Un modele qui fusionne deux lignes ferait ouvrir le mauvais fichier des
    mois plus tard, sans que rien ne signale l'origine. On garde l'anglais
    plutot que de risquer un decalage.
    """
    catalogue = Catalogue(tmp_path / "cat.json")

    indexer(
        sorted(images.glob("*.png")),
        catalogue,
        decrire=lambda p: ANGLAIS[p.name],
        traduire=lambda ds: ["une seule ligne pour trois images"],
    )

    descriptions = [e.description for e in catalogue.entrees()]
    assert all(d in ANGLAIS.values() for d in descriptions), "l'anglais est conserve"


def test_le_lot_borne_le_travail_d_un_passage(images, tmp_path):
    """Chaque passage immobilise la machine : il doit rester court."""
    catalogue = Catalogue(tmp_path / "cat.json")

    ajoutees = indexer(
        sorted(images.glob("*.png")), catalogue, decrire=lambda p: ANGLAIS[p.name], lot=1
    )

    assert ajoutees == 1


def test_une_traduction_ratee_se_rattrape(images, tmp_path):
    """⚠️ SANS CA, UNE TRADUCTION RATEE ETAIT DEFINITIVE.

    Releve sur la machine : « Traduction ignoree : 6 ligne(s) pour 10
    image(s) ». Le garde-fou a bien fonctionne — il a refuse d'attribuer la
    description d'une image a une autre — mais les dix entrees sont restees
    en anglais, et « casquette » ne trouvait rien.

    Les images etaient marquees « a jour », et elles l'etaient : elles
    avaient bien ete regardees. Rien ne repassait donc dessus. Le seul remede
    aurait ete de supprimer le catalogue a la main — un geste que personne ne
    devinera.
    """
    from nova.vision.catalogue import retraduire

    catalogue = Catalogue(tmp_path / "cat.json")
    indexer(
        sorted(images.glob("*.png")),
        catalogue,
        decrire=lambda p: ANGLAIS[p.name],
        traduire=lambda ds: ["une seule ligne"],   # le modele fusionne
    )

    assert catalogue.chercher("casquette") == [], "l'anglais ne repond pas au francais"
    assert len(catalogue.non_traduites()) == 3

    reprises = retraduire(catalogue, lambda ds: [FRANCAIS[d] for d in ds])

    assert reprises == 3
    assert catalogue.chercher("casquette")[0][0].nom == "IMG_7826-2.png"
    assert catalogue.non_traduites() == ()


def test_une_entree_traduite_n_est_pas_reprise(rempli):
    """La retraduction ne doit pas tourner en boucle sur ce qui est deja fait."""
    from nova.vision.catalogue import retraduire

    assert rempli.non_traduites() == ()
    assert retraduire(rempli, lambda ds: ds) == 0


def test_la_retraduction_ne_regarde_aucune_image(images, tmp_path):
    """Les descriptions sont deja la : seule leur langue change. Recharger le
    modele de vision pour ca serait absurde."""
    from nova.vision.catalogue import retraduire

    catalogue = Catalogue(tmp_path / "cat.json")
    indexer(
        sorted(images.glob("*.png")),
        catalogue,
        decrire=lambda p: ANGLAIS[p.name],
        traduire=lambda ds: ["fusionne"],
    )
    for image in images.glob("*.png"):
        image.unlink()          # plus aucune image lisible

    assert retraduire(catalogue, lambda ds: [FRANCAIS[d] for d in ds]) == 3


# ══════════════════════════════════════════════════════════════════════════
#  LA PERSISTANCE
# ══════════════════════════════════════════════════════════════════════════
def test_le_catalogue_survit_a_un_redemarrage(rempli, tmp_path):
    """Tout l'interet du catalogue : ne pas refaire le travail."""
    relu = Catalogue(tmp_path / "cat.json")

    assert len(relu) == 3
    assert relu.chercher("une casquette")[0][0].nom == "IMG_7826-2.png"


def test_un_fichier_illisible_ne_fait_pas_tomber_le_demarrage(tmp_path):
    casse = tmp_path / "cat.json"
    casse.write_text("{ceci n'est pas du json")

    assert len(Catalogue(casse)) == 0


def test_l_ecriture_est_atomique(rempli, tmp_path):
    """⚠️ UNE COUPURE AU MILIEU PERDRAIT TOUT LE TRAVAIL, PAS LA DERNIERE
    ENTREE — `charger` jette un JSON tronque en entier."""
    contenu = json.loads((tmp_path / "cat.json").read_text())

    assert len(contenu["images"]) == 3
    assert not (tmp_path / "cat.tmp").exists(), "le temporaire doit avoir ete deplace"


def test_une_image_supprimee_est_oubliee(rempli, images):
    """Sans ca, Nova proposerait d'ouvrir une image supprimee il y a six mois
    — et l'echec viendrait de `open`, sans rapport apparent avec la recherche
    qui l'a designee."""
    (images / "capture.png").unlink()

    assert rempli.oublier_les_disparues() == 1
    assert len(rempli) == 2


# ══════════════════════════════════════════════════════════════════════════
#  LE DECLENCHEUR — chercher, ou regarder ?
# ══════════════════════════════════════════════════════════════════════════
def test_une_transcription_massacree_trouve_quand_meme(rempli):
    """⚠️ LE MOTIF GRAMMATICAL A ECHOUE SUR UNE PHRASE REELLE.

    Transcription relevee telle quelle — « ou il y a une casquette » entendu
    « ou je train casquette » :

        « peut-tu retrouver la Photos ou je train casquette sur mon PC,
          s'il te plait »

    Aucun motif de grammaire ne rattrapera ca. Exiger une tournure correcte
    d'une transcription vocale, c'est ne marcher que dans les demonstrations.
    On prend donc tout ce qui suit le mot d'image, et les mots vides font le
    tri : « train casquette » cherche « casquette ».

    ⚠️ ET « S'IL TE PLAIT » FAISAIT ECHOUER LA RECHERCHE A UN CENTIEME.

    Le score est une proportion : train + casquette + plait = 1/3 = 0,33,
    pour un seuil a 0,34. Une formule de politesse suffisait a perdre la
    bonne image. Sans « plait » : 1/2 = 0,50.
    """
    from nova.vision.regard import contenu_cherche, demande_de_retrouver

    phrase = (
        "peut-tu retrouver la Photos ou je train casquette sur mon PC, "
        "s'il te plaît"
    )

    assert demande_de_retrouver(phrase)
    trouvees = rempli.chercher(contenu_cherche(phrase))
    assert trouvees[0][0].nom == "IMG_7826-2.png"
    assert trouvees[0][1] >= SEUIL_PERTINENCE, "la politesse ne doit pas faire echouer"


def test_le_mot_de_reveil_ne_compte_pas_comme_un_mot_cherche():
    """« Nova » reste souvent dans la transcription — il apparaissait donc
    dans presque toutes les recherches, en faisant baisser toutes."""
    assert mots("Nova retrouve-moi la photo avec la casquette") == ["casquette"]


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        (
            "Nova sur mon PC j'ai une image où il y a une casquette tenue dans "
            "une main, est-ce que tu peux me la retrouver ?",
            "une casquette tenue dans une main",
        ),
        ("retrouve-moi la photo avec la casquette blanche", "la casquette blanche"),
        ("quelle image montre une trottinette", "une trottinette"),
        ("cherche l'image qui montre un chat", "un chat"),
        ("ouvre l'image où il y a une casquette", "une casquette"),
        ("tu as accès à la photo avec le chien ?", "le chien"),
    ],
)
def test_le_contenu_cherche_est_extrait(phrase, attendu):
    """⚠️ LA CAPTURE S'ARRETE A LA VIRGULE.

    Sans cela, « … une casquette tenue dans une main, est-ce que tu peux me
    la retrouver ? » emportait la question avec — et chaque mot parasite fait
    BAISSER un score qui est une proportion.
    """
    from nova.vision.regard import contenu_cherche

    assert contenu_cherche(phrase) == attendu


@pytest.mark.parametrize(
    "phrase",
    [
        # Regarder, pas chercher : aucune description de contenu.
        "decris cette image",
        "ouvre la dernière image",
        "analyse cette photo",
        "retrouve mon image",
        # Rien a voir avec des images.
        "quelle heure est-il",
        "parle-moi de Mars",
    ],
)
def test_une_phrase_sans_contenu_decrit_ne_declenche_pas_de_recherche(phrase):
    from nova.vision.regard import demande_de_retrouver

    assert not demande_de_retrouver(phrase), phrase


# ══════════════════════════════════════════════════════════════════════════
#  LE BLOC DE REPONSE
# ══════════════════════════════════════════════════════════════════════════
def test_le_bloc_annonce_la_trouvaille_SANS_nommer_ni_decrire(
    monkeypatch, rempli, tmp_path
):
    """⚠️ CE BANC EXIGEAIT LE CONTRAIRE, ET IL AVAIT RAISON A L'EPOQUE.

    Le bloc donnait le nom ET la description au modele, en lui demandant
    explicitement de nommer l'image et de resumer ce qu'on y voit. Il
    obeissait. Releve en conditions reelles :

        « L'image IMG_8156.JPG montre une main tenant une casquette blanche
          avec l'inscription "alo". »

    Demande textuelle : « quand elle la trouve je veux juste que ca dise
    photo trouvee, voulez-vous que je l'ouvre ».

    Un nom de fichier ne se prononce pas, et redecrire une photo a quelqu'un
    qui l'a prise ne lui apprend rien : c'est lui qui vient de la decrire
    pour la retrouver.
    """
    from nova.vision import catalogue as cat
    from nova.vision import focus
    from nova.vision.regard import bloc

    monkeypatch.setattr(cat, "fichier_par_defaut", lambda: tmp_path / "cat.json")

    sortie = bloc("retrouve-moi l'image où il y a une casquette")

    assert "IMG_7826-2.png" not in sortie, "elle ne nomme plus le fichier"
    assert "je te l'ouvre ?" in sortie, "elle propose, et « oui » suffira"
    # ⚠️ LA BONNE IMAGE A BIEN ETE TROUVEE — CA SE PROUVE DANS LA RETENUE.
    #
    # C'est elle que « ouvre-la » et « c'est quoi son nom » consultent, et
    # c'est ce que le moteur a REELLEMENT choisi. Le bloc, lui, n'etait
    # qu'une consigne de mise en forme.
    retenue = focus.derniere("image")
    assert retenue is not None and retenue.chemin.name == "IMG_7826-2.png"


def test_un_catalogue_vide_le_dit_autrement_qu_une_absence(monkeypatch, tmp_path):
    """⚠️ « RIEN TROUVE » ET « RIEN INDEXE » SONT DEUX PANNES OPPOSEES.

    La premiere se corrige en decrivant autrement, la seconde en attendant.
    Les confondre laisserait quelqu'un reformuler dix fois une question sur
    un catalogue vide.
    """
    from nova.vision import catalogue as cat
    from nova.vision.regard import bloc

    monkeypatch.setattr(cat, "fichier_par_defaut", lambda: tmp_path / "vide.json")

    sortie = bloc("retrouve-moi l'image où il y a une casquette")

    assert "n'a encore regarde aucune image" in sortie
    assert "Reponds EXACTEMENT ceci" in sortie


def test_une_recherche_infructueuse_dit_combien_d_images_sont_connues(
    monkeypatch, rempli, tmp_path
):
    from nova.vision import catalogue as cat
    from nova.vision.regard import bloc

    monkeypatch.setattr(cat, "fichier_par_defaut", lambda: tmp_path / "cat.json")

    sortie = bloc("retrouve-moi l'image où il y a un chat roux")

    assert "3 image(s)" in sortie
    assert "aucune ne correspond" in sortie


def test_la_recherche_ne_charge_aucun_modele(monkeypatch, rempli, tmp_path):
    """⚠️ TOUT CE MODULE EXISTE POUR CA.

    Regarder quarante images a la demande prend deux minutes. Si `bloc`
    appelait le moteur de vision sur le chemin d'une recherche, le catalogue
    ne servirait a rien.
    """
    from nova.vision import catalogue as cat
    from nova.vision import moteur
    from nova.vision.regard import bloc

    monkeypatch.setattr(cat, "fichier_par_defaut", lambda: tmp_path / "cat.json")

    def interdit(*a, **k):  # pragma: no cover - ne doit jamais etre appele
        raise AssertionError("aucun modele de vision ne doit etre charge ici")

    monkeypatch.setattr(moteur, "MoteurOllama", interdit)

    from nova.vision import focus

    debut = time.perf_counter()
    bloc("retrouve-moi l'image où il y a une casquette")

    retenue = focus.derniere("image")
    assert retenue is not None and retenue.chemin.name == "IMG_7826-2.png"
    assert time.perf_counter() - debut < 1.0
