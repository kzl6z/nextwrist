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
    action_a_confirmer,
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
        "diagnostic": "regarde ma trottinette, elle ne fonctionne plus",
        "automatisation": "rappelle-moi chaque jour de relire mes notes",
    }
    assert set(exemples) == {famille for famille, _, _, _ in PATRONS}, (
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
    for famille, _nature, _declencheurs, etapes in PATRONS:
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
    brut = (
        'Voici le plan :\n```json\n'
        '[{"intitule": "Chercher", "capacite": "recherche"}]\n'
        '```\nVoila.'
    )
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


# ══════════════════════════════════════════════════════════════════════════
#  LA NATURE DE LA DEMANDE
#
#  Elle etait calculee puis jetee : le planificateur reconnaissait « voyage »
#  ou « presentation », s'en servait pour choisir les etapes, et n'en gardait
#  aucune trace. L'appelant devait redeviner ce que le planificateur savait.
# ══════════════════════════════════════════════════════════════════════════
def test_une_question_simple_est_nommee_comme_telle():
    """Exemple 1 du cahier des charges : aucune machinerie, et le dire."""
    plan = planifier(Demande("Qu'est-ce qu'un trou noir ?"))

    assert plan.direct
    assert plan.type == "question_simple"
    assert len(plan.etapes) == 1


def test_une_civilite_n_est_pas_une_question():
    """⚠️ MEME PLAN, TYPES DIFFERENTS — ET L'ECART COMPTE.

    « merci » et « qu'est-ce qu'un trou noir » tiennent tous deux en une
    etape. Mais l'un n'appellera jamais ni memoire, ni recherche, ni espace de
    travail, alors que l'autre le pourra. Un seul type pour les deux forcerait
    a redeviner lequel c'est.
    """
    for civilite in ("merci", "bonjour Nova", "oui"):
        assert planifier(Demande(civilite)).type == "conversation", civilite


def test_chaque_famille_annonce_une_nature_connue():
    from nova.core.contrats import TYPES_CONNUS

    for famille, nature, _, _ in PATRONS:
        assert nature in TYPES_CONNUS, f"{famille} declare « {nature} »"


# ══════════════════════════════════════════════════════════════════════════
#  LA MEMOIRE PERSONNELLE
# ══════════════════════════════════════════════════════════════════════════
def test_une_question_sur_soi_reclame_la_memoire():
    assert planifier(Demande("Quel est mon prenom ?")).memoire_utile


def test_une_question_de_culture_generale_ne_la_reclame_pas():
    assert not planifier(Demande("Qu'est-ce qu'un trou noir ?")).memoire_utile


def test_le_moi_accroche_a_un_verbe_ne_compte_pas():
    """⚠️ « parle-moi de Mars » NE PARLE PAS DE TOI.

    Le pronom y est le complement du verbe, pas le sujet de la demande. Sans
    cette exclusion, la moitie des questions de culture generale seraient
    marquees personnelles — et un signal qui s'allume toujours ne signale
    plus rien.
    """
    for phrase in ("parle-moi de Mars", "explique-moi la relativite", "dis-moi l'heure"):
        assert not planifier(Demande(phrase)).memoire_utile, phrase


# ══════════════════════════════════════════════════════════════════════════
#  LES ACTIONS QUI SORTENT DE LA MACHINE
# ══════════════════════════════════════════════════════════════════════════
def test_une_etape_sans_consequence_externe_n_est_pas_marquee():
    """⚠️ LA CAPACITE « action » NE SUFFIT PAS A DECIDER.

    « Presenter l'espace de travail » est une action : elle affiche. Exiger
    une confirmation pour afficher quelque chose apprendrait a l'utilisateur
    a confirmer sans lire — et la confirmation ne protegerait plus rien.
    """
    plan = planifier_deterministe(Demande("prepare un expose sur Rome"))

    assert not plan.demande_confirmation
    assert plan.etapes[-1].capacite == "action"


def test_les_verbes_de_consequence_sont_reconnus():
    for intitule in (
        "Envoyer le message a Paul",
        "Reserver le vol",
        "Acheter le billet",
        "Supprimer les fichiers",
        "Passer l'appel",
        "Lancer l'impression",
    ):
        assert action_a_confirmer(intitule, "action"), intitule


def test_un_verbe_de_consequence_hors_action_ne_marque_rien():
    """« Comprendre ce qu'il faut envoyer » ne fait rien du tout."""
    assert not action_a_confirmer("Comprendre ce qu'il faut envoyer", "raisonnement")
    assert not action_a_confirmer("Rechercher les vols a reserver", "recherche")


def test_l_impression_3d_demande_une_confirmation():
    """Un plan qui va lancer une machine doit le dire avant, pas apres."""
    plan = planifier_deterministe(Demande("prepare cette piece pour l'impression 3d"))

    assert plan.demande_confirmation
    assert any(e.confirmation_requise and e.capacite == "action" for e in plan.etapes)


# ══════════════════════════════════════════════════════════════════════════
#  LES FAMILLES DU CAHIER DES CHARGES
# ══════════════════════════════════════════════════════════════════════════
def test_la_tache_complexe_produit_un_plan_multi_etapes():
    """Exemple 2 : « Prepare-moi un expose sur les trous noirs. »"""
    plan = planifier(Demande("Prepare-moi un expose sur les trous noirs."))

    assert plan.type == "creation"
    assert len(plan.etapes) >= 5
    assert {e.capacite for e in plan.etapes} >= {"recherche", "redaction"}


def test_le_voyage_produit_un_plan_multi_etapes():
    """Exemple 3 : « organise-moi un voyage a Chicago la semaine prochaine »"""
    plan = planifier(Demande("Nova, organise-moi un voyage a Chicago la semaine prochaine."))

    assert plan.type == "tache_multi_etapes"
    assert len(plan.etapes) >= 4


def test_le_diagnostic_d_un_objet_produit_un_plan_multimodal():
    """⚠️ EXEMPLE 4 — CE CAS ETAIT UNE CONTRADICTION INTERNE.

    « Nova, analyse cette trottinette et dis-moi pourquoi elle ne fonctionne
    plus » passait la porte `merite_un_plan` — soixante-seize caracteres — et
    ne correspondait a aucun patron. Le planificateur declarait donc que la
    demande meritait un plan, puis rendait une seule etape « Repondre ».

    Rien ne le signalait : un plan direct est un resultat valide. Seul un
    essai sur les exemples du cahier des charges l'a montre.
    """
    plan = planifier(
        Demande("Nova, analyse cette trottinette et dis-moi pourquoi elle ne fonctionne plus.")
    )

    assert not plan.direct, "la demande merite un plan et n'en recevait aucun"
    assert plan.type == "analyse"
    assert plan.etapes[0].capacite == "vision"


def test_la_porte_et_les_patrons_ne_se_contredisent_pas():
    """⚠️ LE BANC QUI AURAIT ATTRAPE LE DEFAUT PRECEDENT.

    Si `merite_un_plan` dit oui, un patron doit suivre — sinon le
    planificateur promet un decoupage qu'il ne fournit pas. La seule
    exception legitime est la demande longue sans famille reconnue, ou le
    modele prend le relais quand il est disponible.
    """
    exemples_de_famille = (
        "prepare un expose sur Rome",
        "organise-moi un voyage a Tokyo",
        "analyse cette trottinette, elle ne fonctionne plus",
        "rappelle-moi chaque jour de relire mes notes",
        "prepare cette piece pour l'impression 3d",
    )
    for phrase in exemples_de_famille:
        demande = Demande(phrase)
        assert merite_un_plan(demande), phrase
        assert not planifier(demande).direct, (
            f"« {phrase} » merite un plan mais n'en recoit aucun"
        )


# ══════════════════════════════════════════════════════════════════════════
#  LA NUMEROTATION
# ══════════════════════════════════════════════════════════════════════════
def test_les_numeros_suivent_toujours_les_dependances():
    """⚠️ UNE SEULE SOURCE DE VERITE POUR LE RANG D'UNE ETAPE.

    Le numero affiche et les indices de `depend_de` decrivent la meme
    position. Saisis separement, ils finiraient par se contredire — et un
    plan dont les dependances pointent ailleurs que ce qu'il affiche est pire
    qu'un plan sans numeros.
    """
    plan = planifier_deterministe(Demande("prepare un expose sur Rome"))

    for rang, etape in enumerate(plan.etapes):
        assert etape.numero == rang + 1
        for indice in etape.depend_de:
            assert plan.etapes[indice].numero == indice + 1


def test_les_statuts_sortent_tous_en_attente():
    """Planifier n'est pas faire. Aucune etape ne peut se dire accomplie."""
    plan = planifier_deterministe(Demande("organise-moi un voyage a Tokyo"))

    assert all(e.statut == "en_attente" for e in plan.etapes)


# ══════════════════════════════════════════════════════════════════════════
#  LE COUT
# ══════════════════════════════════════════════════════════════════════════
def test_planifier_ne_coute_rien_sur_une_demande_simple():
    """⚠️ LE PLANIFICATEUR EST SUR LE CHEMIN DE CHAQUE PHRASE.

    Il s'execute avant que Nova ne reponde, y compris pour « quelle heure
    est-il ». S'il coutait ne serait-ce que dix millisecondes, il les
    ajouterait a tout — et la premiere chose qu'on ferait serait de le
    desactiver.
    """
    import time

    phrases = ("quelle heure est-il", "merci", "Quelle est la capitale de la France ?")
    debut = time.perf_counter()
    for _ in range(1000):
        for phrase in phrases:
            planifier(Demande(phrase))
    par_appel_us = (time.perf_counter() - debut) / (1000 * len(phrases)) * 1e6

    # 500 µs est deja mille fois moins que la plus rapide des etapes reelles.
    # La marge est large a dessein : ce banc doit attraper une regression
    # d'ordre de grandeur — un appel modele glisse ici, une lecture de base —
    # pas la variabilite d'une machine de test partagee.
    assert par_appel_us < 500, f"{par_appel_us:.0f} µs par plan"


def test_planifier_une_tache_complexe_reste_gratuit():
    """Sept etapes ne coutent pas plus que une : c'est de la reconnaissance."""
    import time

    debut = time.perf_counter()
    for _ in range(1000):
        planifier(Demande("Prepare-moi un expose sur les trous noirs."))
    par_appel_us = (time.perf_counter() - debut) / 1000 * 1e6

    assert par_appel_us < 500, f"{par_appel_us:.0f} µs par plan"
