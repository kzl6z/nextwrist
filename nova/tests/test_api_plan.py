"""Le plan, vu de l'exterieur.

POURQUOI CE BANC EXISTE SEPAREMENT

`test_core_planificateur.py` verifie que le planificateur pense juste. Celui-ci
verifie qu'il le DIT — ce qui n'est pas la meme chose et ne casse pas au meme
moment.

Le cas concret : la nature de la demande etait calculee par le planificateur
depuis toujours, et jetee au moment de repondre. Un banc de module l'aurait
trouvee correcte ; l'interface, elle, ne la recevait pas. Une propriete
verifiee a l'interieur et perdue a la frontiere est une propriete absente.

⚠️ CE POINT D'ENTREE EST SUR LE CHEMIN DE CHAQUE DEMANDE.

L'interface l'appelle avant que Nova ne reponde. Il ne doit donc jamais
appeler de modele, jamais lire la base, jamais attendre — et c'est verifie
ici, pas seulement espere.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from nova.api.app import app

client = TestClient(app)


def demander(texte: str) -> dict:
    reponse = client.post("/v1/plan", json={"texte": texte})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


# ── Les quatre exemples du cahier des charges ─────────────────────────────


def test_question_simple():
    """Exemple 1 : aucune machinerie ne doit se declencher."""
    corps = demander("Qu'est-ce qu'un trou noir ?")

    assert corps["direct"] is True
    assert corps["type"] == "question_simple"
    assert len(corps["etapes"]) == 1
    assert corps["confirmation_requise"] is False
    assert corps["memoire_utile"] is False


def test_tache_complexe():
    """Exemple 2 : « Prepare-moi un expose sur les trous noirs. »"""
    corps = demander("Prepare-moi un expose sur les trous noirs.")

    assert corps["direct"] is False
    assert corps["type"] == "creation"
    assert len(corps["etapes"]) >= 5
    # Les etapes sont numerotees et enchainees : c'est ce qui permettra a
    # l'executeur de savoir ce qu'il peut lancer tout de suite.
    assert [e["numero"] for e in corps["etapes"]] == list(
        range(1, len(corps["etapes"]) + 1)
    )
    assert corps["etapes"][0]["depend_de"] == []
    assert corps["etapes"][1]["depend_de"] == [0]


def test_voyage():
    """Exemple 3 : plusieurs etapes, et rien de reserve."""
    corps = demander("Nova, organise-moi un voyage a Chicago la semaine prochaine.")

    assert corps["type"] == "tache_multi_etapes"
    assert len(corps["etapes"]) >= 4
    # ⚠️ AUCUNE ETAPE NE DIT AVOIR RESERVE QUOI QUE CE SOIT.
    #
    # Le planificateur planifie ; il n'execute pas. Un plan qui affirmerait
    # une reservation ferait croire a l'utilisateur qu'un billet existe.
    assert all(e["statut"] == "en_attente" for e in corps["etapes"])


def test_analyse_multimodale():
    """Exemple 4 : le cas qui ne produisait aucun plan."""
    corps = demander(
        "Nova, analyse cette trottinette et dis-moi pourquoi elle ne fonctionne plus."
    )

    assert corps["direct"] is False
    assert corps["type"] == "analyse"
    assert corps["etapes"][0]["capacite"] == "vision"


# ── La memoire, et la confirmation ────────────────────────────────────────


def test_une_question_sur_soi_signale_la_memoire():
    assert demander("Quel est mon prenom ?")["memoire_utile"] is True


def test_une_action_consequente_est_signalee_a_l_appelant():
    """⚠️ L'INTERFACE DOIT POUVOIR PREVENIR AVANT, PAS APRES.

    Un plan qui contient une impression, un envoi ou un achat porte le
    drapeau jusqu'a l'appelant. Sans ca, la seule facon de decouvrir qu'une
    etape avait des consequences serait de l'executer.
    """
    corps = demander("prepare cette piece pour l'impression 3d")

    assert corps["confirmation_requise"] is True
    consequentes = [e for e in corps["etapes"] if e["confirmation_requise"]]
    assert consequentes, "aucune etape ne porte le drapeau"
    assert all(e["capacite"] == "action" for e in consequentes)


def test_afficher_un_espace_de_travail_ne_demande_pas_de_confirmation():
    """Exiger un accord pour AFFICHER apprendrait a confirmer sans lire."""
    corps = demander("Prepare-moi un expose sur les trous noirs.")

    assert corps["confirmation_requise"] is False
    assert corps["etapes"][-1]["capacite"] == "action"


# ── Le cout ───────────────────────────────────────────────────────────────


def test_le_point_d_entree_repond_sans_attendre():
    """⚠️ IL EST APPELE AVANT CHAQUE REPONSE DE NOVA.

    S'il prenait cinquante millisecondes, il les ajouterait a tout — y
    compris a « quelle heure est-il », qui se repond aujourd'hui sans
    appeler le moindre modele.
    """
    demander("preparation")  # premiere requete : imports et registres

    debut = time.perf_counter()
    for _ in range(50):
        demander("Quelle est la capitale de la France ?")
    par_appel_ms = (time.perf_counter() - debut) / 50 * 1000

    # 50 ms couvre largement le trajet HTTP local du client de test. Ce banc
    # attrape une regression d'ordre de grandeur — un appel modele glisse
    # dans le chemin, une lecture de base — pas la variabilite d'une machine
    # de test partagee.
    assert par_appel_ms < 50, f"{par_appel_ms:.1f} ms par appel"
