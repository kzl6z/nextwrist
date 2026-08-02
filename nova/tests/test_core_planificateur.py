"""Le planificateur : ce que Nova compte faire, avant de le faire.

Deux exigences qui se contredisent en apparence :

  — planifier quand la demande le merite (l'expose en sept etapes) ;
  — ne JAMAIS planifier quand elle ne le merite pas (« quelle heure est-il »).

Et une troisieme qui prime sur les deux : le planificateur ne peut pas
echouer. Un modele absent, lent ou incoherent degrade la finesse du plan,
jamais la capacite de Nova a repondre.
"""

import json

from nova.core.contrats import CAPACITES_CONNUES, Demande
from nova.core.planificateur import (
    PATRONS,
    lire_plan,
    merite_un_plan,
    planifier,
    planifier_deterministe,
)


def test_l_exemple_du_projet_produit_sept_etapes():
    plan = planifier(Demande("Prepare-moi un expose sur Donald Trump"))
    assert len(plan.etapes) == 7
    assert plan.etapes[0].capacite == "raisonnement"
    assert plan.etapes[-1].capacite == "action"
    assert not plan.direct


def test_une_question_simple_reste_directe():
    # Le cas de loin le plus frequent : aucune machinerie ne doit se declencher.
    for phrase in ("quelle heure est-il", "merci", "bonjour Nova", "oui"):
        plan = planifier(Demande(phrase))
        assert plan.direct, phrase
        assert len(plan.etapes) == 1


def test_chaque_famille_connue_produit_son_plan():
    exemples = {
        "presentation": "fais-moi un powerpoint sur Rome",
        "developpement": "je veux developper une application de finances",
        "voyage": "je pars a Tokyo au mois de mars prochain",
        "document": "resume-moi ce rapport de trente pages",
        "recherche": "qui est Charles Aznavour exactement",
        "analyse_media": "analyse cette video que je viens de filmer",
        "impression_3d": "prepare cette piece pour l'impression 3d",
        "automatisation": "rappelle-moi chaque jour de relire mes notes",
    }
    assert set(exemples) == {famille for famille, _, _ in PATRONS}, (
        "un patron sans exemple n'est pas teste"
    )
    for famille, phrase in exemples.items():
        plan = planifier_deterministe(Demande(phrase))
        assert len(plan.etapes) >= 3, f"{famille} : {phrase}"
        assert not plan.direct, f"{famille} : {phrase}"


def test_les_etapes_s_enchainent():
    plan = planifier_deterministe(Demande("prepare un expose sur Rome"))
    assert plan.etapes[0].depend_de == ()
    assert plan.etapes[1].depend_de == (0,)
    assert plan.etapes[3].depend_de == (2,)


def test_toutes_les_capacites_des_patrons_sont_connues():
    # Un patron qui declare une capacite inventee produirait des etapes que
    # personne ne sait executer.
    for famille, _, etapes in PATRONS:
        for intitule, capacite in etapes:
            assert capacite in CAPACITES_CONNUES, f"{famille} / {intitule}"


# ── Le plan propose par un modele ─────────────────────────────────────────


def test_lit_un_plan_bien_forme():
    brut = json.dumps([
        {"intitule": "Comprendre", "capacite": "raisonnement"},
        {"intitule": "Rediger", "capacite": "redaction"},
    ])
    plan = lire_plan(brut, "peu importe")
    assert plan is not None and len(plan.etapes) == 2
    assert plan.origine == "modele"


def test_tolere_le_bavardage_autour_du_json():
    # Un petit modele entoure presque toujours sa reponse de texte.
    brut = 'Voici le plan :\n```json\n[{"intitule": "Chercher", "capacite": "recherche"}]\n```\nVoila.'
    plan = lire_plan(brut, "x")
    assert plan is not None and plan.etapes[0].intitule == "Chercher"


def test_tolere_une_liste_enveloppee_dans_un_objet():
    brut = json.dumps({"etapes": [{"intitule": "Chercher", "capacite": "recherche"}]})
    assert lire_plan(brut, "x") is not None


def test_tolere_une_simple_liste_de_chaines():
    plan = lire_plan(json.dumps(["Comprendre", "Rediger"]), "x")
    assert plan is not None and len(plan.etapes) == 2


def test_une_capacite_inventee_est_ramenee_au_raisonnement():
    # Plutot que de jeter l'etape : l'intitule reste utile.
    plan = lire_plan(json.dumps([{"intitule": "Voir", "capacite": "telepathie"}]), "x")
    assert plan is not None and plan.etapes[0].capacite == "raisonnement"


def test_une_proposition_inexploitable_rend_none():
    for brut in ("", "je ne sais pas faire", "[]", "{}", "[{}]", "null"):
        assert lire_plan(brut, "x") is None, brut


# ── Le planificateur ne peut pas echouer ──────────────────────────────────


def test_un_modele_qui_leve_ne_bloque_pas():
    def casse(consigne, demande):
        raise RuntimeError("moteur injoignable")

    plan = planifier(Demande("prepare un expose sur Rome"), proposer=casse)
    assert len(plan.etapes) == 7
    assert plan.origine == "repli"


def test_un_modele_qui_repond_n_importe_quoi_ne_bloque_pas():
    plan = planifier(Demande("prepare un expose sur Rome"), proposer=lambda c, d: "bonjour !")
    assert len(plan.etapes) == 7
    assert plan.origine == "repli"


def test_un_modele_utile_est_utilise():
    bon = json.dumps([{"intitule": "Faire", "capacite": "action"}])
    plan = planifier(Demande("prepare un expose sur Rome"), proposer=lambda c, d: bon)
    assert plan.origine == "modele" and len(plan.etapes) == 1


def test_le_modele_n_est_pas_appele_pour_une_phrase_simple():
    appels = []
    planifier(Demande("merci"), proposer=lambda c, d: appels.append(1) or "[]")
    assert appels == [], "planifier « merci » coute plus que ca ne rapporte"


def test_merite_un_plan_sur_la_longueur_ou_la_famille():
    assert merite_un_plan(Demande("fais-moi un expose"))          # famille
    assert merite_un_plan(Demande("a" * 60))                      # longueur
    assert not merite_un_plan(Demande("merci"))
