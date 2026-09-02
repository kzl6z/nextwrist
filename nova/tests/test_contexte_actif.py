"""Le contexte actif : de quoi on parle, et depuis quand.

CE QUE CES BANCS PROTEGENT

    « ouvre mon projet moteur »           → un projet actif, qui dure
    « on va gagner 15 % de puissance »    → un objectif
    « ajoute ca aux prochaines etapes »   → une tache
    « rappelle-moi pourquoi on avait… »   → la RAISON d'une decision
    « revenons au projet NOVA »           → un basculement
    « je veux garder ca pour moi »        → une confidentialite lisible

⚠️ ET ILS PROTEGENT SURTOUT CE QUE CE MODULE NE FAIT PAS.

Il ne resout aucune reference. Pas de regle « si la phrase dit "augmente ca"
alors … » : ce serait l'illusion de comprendre, et ca casserait a la premiere
tournure non prevue. Il FOURNIT les referents, le modele rattache.

Un banc verifie qu'aucun nom de fichier ne repart dans le prompt — c'est la
correction « Nova ne cite plus les documents », qu'une premiere version de ce
bloc defaisait par la porte de derriere.
"""

from __future__ import annotations

import pytest

psycopg = pytest.importorskip("psycopg")


def _schema_pret() -> bool:
    from nova.settings import get_settings

    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=2) as conn:
            return (
                conn.execute("SELECT to_regclass('public.projets')").fetchone()[0]
                is not None
            )
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _schema_pret(),
    reason="base absente ou migrations non appliquees — lance `uv run nova db migrate`",
)


@pytest.fixture
def sans_projet():
    """Table nette avant et apres. Les projets d'un banc ne sont a personne."""
    from nova.db import connection

    with connection() as conn:
        conn.execute("DELETE FROM projets")
    yield
    with connection() as conn:
        conn.execute("DELETE FROM projets")


# ══════════════════════════════════════════════════════════════════════════
#  1 & 6. UN PROJET QUI DURE
# ══════════════════════════════════════════════════════════════════════════
def test_ouvrir_un_projet_le_rend_actif(sans_projet):
    from nova.contexte import actif

    actif.ouvrir("projet moteur", objectif="gagner 15 % de puissance")

    courant = actif.projet_actif()
    assert courant is not None
    assert courant.nom == "projet moteur"
    assert courant.objectif == "gagner 15 % de puissance"


def test_ouvrir_deux_fois_ne_cree_pas_deux_projets(sans_projet):
    """⚠️ IDEMPOTENT, ET C'EST NECESSAIRE.

    « ouvre le projet moteur » dit deux fois ne doit pas creer deux projets
    moteur, ni perdre ce qui a ete accumule dans le premier.
    """
    from nova.contexte import actif

    premier = actif.ouvrir("projet moteur", objectif="gagner 15 %")
    actif.noter("decision", "on augmente le débit", pourquoi="levier le moins coûteux")
    second = actif.ouvrir("projet moteur")

    assert premier.id == second.id
    assert actif.projet_actif().objectif == "gagner 15 %", "l'objectif survit"
    assert len(actif.projet_actif().decisions) == 1, "la décision aussi"


def test_un_seul_projet_actif_a_la_fois(sans_projet):
    """« De quoi parlons-nous maintenant » n'a qu'une reponse — et c'est un
    index unique qui le garantit, pas du code qui essaie d'y penser."""
    from nova.contexte import actif
    from nova.db import connection

    actif.ouvrir("projet moteur")
    actif.ouvrir("projet NOVA")

    with connection() as conn:
        combien = conn.execute("SELECT count(*) AS n FROM projets WHERE actif").fetchone()
    assert combien["n"] == 1
    assert actif.projet_actif().nom == "projet NOVA"


# ══════════════════════════════════════════════════════════════════════════
#  3 & 4 & 7. CHANGER DE SUJET, ET REVENIR
# ══════════════════════════════════════════════════════════════════════════
def test_revenir_a_un_projet_retrouve_tout_ce_qu_il_portait(sans_projet):
    """LE BANC CENTRAL DU CHANGEMENT DE CONTEXTE.

    « Bon, revenons au projet NOVA » doit rendre l'objectif, les decisions et
    les taches — sans que rien soit reexplique.
    """
    from nova.contexte import actif

    actif.ouvrir("projet NOVA", objectif="rendre Nova conversationnelle")
    actif.noter("decision", "un seul projet actif", pourquoi="une seule réponse possible")
    actif.noter("tache", "brancher le contexte au prompt")

    actif.ouvrir("projet moteur", objectif="gagner 15 %")
    assert actif.projet_actif().nom == "projet moteur"

    retour = actif.basculer("projet NOVA")

    assert retour is not None
    courant = actif.projet_actif()
    assert courant.objectif == "rendre Nova conversationnelle"
    assert [d.contenu for d in courant.decisions] == ["un seul projet actif"]
    assert [t.contenu for t in courant.taches] == ["brancher le contexte au prompt"]


def test_basculer_vers_un_projet_inconnu_ne_cree_rien(sans_projet):
    """⚠️ UN NOM MAL TRANSCRIT NE DOIT PAS FABRIQUER UN PROJET FANTOME.

    Whisper entend « projet moteure ». Le creer a la volee donnerait un projet
    vide, actif, qui prendrait la place du vrai — et il faudrait ensuite
    comprendre pourquoi Nova ne se souvient de rien.
    """
    from nova.contexte import actif

    actif.ouvrir("projet moteur")

    assert actif.basculer("projet moteure") is None
    assert actif.projet_actif().nom == "projet moteur", "l'actif n'a pas bougé"


# ══════════════════════════════════════════════════════════════════════════
#  LA RAISON D'UNE DECISION
# ══════════════════════════════════════════════════════════════════════════
def test_une_decision_garde_son_pourquoi(sans_projet):
    """⚠️ « RAPPELLE-MOI POURQUOI ON AVAIT CHOISI CETTE APPROCHE ».

    Ne se repond pas avec une liste de decisions : il faut la RAISON. Une
    decision sans motif est une contrainte qu'on subit six mois plus tard sans
    savoir pourquoi.
    """
    from nova.contexte import actif

    actif.ouvrir("projet moteur")
    actif.noter(
        "decision",
        "on augmente le débit de 20 %",
        pourquoi="c'est le levier le moins coûteux",
    )

    decision = actif.projet_actif().decisions[0]
    assert decision.pourquoi == "c'est le levier le moins coûteux"
    assert "parce que c'est le levier" in actif.bloc()


# ══════════════════════════════════════════════════════════════════════════
#  LA CONFIDENTIALITE
# ══════════════════════════════════════════════════════════════════════════
def test_garder_ca_pour_moi_devient_une_propriete_lisible(sans_projet):
    """⚠️ SANS CE CHAMP, LA PHRASE EST ENTENDUE PUIS PERDUE.

    « Je veux garder ca pour moi » doit se traduire quelque part que les
    OUTILS puissent lire avant d'ecrire ou d'envoyer. Une intention qui ne vit
    que dans l'historique de conversation ne protege rien : elle depend du bon
    vouloir d'un modele de trois milliards de parametres.
    """
    from nova.contexte import actif

    actif.ouvrir("prototype confidentiel")
    actif.confidentialite("personnel")

    assert actif.projet_actif().confidentialite == "personnel"
    assert "PERSONNEL" in actif.bloc()


def test_une_confidentialite_inconnue_est_refusee(sans_projet):
    from nova.contexte import actif

    actif.ouvrir("projet moteur")
    with pytest.raises(ValueError):
        actif.confidentialite("secret-defense")


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ CE QUE LE BLOC NE FAIT PAS
# ══════════════════════════════════════════════════════════════════════════
def test_le_bloc_fournit_les_referents_sans_resoudre_la_reference(sans_projet):
    """⚠️ LA DECISION DE CONCEPTION CENTRALE, ET ELLE EST DEMANDEE.

    Pas de regle « si la phrase dit "augmente ca" alors … ». Ce serait
    l'illusion de comprendre, et ca casserait a la premiere tournure non
    prevue — le francais ne se met pas en liste.

    Le bloc dit CE DONT ON PARLE. Le modele rattache. C'est exactement ce qui
    a marche pour « ouvre le deuxieme » : nous ne devinons pas lequel, nous
    retenons la liste dans l'ordre annonce.
    """
    from nova.contexte import actif

    actif.ouvrir("projet moteur", objectif="gagner 15 %")
    actif.noter("entite", "le système de refroidissement")
    actif.noter("entite", "le moteur")

    bloc = actif.bloc("et si on augmente ça de 20 % ?")

    assert "le système de refroidissement" in bloc
    assert "le moteur" in bloc
    # Aucune resolution : le bloc ne dit pas ce que « ca » designe.
    assert "ça désigne" not in bloc
    assert "demande LAQUELLE" in bloc, "il dit quoi faire en cas d'ambiguïté"


def test_le_bloc_ne_remet_jamais_les_noms_de_fichiers(sans_projet, tmp_path):
    """⚠️ UNE PREMIERE VERSION DEFAISAIT UNE CORRECTION PAR LA PORTE DE DERRIERE.

    Elle numerotait les fichiers annonces. Nova ne cite plus les documents
    qu'elle trouve — et le modele n'en a pas besoin : « le deuxieme » est
    resolu par `fichier_en_tete_pour`, hors du modele, sur la liste retenue.

    Lui donner les noms ne l'aiderait pas a choisir. Ca lui donnerait de quoi
    les prononcer.
    """
    from nova.contexte import actif
    from nova.vision import focus

    premier = tmp_path / "impots 2024 1.pdf"
    second = tmp_path / "impots 2024 2.pdf"
    for fichier in (premier, second):
        fichier.write_text("x")
    actif.ouvrir("projet moteur")
    focus.retenir(
        premier, origine="recherche de fichier", genre="fichier",
        demande="impots 2024", liste=(premier, second),
    )

    bloc = actif.bloc("c'est quoi le deuxième ?")

    assert "impots 2024" in bloc, "ce qu'on a cherché est dit"
    assert "impots 2024 1.pdf" not in bloc, "le NOM ne l'est pas"
    assert "impots 2024 2.pdf" not in bloc


def test_sans_projet_ni_retenue_le_bloc_est_vide(sans_projet):
    """Le cas courant : une question ordinaire ne doit rien coûter."""
    from nova.contexte import actif
    from nova.vision import focus

    focus.oublier()

    assert actif.bloc("quelle heure est-il ?") == ""


def test_on_ne_note_rien_sans_projet_et_on_n_en_invente_pas(sans_projet):
    """⚠️ CREER UN PROJET « SANS TITRE » POUR POUVOIR NOTER SERAIT PIRE.

    Ce serait fabriquer du contexte que personne n'a demande — et il faudrait
    ensuite deviner quand le fermer.
    """
    from nova.contexte import actif

    assert actif.noter("tache", "revoir le refroidissement") is None
    assert actif.projet_actif() is None


def test_un_genre_inconnu_est_refuse(sans_projet):
    from nova.contexte import actif

    actif.ouvrir("projet moteur")
    with pytest.raises(ValueError):
        actif.noter("intuition", "ça devrait marcher")


# ══════════════════════════════════════════════════════════════════════════
#  12 & 23. LE BLOC EST BORNE, ET IL NE COUTE RIEN
# ══════════════════════════════════════════════════════════════════════════
def test_le_bloc_reste_dans_son_budget(sans_projet):
    """⚠️ ~3,3 ms PAR CARACTERE AVANT LE PREMIER MOT, MESURE SUR L'iMac M1.

    Un contexte qui grossit sans borne ralentit Nova a mesure qu'on travaille
    — exactement quand on en a le plus besoin. C'est le meme defaut, et la
    meme borne, que le budget des faits.
    """
    from nova.contexte import actif

    # ⚠️ IL FAUT DE LONGS ELEMENTS, PAS BEAUCOUP D'ELEMENTS.
    #
    # Premiere version de ce banc : quarante hypotheses courtes. Il passait —
    # et il passait AUSSI quand on retirait la troncature, parce que
    # `COMBIEN_PAR_GENRE` en garde cinq et que cinq phrases courtes tiennent
    # dans 900 caracteres. Le banc n'atteignait jamais la branche qu'il
    # pretendait proteger.
    #
    # C'est le meme defaut que j'ai deja trouve trois fois dans ce depot : un
    # banc vert qui ne protege rien. Verifie par retrait, cette fois.
    actif.ouvrir("projet moteur", objectif="gagner 15 % de puissance")
    for i in range(8):
        actif.noter("hypothese", f"hypothèse {i} — " + "détail nécessaire " * 15)
        actif.noter("tache", f"tâche {i} — " + "à faire absolument " * 15)

    bloc = actif.bloc("et alors ?")

    assert len(bloc) <= actif.BUDGET, f"{len(bloc)} caractères pour un budget de {actif.BUDGET}"
    assert "demande LAQUELLE" in bloc, "la consigne survit à la troncature"


def test_le_projet_et_l_objectif_survivent_a_la_troncature(sans_projet):
    """Les lignes sont dans l'ordre d'importance : ce qui tombe est ce dont on
    peut se passer."""
    from nova.contexte import actif

    actif.ouvrir("projet moteur", objectif="gagner 15 % de puissance")
    for i in range(8):
        actif.noter("hypothese", f"hypothèse {i} — " + "détail nécessaire " * 15)

    bloc = actif.bloc("et alors ?")
    assert len(bloc) <= actif.BUDGET, "le banc doit atteindre la troncature"

    assert "Projet : projet moteur" in bloc
    assert "Objectif : gagner 15 % de puissance" in bloc


def test_lire_le_contexte_ne_coute_qu_un_aller_retour(sans_projet):
    """⚠️ UNE REQUETE PAR GENRE AURAIT COUTE CINQ ALLERS-RETOURS.

    Sur le chemin d'une reponse, et a chaque phrase. La jointure evite le
    defaut classique.
    """
    import time

    from nova.contexte import actif

    actif.ouvrir("projet moteur", objectif="gagner 15 %")
    for genre in ("decision", "hypothese", "tache", "entite", "question"):
        actif.noter(genre, f"un {genre} pour le banc")

    depart = time.perf_counter()
    for _ in range(20):
        actif.bloc("et alors ?")
    millisecondes = (time.perf_counter() - depart) * 1000 / 20

    assert millisecondes < 50, f"un bloc coûte {millisecondes:.1f} ms"
