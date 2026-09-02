"""Creer un dossier sur la machine, a la voix.

⚠️ C'EST LA PREMIERE FOIS QUE NOVA ECRIT SUR LE DISQUE.

Jusqu'ici elle savait DESIGNER un fichier — un nom, un dossier, une date — et
l'OUVRIR : une fenetre s'ouvre, on la ferme, il ne reste rien. Creer laisse
une trace apres coup, et c'est ce que la moitie de ces bancs surveille : la
borne d'ECRITURE, qui n'est pas celle de lecture.

    « Nova, je cherche a creer un moteur electrique. »
    « J'aimerais que tout soit classe dans un dossier sur mon bureau. »

La seconde phrase ne porte pas de nom. Il vient du projet actif, que la
premiere vient d'ouvrir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova.fichiers import creer
from nova.outils.fichiers import CreerDossier, FichierRefuse, borner_creation


@pytest.fixture
def bureau(tmp_path, monkeypatch):
    """Un Bureau a nous, declare comme SEULE racine d'ecriture."""
    faux = tmp_path / "Desktop"
    faux.mkdir()
    monkeypatch.setattr(creer, "dossiers_ou_creer", lambda: (faux.resolve(),))
    return faux.resolve()


# ══════════════════════════════════════════════════════════════════════════
#  RECONNAITRE LA DEMANDE
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("phrase", "nom", "ou"),
    [
        ("crée un dossier moteur électrique sur mon bureau", "moteur électrique", "bureau"),
        ("crée-moi un dossier sur le bureau qui s'appelle Moteur", "Moteur", "bureau"),
        ("fais un dossier nommé Impôts dans mes documents", "Impôts", "documents"),
        ("range tout dans un dossier Photos", "Photos", ""),
        # ⚠️ LA PHRASE EXACTE QUI A DEMANDE CETTE FONCTIONNALITE.
        #
        # Elle ne porte pas de nom : c'est le projet actif qui le donne.
        ("j'aimerais que tout soit classé dans un dossier sur mon bureau", "", "bureau"),
        ("j'aimerais que tout soit classé dans un fichier sur mon bureau", "", "bureau"),
    ],
)
def test_les_demandes_de_creation_sont_reconnues(phrase, nom, ou):
    voulu = creer.demande_de_dossier(phrase)

    assert voulu is not None, phrase
    assert voulu.nom == nom
    assert voulu.ou == ou


def test_le_nom_garde_ses_accents_et_sa_casse():
    """⚠️ LE DOSSIER PORTE CE NOM POUR DE BON, SUR LE DISQUE.

    Le meme defaut avait ete corrige pour les projets : « Décision notée :
    augmenter le debit » perdait l'accent de « débit ». Ici, il resterait
    dans le nom du dossier, visible chaque jour.
    """
    voulu = creer.demande_de_dossier("crée un dossier Moteur Électrique V2 sur le bureau")

    assert voulu is not None
    assert voulu.nom == "Moteur Électrique V2"


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ UN SEUL SIGNAL NE SUFFIT PAS, ET C'EST TOUT LE GARDE-FOU.
        #
        # Le verbe seul attrape la moitie du francais parle ; le mot
        # « dossier » seul attrape une question sur un dossier existant.
        "je voudrais savoir l'heure",
        "dans quel dossier est ce fichier",
        "montre-moi le dossier des impôts",
        "ouvre le deuxième dossier",
        "quelle heure est-il",
        "",
    ],
)
def test_ces_phrases_ne_creent_rien(phrase):
    assert creer.demande_de_dossier(phrase) is None


def test_la_destination_n_est_jamais_prise_pour_un_nom():
    """« dossier moteur électrique sur mon bureau » ne nomme pas un dossier
    « moteur électrique sur mon bureau »."""
    voulu = creer.demande_de_dossier("crée un dossier moteur électrique sur mon bureau")

    assert voulu is not None
    assert "bureau" not in voulu.nom


@pytest.mark.parametrize(
    "brut",
    ["../secrets", "a/b", ".cache", "  .  ", "moteur/../.ssh"],
)
def test_un_nom_dicte_douteux_est_refuse_pas_repare(brut):
    """⚠️ LA PREMIERE VERSION REPARAIT, ET C'ETAIT LE MAUVAIS CHOIX.

    Elle remplacait les separateurs par des espaces : « ../evade » devenait
    « evade », « .ssh » devenait « ssh ». Rien ne sortait du Bureau — la borne
    tenait — mais Nova creait un dossier que PERSONNE n'avait demande, sous un
    nom qu'elle avait invente, sans le dire. Le banc de bout en bout l'a vu ;
    la relecture, non.
    """
    assert creer._nom_propre(brut) == ""


@pytest.mark.parametrize(
    ("brut", "propre"),
    [
        ("  Moteur   Électrique  ", "Moteur Électrique"),
        ("Impôts 2024.", "Impôts 2024"),
        ("plans-du-moteur", "plans-du-moteur"),
    ],
)
def test_le_bruit_de_dictee_se_nettoie(brut, propre):
    """Espaces multiples et ponctuation finale ne changent pas ce qui a ete
    demande : ceux-la se corrigent au lieu de faire refuser."""
    assert creer._nom_propre(brut) == propre


def test_un_nom_dicte_trop_long_est_coupe():
    """Whisper rend parfois une phrase entiere la ou l'on attendait deux mots."""
    assert len(creer._nom_propre("mot " * 80)) <= creer.NOM_MAX


# ══════════════════════════════════════════════════════════════════════════
#  LA BORNE D'ECRITURE
# ══════════════════════════════════════════════════════════════════════════


def test_la_racine_d_ecriture_n_est_pas_celle_de_lecture():
    """⚠️ TROIS PORTEES, TROIS REGLAGES — ET CELUI-CI EST LE PLUS ETROIT.

    `fichiers_dossiers` vaut « ~ » : tout le dossier personnel est NOMMABLE.
    Reutiliser cette racine pour l'ecriture permettrait a Nova de fabriquer un
    dossier n'importe ou dans la maison, sur une phrase mal transcrite.
    """
    from nova.settings import get_settings

    reglages = get_settings()

    assert reglages.fichiers_dossiers == "~"
    assert reglages.fichiers_creation_dossiers == "~/Desktop"
    assert reglages.fichiers_creation_dossiers != reglages.fichiers_dossiers


def test_creer_dans_une_racine_declaree(bureau):
    cible = borner_creation(bureau, "moteur électrique")

    assert cible.parent == bureau


def test_un_dossier_non_declare_est_refuse(bureau, tmp_path):
    ailleurs = tmp_path / "Ailleurs"
    ailleurs.mkdir()

    with pytest.raises(FichierRefuse):
        borner_creation(ailleurs, "moteur")


@pytest.mark.parametrize("nom", ["..", ".", "a/b", "../evade", ".cache", "a\\b"])
def test_un_nom_qui_sort_du_dossier_est_refuse(bureau, nom):
    with pytest.raises(FichierRefuse):
        borner_creation(bureau, nom)


def test_un_lien_symbolique_ne_fait_pas_sortir(bureau, tmp_path):
    """⚠️ LA VERIFICATION DU NOM NE SUFFIT PAS, ET C'EST POURQUOI IL Y EN A
    DEUX.

    « evasion » ne contient ni « / » ni « .. ». Si le Bureau contient un lien
    de ce nom vers ailleurs, `mkdir` ecrirait pourtant hors de la racine. On
    resout donc le chemin AVANT de comparer — meme regle que `borner`.
    """
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    (bureau / "evasion").symlink_to(dehors)

    with pytest.raises(FichierRefuse):
        borner_creation(bureau, "evasion")


# ══════════════════════════════════════════════════════════════════════════
#  L'OUTIL
# ══════════════════════════════════════════════════════════════════════════


def test_le_niveau_est_celui_que_le_bareme_annoncait():
    """⚠️ LE BAREME NOMMAIT DEJA « CREER UN DOSSIER » DANS REVERSIBLE.

    Il a ete ecrit avant le premier outil qui agit, precisement pour que ce
    choix ne se decide pas au moment ou l'on a envie que ca marche.
    """
    from nova.core import contrats

    assert CreerDossier.niveau == contrats.REVERSIBLE
    assert not contrats.exige_confirmation(CreerDossier.niveau)


def test_aucun_outil_ne_declare_un_argument_nomme_nom():
    """⚠️ CE DEFAUT NE SE VOIT QU'A L'APPEL, JAMAIS A LA RELECTURE.

    `executer_outil(nom, *, confirme, **arguments)` : son premier parametre
    est le nom de L'OUTIL. Un outil qui declare a son tour un argument `nom`
    produit, au moment ou quelqu'un parle :

        executer_outil() got multiple values for argument 'nom'

    C'est arrive ici, sur le premier essai de bout en bout. L'outil
    s'enregistrait, le catalogue le montrait, les bancs unitaires passaient —
    et la fonctionnalite ne marchait pas. Ce banc regarde TOUS les outils :
    le prochain qui tombera dans le piege le saura avant d'etre livre.
    """
    import inspect

    from nova.outils import registre_outils
    from nova.outils.fichiers import enregistrer_outils_fichiers

    class Registre:
        def __init__(self):
            self.outils = []

        def __contains__(self, nom):
            return False

        def enregistrer(self, outil):
            self.outils.append(outil)

    registre = Registre()
    enregistrer_outils_fichiers(registre)
    assert registre.outils, "aucun outil a examiner"
    assert registre_outils is not None

    for outil in registre.outils:
        parametres = inspect.signature(outil.executer).parameters
        assert "nom" not in parametres, (
            f"« {outil.nom} » declare un argument `nom` : il entrera en "
            "collision avec le nom de l'outil dans `executer_outil`"
        )


def test_l_outil_cree_le_dossier_et_le_dit(bureau):
    message = CreerDossier().executer(dossier="moteur électrique")

    assert (bureau / "moteur électrique").is_dir()
    assert "moteur électrique" in message


def test_deux_fois_la_meme_demande_ne_font_pas_deux_dossiers(bureau):
    """Ni erreur ni doublon : le resultat demande est deja la."""
    CreerDossier().executer(dossier="moteur")
    message = CreerDossier().executer(dossier="moteur")

    assert [d.name for d in bureau.iterdir()] == ["moteur"]
    assert "déjà" in message


def test_l_outil_ne_remplace_jamais_rien(bureau):
    """⚠️ ECRASER SERAIT `CONSEQUENT`, DONC A CONFIRMER.

    On ne le fait pas du tout plutot que de demander : le contenu d'un dossier
    de travail ne se rejoue pas.
    """
    (bureau / "moteur").mkdir()
    (bureau / "moteur" / "plan.pdf").write_text("le plan")

    CreerDossier().executer(dossier="moteur")

    assert (bureau / "moteur" / "plan.pdf").read_text() == "le plan"


def test_sans_nom_l_outil_refuse(bureau):
    with pytest.raises(FichierRefuse):
        CreerDossier().executer(dossier="   ")


def test_une_destination_inconnue_est_refusee(bureau):
    with pytest.raises(FichierRefuse):
        CreerDossier().executer(dossier="moteur", ou="documents")


def test_l_outil_est_au_catalogue():
    """Un outil qui existe et que personne ne peut appeler n'existe pas."""
    from nova.outils import registre_outils
    from nova.outils.fichiers import enregistrer_outils_fichiers

    class FauxRegistre:
        def __init__(self):
            self.noms = []

        def __contains__(self, nom):
            return False

        def enregistrer(self, outil):
            self.noms.append(outil.nom)

    registre = FauxRegistre()
    enregistrer_outils_fichiers(registre)

    assert "creer_dossier" in registre.noms
    assert registre_outils is not None


# ══════════════════════════════════════════════════════════════════════════
#  DE BOUT EN BOUT — la phrase qui a demande cette fonctionnalite
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def outils_inscrits():
    """Le catalogue d'outils, comme au demarrage de Nova.

    ⚠️ SANS CETTE INSCRIPTION, LES BANCS DE BOUT EN BOUT MENTENT.

    `enregistrer_outils_fichiers` est appelee dans le `lifespan` de
    l'application, que `TestClient(app)` ne joue pas quand on ne l'utilise pas
    en gestionnaire de contexte. Le premier essai a donc rendu « outil
    creer_dossier introuvable. Disponibles : horloge » — un echec qui
    ressemblait a un defaut de l'outil et n'en etait pas un.

    On rend le registre a son etat d'origine apres coup : un outil qui reste
    inscrit changerait le catalogue vu par les bancs suivants.
    """
    from nova.outils import registre_outils
    from nova.outils.fichiers import enregistrer_outils_fichiers

    avant = dict(registre_outils._entrees)
    enregistrer_outils_fichiers(registre_outils)
    yield
    registre_outils._entrees = avant


def _client():
    from fastapi.testclient import TestClient

    from nova.api.app import app

    return TestClient(app)


def test_la_phrase_nomme_le_dossier(bureau):
    reponse = _client().post(
        "/v1/action", json={"texte": "crée un dossier Moteur Électrique sur mon bureau"}
    )

    assert reponse.status_code == 200
    fait = reponse.json()
    assert fait["etat"] == "executee", fait["message"]
    assert (bureau / "Moteur Électrique").is_dir()
    assert "Moteur Électrique" in fait["message"], "Nova doit dire le nom qu'elle a retenu"


def test_sans_nom_ni_projet_nova_demande(bureau, monkeypatch):
    """⚠️ ELLE NE DEVINE PAS UN NOM. ELLE POSE LA QUESTION.

    Un dossier « Nouveau dossier » sur le Bureau serait pire que rien : on ne
    saurait ni ce qu'il contient ni pourquoi il est la.
    """
    from nova.api import actions

    monkeypatch.setattr(actions, "_nom_du_projet_actif", lambda: "")

    dit = "j'aimerais que tout soit classé dans un dossier sur mon bureau"
    reponse = _client().post("/v1/action", json={"texte": dit})

    fait = reponse.json()
    assert fait["etat"] == "ignoree"
    assert "appeler" in fait["message"]
    assert list(bureau.iterdir()) == []


def test_le_projet_actif_donne_le_nom(bureau, monkeypatch):
    """⚠️ C'EST CE QUI FAIT MARCHER LA PHRASE LA PLUS NATURELLE DES DEUX.

        « Nova, ouvre le projet moteur électrique »
        « j'aimerais que tout soit classé dans un dossier sur mon bureau »

    Sans ce relais, la seconde serait la seule a ne rien faire.
    """
    from nova.api import actions

    monkeypatch.setattr(actions, "_nom_du_projet_actif", lambda: "moteur électrique")

    dit = "j'aimerais que tout soit classé dans un dossier sur mon bureau"
    reponse = _client().post("/v1/action", json={"texte": dit})

    fait = reponse.json()
    assert fait["etat"] == "executee", fait["message"]
    assert (bureau / "moteur électrique").is_dir()


def test_un_refus_se_dit_au_lieu_de_remonter(bureau, monkeypatch):
    """Une action impossible doit se PRONONCER. Une exception qui remonte
    jusqu'a l'application donne un 500 et un silence."""
    monkeypatch.setattr(creer, "dossiers_ou_creer", lambda: ())

    reponse = _client().post(
        "/v1/action", json={"texte": "crée un dossier Moteur sur mon bureau"}
    )

    assert reponse.status_code == 200
    fait = reponse.json()
    assert fait["etat"] == "echouee"
    assert fait["message"]


def test_ouvrir_un_projet_reste_un_ordre_de_contexte(bureau):
    """⚠️ L'ORDRE DES BRANCHEMENTS EST CE QUI SEPARE LES DEUX.

    « ouvre le projet moteur » contient un verbe de creation possible et le
    mot « projet ». Il doit rester un ordre de CONTEXTE, et ne fabriquer
    aucun dossier.
    """
    reponse = _client().post("/v1/action", json={"texte": "ouvre le projet essai bancs"})

    assert reponse.json()["intention"] != "creer_dossier"
    assert not any(d.name.startswith("essai") for d in bureau.iterdir())


def test_rien_n_est_cree_hors_de_la_racine(bureau, tmp_path, monkeypatch):
    """⚠️ LE BANC QUI VAUT TOUS LES AUTRES.

    Nova ne doit rien poser ailleurs — et rien poser du tout sur un nom
    qu'elle a du reecrire pour qu'il devienne sur. C'est celui-la qui a
    montre que le nettoyage reparait au lieu de refuser.
    """
    from nova.api import actions

    monkeypatch.setattr(actions, "_nom_du_projet_actif", lambda: "")
    temoin = sorted(p.name for p in tmp_path.iterdir())

    for phrase in (
        "crée un dossier ../evade sur mon bureau",
        "crée un dossier .ssh sur mon bureau",
        "crée un dossier /etc/passwd sur mon bureau",
        "crée un dossier ~/Library sur mon bureau",
    ):
        _client().post("/v1/action", json={"texte": phrase})

    assert sorted(p.name for p in tmp_path.iterdir()) == temoin, "Nova a écrit hors du Bureau"
    for cree in bureau.iterdir():
        assert cree.parent == bureau
        assert not cree.name.startswith(".")


def test_un_separateur_dans_le_nom_fait_refuser(bureau, monkeypatch):
    """⚠️ LA PONCTUATION EN TETE ET LE SEPARATEUR AU MILIEU NE SE VALENT PAS.

    L'aplatissement qui preserve les positions remplace la ponctuation par des
    espaces : « dossier ../evade » se lit « dossier   evade », et le motif
    passe simplement par-dessus. C'est le bon comportement — une dictee est
    pleine de virgules et de tirets en tete de mot, et ils ne font pas partie
    du nom.

    Un separateur AU MILIEU, lui, survit a l'aplatissement des positions et
    arrive tel quel dans le nom relu. Celui-la n'est pas du bruit : c'est un
    chemin, et Nova ne cree pas de chemins.
    """
    from nova.api import actions

    monkeypatch.setattr(actions, "_nom_du_projet_actif", lambda: "")

    fait = _client().post(
        "/v1/action", json={"texte": "crée un dossier plans/secrets sur mon bureau"}
    ).json()

    assert fait["etat"] == "ignoree", fait["message"]
    assert list(bureau.iterdir()) == []


def test_le_dossier_cree_est_ensuite_trouvable(bureau, monkeypatch):
    """Creer sans pouvoir retrouver ne servirait a rien : les deux couches
    doivent parler du meme disque."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: bureau.parent))

    CreerDossier().executer(dossier="moteur électrique")

    assert (bureau / "moteur électrique").exists()
