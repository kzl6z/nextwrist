"""Trois defauts releves en conditions reelles, sur les journaux de la machine.

CE QUI ETAIT DIT, ET CE QUE NOVA A REPONDU

    « J'ai trouve 3 photos d'une carte Pokemon. Laquelle veux-tu ? »
    « Ouvre-les toutes. »
    « Je ne trouve pas d'application "toutes" sur cette machine. »

    « Cré, un dossier sur mon bureau de PC, avec la photo… »
    « Créer un dossier sur le bureau est possible via le menu 'Fichier'. »

    « je cherche a creer une fusee »
    (rien)

Les trois ont la meme forme : une chaine de fonctionnalites qui existe,
qui est testee, et dont le premier maillon ne se declenche pas. Un module
juste que rien n'appelle ne vaut pas mieux qu'un module absent.
"""

from __future__ import annotations

import pytest

from nova.contexte import commandes
from nova.fichiers import creer

# ══════════════════════════════════════════════════════════════════════════
#  1. « OUVRE-LES TOUTES » NE MARCHAIT QUE SUR DES DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def trois_photos(tmp_path):
    """Trois photos annoncees, comme apres une recherche d'images."""
    from nova.vision import focus

    chemins = []
    for i in range(3):
        photo = tmp_path / f"carte-{i}.png"
        photo.write_bytes(b"\x89PNG")
        chemins.append(photo)
    focus.retenir(
        chemins[0],
        description="une carte Pokemon",
        origine="recherche",
        liste=tuple(chemins),
        demande="une carte Pokemon",
    )
    yield tuple(chemins)
    focus.oublier()


def test_ouvre_les_toutes_ouvre_des_photos(trois_photos, monkeypatch):
    """⚠️ LE CORRECTIF DE « PEUX-TU TOUS LES OUVRIR » NE COUVRAIT QU'UNE MOITIE.

    Il lisait `liste_en_tete()`, qui ne rend QUE des documents. Apres une
    recherche d'IMAGES la liste etait vide, le branchement ne prenait pas, et
    « toutes » repartait au catalogue des applications.

    Les deux cotes avaient chacun leur banc. Aucun n'avait celui-ci.
    """
    from nova.api import actions

    ouverts: list[tuple[str, str]] = []

    def faux_outil(nom, **kw):
        ouverts.append((nom, kw.get("chemin", "")))
        return "ouvert"

    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", faux_outil)

    fait = actions._executer(actions.DemandeAction(texte="Ouvre les toutes."))

    assert fait.etat == "executee", fait.message
    assert [nom for nom, _ in ouverts] == ["ouvrir_image"] * 3, (
        "les photos doivent passer par `ouvrir_image`, pas par `ouvrir_fichier`"
    )
    assert fait.intention == "ouvrir_tout"
    assert "photos" in fait.message, "Nova doit dire « photos », pas « fichiers »"


def test_sans_rien_d_annonce_ouvre_les_toutes_ne_fait_rien(monkeypatch):
    """« Ouvre-les toutes » sans rien avant ne designe rien. Mieux vaut ne
    rien faire que d'ouvrir ce qui trainait."""
    from nova.api import actions
    from nova.vision import focus

    focus.oublier()

    liste, outil, mot = actions._liste_annoncee()

    assert liste == ()
    assert outil == "ouvrir_fichier"
    assert mot == "fichiers"


def test_une_liste_de_documents_passe_toujours_par_ouvrir_fichier(tmp_path):
    """La regression qui couterait le plus cher : ne pas casser ce qui marchait."""
    from nova.api import actions
    from nova.vision import focus

    papier = tmp_path / "impots.pdf"
    papier.write_text("x")
    focus.retenir(papier, genre="fichier", liste=(papier,), origine="recherche")
    try:
        liste, outil, mot = actions._liste_annoncee()
    finally:
        focus.oublier()

    assert liste == (papier,)
    assert outil == "ouvrir_fichier"
    assert mot == "fichiers"


# ══════════════════════════════════════════════════════════════════════════
#  2. « JE CHERCHE A CREER UNE FUSEE » N'OUVRAIT AUCUN PROJET
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("phrase", "nom"),
    [
        # ⚠️ LA PHRASE EXACTE DU RELEVE.
        ("je cherche à créer une fusée", "fusée"),
        ("j'aimerais bien créer une centrale nucléaire", "centrale nucléaire"),
        ("je veux construire un moteur électrique", "moteur électrique"),
        ("je voudrais faire une application de recettes", "application de recettes"),
        ("on va créer une fusée", "fusée"),
        ("j'ai envie de monter un studio photo", "studio photo"),
    ],
)
def test_une_intention_de_projet_ouvre_le_projet(phrase, nom):
    """⚠️ PERSONNE NE DIT « OUVRE LE PROJET FUSEE ».

    `_OUVRIR` exigeait le mot « projet ». Sans projet actif, l'objectif ne
    s'enregistre pas, les decisions non plus, et la proposition d'ecrire le
    dossier ne peut jamais arriver. Toute la chaine restait morte derriere un
    mot que personne ne prononce.
    """
    ordre = commandes.lire(phrase)

    assert ordre is not None, phrase
    assert ordre.genre == "ouvrir"
    assert ordre.contenu == nom


def test_l_article_ne_finit_pas_dans_le_nom_du_dossier():
    """« une centrale nucléaire » deviendra un dossier sur le Bureau. On lit
    « une » chaque jour, et il n'a rien a y faire."""
    ordre = commandes.lire("j'aimerais créer une centrale nucléaire")

    assert ordre is not None
    assert not ordre.contenu.startswith("une ")


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ CES PHRASES NE DOIVENT PAS OUVRIR DE PROJET.
        #
        # Sans l'exclusion, Nova ouvrirait un projet « un dossier sur mon
        # bureau » — et le creerait en base, ou il resterait.
        "j'aimerais créer un dossier sur mon bureau",
        "je voudrais créer un fichier",
        "j'aimerais que tout soit classé dans un dossier sur mon bureau",
        # Un seul verbe ne suffit pas : il faut la volonte ET la fabrication.
        "je cherche mes impôts de 2024",
        "crée un dossier Impôts sur mon bureau",
        "je veux voir ma carte d'identité",
        "quelle heure est-il",
    ],
)
def test_ces_phrases_n_ouvrent_aucun_projet(phrase):
    ordre = commandes.lire(phrase)

    assert ordre is None or ordre.genre != "ouvrir", f"{phrase} → {ordre}"


def test_ouvrir_explicitement_reste_prioritaire():
    """« ouvre le projet X » dit deja ce qu'il veut : le motif implicite ne
    doit pas s'interposer."""
    ordre = commandes.lire("Nova, ouvre le projet centrale nucléaire")

    assert ordre is not None
    assert ordre.genre == "ouvrir"
    assert ordre.contenu == "centrale nucléaire"


def test_les_deux_familles_ne_se_marchent_pas_dessus():
    """⚠️ « j'aimerais créer un dossier » PORTE LES DEUX SIGNAUX.

    Un verbe de fabrication a la premiere personne, et le mot « dossier ».
    Si les deux familles le revendiquent, l'ordre des branchements decide en
    silence — et c'est exactement le genre de choix qu'on ne retrouve plus
    six mois apres.
    """
    phrase = "j'aimerais créer un dossier sur mon bureau"

    assert commandes.lire(phrase) is None, "le contexte doit s'abstenir"
    assert creer.demande_de_dossier(phrase) is not None, "les fichiers doivent prendre"


# ══════════════════════════════════════════════════════════════════════════
#  3. UNE PANNE DE RESUME EMPORTAIT LE RAPPEL BRUT
# ══════════════════════════════════════════════════════════════════════════


def test_un_resume_illisible_ne_fait_pas_perdre_le_passe_recent(monkeypatch):
    """⚠️ UN PLUS NE PREND PAS EN OTAGE CE QU'IL COMPLETE.

    `rappeler` a remplace un appel nu a `derniers_echanges`. En lisant le
    resume EN PREMIER, elle a mis un point de panne devant une fonctionnalite
    qui marchait : table absente, migration non appliquee, base momentanement
    injoignable — et le passe recent disparaissait avec.

    Trois bancs ecrits bien avant ce module l'ont montre, le jour ou la base
    s'est arretee pendant une passe.
    """
    from nova.memory import conversations, resume

    def base_en_panne(*a, **k):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(resume, "courant", base_en_panne)
    monkeypatch.setattr(
        conversations,
        "derniers_echanges",
        lambda *a, **k: [{"role": "user", "content": "Parle-moi de Mars."}],
    )

    rappel = resume.rappeler(1, budget_caracteres=1200)

    assert rappel.resume == ""
    assert [m["content"] for m in rappel.messages] == ["Parle-moi de Mars."]
