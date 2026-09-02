"""Nova propose d'ecrire le projet sur le disque, et le fait si on dit oui.

    « Bon, j'aimerais creer une centrale nucleaire. »
    … on explique, Nova note l'objectif, une decision, une tache …
    « Décision notée : refroidissement passif. Veux-tu que je mette ce projet
      sur ton Bureau, dans un dossier « centrale nucléaire » ? »
    « oui »
    « C'est fait : le dossier centrale nucléaire est sur ton Bureau, avec
      4 élément(s) de notre conversation. »

⚠️ CE QUI EST ECRIT NE PASSE PAR AUCUN MODELE.

« Elle synthetise » : la synthese a deja eu lieu, phrase par phrase, quand
Nova a note l'objectif, la decision et sa raison. Ce qui reste est de la mise
en forme. Demander a un modele de 3 milliards de reecrire ces lignes ferait
une chose de plus — inventer — sur un document qu'on relira dans six mois en
croyant qu'il dit ce qu'on avait decide.

Plusieurs bancs ci-dessous ne verifient donc rien d'autre que ca : le
document ne contient RIEN que la base ne contienne.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from nova.contexte import Element, Projet, document
from nova.fichiers import creer

psycopg = pytest.importorskip("psycopg")


def _schema_pret() -> bool:
    from nova.settings import get_settings

    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'projets' AND column_name = 'dossier'"
                ).fetchone()
                is not None
            )
    except Exception:  # noqa: BLE001
        return False


besoin_de_base = pytest.mark.skipif(
    not _schema_pret(),
    reason="base absente ou migration 005 non appliquee — lance `uv run nova db migrate`",
)


def _projet(**kw) -> Projet:
    defauts = {"id": 1, "nom": "centrale nucléaire"}
    return Projet(**{**defauts, **kw})


def _element(genre: str, contenu: str, pourquoi: str | None = None) -> Element:
    return Element(id=1, genre=genre, contenu=contenu, pourquoi=pourquoi)


# ══════════════════════════════════════════════════════════════════════════
#  QUAND PROPOSER
# ══════════════════════════════════════════════════════════════════════════


def test_un_projet_a_peine_ouvert_ne_merite_pas_encore_un_dossier():
    """En dessous du seuil, la proposition passe pour du zele."""
    assert not document.merite_un_dossier(_projet())
    assert not document.merite_un_dossier(_projet(objectif="produire 900 MW"))


def test_l_objectif_compte_pour_un():
    """C'est souvent la premiere chose dite, et souvent la plus importante."""
    presque = _projet(
        objectif="produire 900 MW",
        elements=(_element("decision", "cycle fermé"),),
    )
    assert not document.merite_un_dossier(presque)

    assez = _projet(
        objectif="produire 900 MW",
        elements=(_element("decision", "cycle fermé"), _element("tache", "chiffrer")),
    )
    assert document.merite_un_dossier(assez)
    assert document.poids(assez) == 3


def test_un_projet_qui_a_deja_son_dossier_ne_le_repropose_pas():
    deja = _projet(
        objectif="produire 900 MW",
        dossier="/Users/x/Desktop/centrale",
        elements=(_element("decision", "a"), _element("tache", "b")),
    )
    assert not document.merite_un_dossier(deja)


def test_une_question_deja_posee_ne_revient_pas():
    """⚠️ C'EST LA CONDITION QU'ON OUBLIE, ET LA PLUS IMPORTANTE DES TROIS.

    Sans elle, un refus serait suivi de la meme question a la decision
    suivante. Ce n'est plus une proposition, c'est du harcelement — et l'on
    finit par ne plus rien dicter.
    """
    refuse = _projet(
        objectif="produire 900 MW",
        document_propose_le=datetime(2026, 9, 2, 10, 0),
        elements=(_element("decision", "a"), _element("tache", "b")),
    )
    assert not document.merite_un_dossier(refuse)
    assert refuse.dossier is None, "un refus ne cree pas de dossier"


def test_sans_projet_il_n_y_a_rien_a_proposer():
    assert not document.merite_un_dossier(None)


def test_la_question_nomme_le_dossier():
    """Une proposition qui ne dit pas ce qui va apparaitre se fait accepter
    sans qu'on sache quoi — et le nom est ce qu'on voudrait corriger."""
    dite = document.question(_projet())

    assert "centrale nucléaire" in dite
    assert dite.endswith("?")


# ══════════════════════════════════════════════════════════════════════════
#  CE QUI EST ECRIT
# ══════════════════════════════════════════════════════════════════════════


def test_le_document_porte_la_raison_des_decisions():
    """⚠️ C'EST LA COLONNE POUR LAQUELLE `elements` EXISTE SOUS CETTE FORME.

    Une decision sans son motif est une contrainte qu'on subit six mois plus
    tard sans savoir pourquoi. Un document qui la perdrait ne vaudrait pas le
    disque qu'il occupe.
    """
    rendu = document.rendre(
        _projet(elements=(_element("decision", "refroidissement passif", "pas de pompe"),)),
        le_jour=date(2026, 9, 2),
    )

    assert "refroidissement passif" in rendu
    assert "*Pourquoi :* pas de pompe" in rendu


def test_le_document_ne_contient_que_ce_qui_a_ete_note():
    """Le banc qui garde le module honnete : aucun mot qui ne vienne d'ici."""
    projet = _projet(
        objectif="produire 900 MW",
        elements=(
            _element("decision", "cycle fermé"),
            _element("tache", "chiffrer le génie civil"),
            _element("hypothese", "le terrain suffit"),
            _element("question", "quel combustible"),
            _element("entite", "le circuit primaire"),
        ),
    )

    rendu = document.rendre(projet, le_jour=date(2026, 9, 2))

    for attendu in (
        "centrale nucléaire", "produire 900 MW", "cycle fermé",
        "chiffrer le génie civil", "le terrain suffit",
        "quel combustible", "le circuit primaire", "2026-09-02",
    ):
        assert attendu in rendu, attendu
    # Rien d'invente : chaque ligne a puce vient d'un element ou de l'objectif.
    dits = {e.contenu for e in projet.elements} | {projet.objectif}
    for ligne in rendu.splitlines():
        if ligne.startswith(("- ", "- [ ] ")):
            nu = ligne.removeprefix("- [ ] ").removeprefix("- ")
            assert nu in dits, f"ligne inventée : « {ligne} »"


def test_les_taches_sont_des_cases_a_cocher():
    """Le document n'est pas un rapport, c'est un point de depart : on doit
    pouvoir le continuer a la main."""
    rendu = document.rendre(_projet(elements=(_element("tache", "chiffrer"),)))

    assert "- [ ] chiffrer" in rendu


def test_un_projet_personnel_le_dit_sur_le_document():
    """⚠️ « JE VEUX GARDER CA POUR MOI » DOIT VOYAGER AVEC LE FICHIER.

    Le document va vivre sa vie : il sera copie, envoye, ouvert devant
    quelqu'un. La propriete ne peut pas rester en base.
    """
    rendu = document.rendre(_projet(confidentialite="personnel"))

    assert "Personnel" in rendu


def test_une_section_vide_n_apparait_pas():
    """Un titre « Décisions » suivi de rien laisse croire qu'on en a perdu."""
    rendu = document.rendre(_projet(elements=(_element("tache", "chiffrer"),)))

    assert "## Décisions" not in rendu
    assert "## À faire" in rendu


def test_le_document_dit_d_ou_il_vient():
    """Un fichier qu'on retrouve dans six mois sans savoir qui l'a ecrit ni
    a partir de quoi est un fichier qu'on n'ose pas croire."""
    rendu = document.rendre(_projet(), le_jour=date(2026, 9, 2))

    assert "Nova" in rendu
    assert "2026-09-02" in rendu


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
def projet_en_base():
    """Un projet a nous, efface a la fin. Les autres sont laisses tranquilles."""
    from nova.contexte import actif
    from nova.db import connection

    with connection() as conn:
        conn.execute("UPDATE projets SET actif = false WHERE actif")
    projet = actif.ouvrir("centrale nucléaire d'essai")
    yield projet
    with connection() as conn:
        conn.execute("DELETE FROM projets WHERE id = %s", (projet.id,))


def _client():
    from fastapi.testclient import TestClient

    from nova.api.app import app

    return TestClient(app)


def _dire(texte: str) -> dict:
    reponse = _client().post("/v1/action", json={"texte": texte})
    assert reponse.status_code == 200
    return reponse.json()


@besoin_de_base
def test_la_conversation_entiere(bureau, projet_en_base):
    """⚠️ LE BANC QUI DIT SI LA FONCTIONNALITE EXISTE VRAIMENT.

    Trois phrases, une proposition, un « oui », un fichier sur le disque.
    """
    from nova.voice import session

    session.oublier()
    _dire("l'objectif c'est produire 900 mégawatts")
    _dire("il faudra chiffrer le génie civil")
    dite = _dire("on part sur un refroidissement passif parce qu'il n'y a pas de pompe")

    assert "Décision notée" in dite["message"]
    assert "Veux-tu que je mette ce projet sur ton Bureau" in dite["message"], (
        "Nova n'a rien propose alors que le projet est assez fourni"
    )

    fait = _dire("oui")

    assert fait["etat"] == "executee", fait["message"]
    dossier = bureau / "centrale nucléaire d'essai"
    ecrit = (dossier / "centrale nucléaire d'essai.md").read_text(encoding="utf-8")
    assert "produire 900 mégawatts" in ecrit
    assert "refroidissement passif" in ecrit
    assert "*Pourquoi :* il n'y a pas de pompe" in ecrit
    assert "- [ ] chiffrer le génie civil" in ecrit


@besoin_de_base
def test_la_proposition_n_arrive_qu_une_fois(bureau, projet_en_base):
    from nova.voice import session

    session.oublier()
    _dire("l'objectif c'est produire 900 mégawatts")
    _dire("il faudra chiffrer le génie civil")
    premiere = _dire("on part sur un refroidissement passif")
    # On ne repond pas. La proposition meurt, et ne doit pas renaitre.
    seconde = _dire("on part sur une turbine unique")

    assert "Veux-tu" in premiere["message"]
    assert "Veux-tu" not in seconde["message"], "la question est revenue"


@besoin_de_base
def test_un_refus_n_ecrit_rien(bureau, projet_en_base):
    from nova.voice import session

    session.oublier()
    _dire("l'objectif c'est produire 900 mégawatts")
    _dire("il faudra chiffrer le génie civil")
    _dire("on part sur un refroidissement passif")

    _dire("non merci")

    assert list(bureau.iterdir()) == []


@besoin_de_base
def test_ecrire_deux_fois_ne_reecrit_pas_le_document(bureau, projet_en_base):
    """⚠️ LE DOCUMENT PEUT AVOIR ETE REPRIS A LA MAIN.

    Le reecrire perdrait ce travail sans que rien ne le dise — exactement ce
    que CONSEQUENT designe dans le bareme. Cet outil reste REVERSIBLE parce
    qu'il n'ecrase pas ; c'est sa seule raison de l'etre.
    """
    from nova.outils.fichiers import EcrireProjet

    EcrireProjet().executer()
    fichier = bureau / "centrale nucléaire d'essai" / "centrale nucléaire d'essai.md"
    fichier.write_text("j'ai tout réécrit à la main", encoding="utf-8")

    message = EcrireProjet().executer()

    assert fichier.read_text(encoding="utf-8") == "j'ai tout réécrit à la main"
    assert "n'y touche pas" in message


@besoin_de_base
def test_le_niveau_reste_reversible():
    from nova.core import contrats
    from nova.outils.fichiers import EcrireProjet

    assert EcrireProjet.niveau == contrats.REVERSIBLE
    assert not contrats.exige_confirmation(EcrireProjet.niveau)


@besoin_de_base
def test_sans_projet_ouvert_l_outil_refuse_au_lieu_d_en_inventer_un(bureau):
    from nova.db import connection
    from nova.outils.fichiers import EcrireProjet

    with connection() as conn:
        conn.execute("UPDATE projets SET actif = false WHERE actif")

    with pytest.raises(Exception, match="Aucun projet"):
        EcrireProjet().executer()
    assert list(bureau.iterdir()) == []


@besoin_de_base
def test_si_le_projet_a_change_entre_la_question_et_le_oui(bureau, projet_en_base):
    """⚠️ « OUI » PEUT ARRIVER APRES UN CHANGEMENT DE PROJET.

    On propose pour la centrale, on bascule sur autre chose, puis on dit oui.
    Ecrire le mauvais projet sous le nom du bon serait pire que ne rien
    ecrire : le fichier aurait l'air juste.
    """
    from nova.outils.fichiers import EcrireProjet

    with pytest.raises(Exception, match="n'est plus"):
        EcrireProjet().executer(projet="un tout autre projet")
    assert list(bureau.iterdir()) == []


def test_une_proposition_ratee_n_emporte_pas_la_reponse(monkeypatch):
    """« Décision notée » a de la valeur toute seule.

    Chaque capacite est facultative : une proposition impossible se tait, elle
    ne fait pas tomber la phrase qu'elle accompagne.
    """
    from nova.api import actions
    from nova.contexte import actif

    def casse():
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(actif, "projet_actif", casse)

    assert actions._proposer_le_dossier() == ""
