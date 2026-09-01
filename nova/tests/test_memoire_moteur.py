"""Le Memory Engine : retenir, rappeler, mettre a jour, oublier.

⚠️ CE QUE L'ANALYSE A TROUVE AVANT D'ECRIRE UNE LIGNE.

    « souviens-toi que mon projet s'appelle NOVA »
    → intention « memoire » reconnue, AUCUNE action derriere, 0 fait en base

Le seul chemin d'ecriture etait la ligne de commande et l'API
d'administration. La recette du cahier des charges — memoriser, redemarrer,
se rappeler — ne pouvait pas passer. Ce n'etait pas une amelioration a faire,
c'etait un trou.

CE QUE CES BANCS PROTEGENT, ET CE QU'ILS NE TOUCHENT PAS

Ils s'arretent au moteur : decision, selection, contradiction, oubli. Aucun
n'a besoin de base — c'est ce qui permet de les faire tourner partout, et la
lecon des bancs de fichiers qui passaient ici et tombaient sur le Mac.

Le cablage jusqu'a la base a ses propres bancs, dans `test_memoire_bout_en_bout`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nova.memory import moteur
from nova.memory.models import Fact


def _fait(
    identifiant: int,
    contenu: str,
    *,
    importance: str = "moyenne",
    statut: str = "confirmed",
    expire=None,
    quand=None,
) -> Fact:
    return Fact(
        id=identifiant,
        category="profil",
        content=contenu,
        status=statut,
        origin="user",
        confidence=1.0,
        source=None,
        created_at=quand or datetime.now(UTC),
        importance=importance,
        expires_at=expire,
    )


# ══════════════════════════════════════════════════════════════════════════
#  1 & 3. LA DECISION — CE QU'ON RETIENT, ET SURTOUT CE QU'ON NE RETIENT PAS
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "souviens-toi que mon projet s'appelle NOVA",
        "retiens que je préfère les réponses courtes",
        "note que mon modèle principal est llama",
        "n'oublie pas que je suis allergique aux arachides",
        "garde en mémoire que je travaille sur un iMac M1",
        "mémorise mon adresse",
    ],
)
def test_une_demande_explicite_est_retenue(phrase):
    assert moteur.demande_de_retenir(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ LES EXEMPLES DU CAHIER DES CHARGES, MOT POUR MOT.
        "il fait chaud aujourd'hui",
        "j'ai mangé une pizza",
        # Une conversation ordinaire n'est pas une demande de memoire.
        "quelle heure est-il",
        "parle-moi des trous noirs",
        "ouvre Chrome",
        "retrouve mes impôts de 2024",
        "",
    ],
)
def test_ce_qui_ne_merite_pas_d_etre_retenu(phrase):
    """⚠️ NOVA NE MEMORISE PAS TOUT CE QU'ON DIT, ET C'EST UNE PROTECTION.

    Deduire seule ce qui merite d'etre garde est la premiere cause de
    pourrissement d'une memoire — le risque R5, deja nomme dans `facts.py` :
    au bout d'un an, Nova est confiante et fausse.

    On commence donc par ce qui ne peut pas se tromper : ce que TU demandes.
    Le schema prevoit deja l'autre cas — `origin` separe le declare du deduit,
    et le deduit entre en `proposed`, pas en `confirmed`.
    """
    assert not moteur.demande_de_retenir(phrase), phrase


def test_on_stocke_le_fait_pas_la_phrase_qui_l_a_dit():
    """« souviens-toi que X » n'est pas une information sur l'utilisateur."""
    assert (
        moteur.contenu_a_retenir("souviens-toi que mon projet s'appelle NOVA")
        == "mon projet s'appelle NOVA"
    )
    assert moteur.contenu_a_retenir("retiens que je préfère le café") == (
        "je préfère le café"
    )


@pytest.mark.parametrize(
    ("contenu", "attendue"),
    [
        ("mon projet s'appelle NOVA", "projet"),
        ("je préfère les réponses courtes", "preference"),
        ("je suis allergique aux arachides", "contrainte"),
        ("mon objectif est de finir en juin", "objectif"),
        ("ma soeur s'appelle Bérangère", "profil"),
    ],
)
def test_la_categorie_est_proposee_pas_devinee_au_hasard(contenu, attendue):
    assert moteur.categorie_probable(contenu) == attendue


# ══════════════════════════════════════════════════════════════════════════
#  8. TEMPORAIRE CONTRE DURABLE
# ══════════════════════════════════════════════════════════════════════════
def test_une_information_datee_recoit_une_peremption():
    assert moteur.peremption_probable("je suis à Paris cette semaine") is not None
    assert moteur.peremption_probable("j'ai un rendez-vous demain") is not None


def test_une_information_durable_n_expire_jamais():
    assert moteur.peremption_probable("mon projet s'appelle NOVA") is None
    assert moteur.peremption_probable("je suis allergique aux arachides") is None


def test_un_fait_perime_sort_de_la_memoire_active():
    """⚠️ PERIME N'EST PAS SUPPRIME.

    On cesse de s'en servir, on ne l'efface pas — c'est ce qui distingue
    l'oubli de l'effacement, et c'est deja la regle de `archive`.
    """
    hier = datetime.now(UTC) - timedelta(days=1)
    memoire = [
        _fait(1, "je suis à Paris", expire=hier),
        _fait(2, "mon projet s'appelle NOVA"),
    ]

    actifs = moteur.actifs(memoire)

    assert [f.id for f in actifs] == [2]


# ══════════════════════════════════════════════════════════════════════════
#  4 & 9. LA SELECTION — ET L'OBJECTION QU'ELLE DOIT SURMONTER
# ══════════════════════════════════════════════════════════════════════════
def test_la_question_fait_remonter_le_fait_qui_y_repond():
    memoire = [
        _fait(1, "j'habite à Lyon"),
        _fait(2, "mon projet s'appelle NOVA"),
        _fait(3, "ma soeur s'appelle Bérangère"),
    ]

    retenus = moteur.pertinents("comment s'appelle mon projet ?", memoire, budget=200)

    assert retenus[0].id == 2


def test_un_fait_critique_passe_meme_sans_rapport_avec_la_question():
    """⚠️ CE BANC REPOND A UNE OBJECTION DE `facts.py` QUI ETAIT JUSTE.

    « Chercher les faits par similarite serait une erreur : le fait important
    est souvent celui qui ne ressemble pas a la question. » Une allergie n'a
    aucun mot commun avec « propose-moi un restaurant », et c'est precisement
    celui qu'il ne faut pas rater.

    L'importance donne donc un PLANCHER que le recouvrement de mots ne fait
    que hausser. Elle n'abaisse jamais rien.
    """
    memoire = [
        _fait(1, "je suis allergique aux arachides", importance="critique"),
        _fait(2, "mon projet s'appelle NOVA"),
        _fait(3, "j'habite à Lyon"),
    ]

    retenus = moteur.pertinents("propose-moi un restaurant", memoire, budget=60)

    assert 1 in [f.id for f in retenus], "l'allergie doit passer, quoi qu'il arrive"


def test_le_budget_ne_tronque_plus_par_date():
    """⚠️ LA TRONCATURE PAR DATE FAISAIT DISPARAITRE LE CRITIQUE, EN SILENCE.

    `render_for_prompt` gardait les plus RECENTS. A vingt faits cela ne se
    voyait pas ; a trois cents, un fait critique de l'an dernier passait
    derriere trois preferences notees hier — sans un mot dans le journal.
    """
    vieux_critique = _fait(
        1,
        "je suis allergique aux arachides",
        importance="critique",
        quand=datetime.now(UTC) - timedelta(days=400),
    )
    recents = [
        _fait(i, f"préférence récente numéro {i} avec du texte pour occuper la place")
        for i in range(2, 8)
    ]

    retenus = moteur.pertinents("bonjour", [*recents, vieux_critique], budget=100)

    assert retenus[0].id == 1, "le critique passe en tete malgre son age"


def test_sans_aucun_fait_la_selection_ne_rend_rien():
    assert moteur.pertinents("bonjour", [], budget=1000) == []


# ══════════════════════════════════════════════════════════════════════════
#  5 & 6. MISE A JOUR ET CONTRADICTION
# ══════════════════════════════════════════════════════════════════════════
def test_deux_faits_sur_le_meme_sujet_sont_reperes():
    """⚠️ « MEME SUJET » N'EST PAS « DIT LE CONTRAIRE », ET C'EST ASSUME.

    Etablir qu'une phrase contredit une autre demanderait de comprendre les
    deux — donc un modele, donc un appel, donc du temps sur le chemin d'une
    reponse. Et un modele de trois milliards de parametres s'y trompe.

    Reperer que deux faits portent sur le meme SUJET se fait sans modele et
    sans se tromper. Si les deux etaient compatibles, on a perdu une redite ;
    s'ils se contredisaient, on a evite que le modele choisisse au hasard.
    """
    existants = [
        _fait(1, "le modèle principal de NOVA est llama"),
        _fait(2, "j'habite à Lyon"),
    ]

    trouves = moteur.contradictions("le modèle principal de NOVA est qwen", existants)

    assert [f.id for f in trouves] == [1]


def test_deux_faits_sans_rapport_ne_se_contredisent_pas():
    existants = [_fait(1, "j'habite à Lyon"), _fait(2, "ma soeur s'appelle Bérangère")]

    assert moteur.contradictions("mon projet s'appelle NOVA", existants) == []


def test_un_fait_archive_ne_contredit_plus_rien():
    """Ce qui a deja ete oublie n'a pas a etre oublie deux fois."""
    existants = [_fait(1, "le modèle principal est llama", statut="archived")]

    assert moteur.contradictions("le modèle principal est qwen", existants) == []


def test_le_recouvrement_est_une_proportion_pas_un_compte():
    """⚠️ MEME REGLE QUE LE CLASSEMENT DES FICHIERS ET DES IMAGES.

    Compter les mots communs ferait gagner les faits LONGS : une phrase de
    trente mots en partage forcement quelques-uns avec tout le monde.
    """
    court = "mon projet s'appelle NOVA"
    long = (
        "mon projet s'appelle NOVA et il comporte un planificateur, un "
        "executeur, un gestionnaire d'agents et un routeur de modèles"
    )

    assert moteur.recouvrement(court, court) == 1.0
    assert moteur.recouvrement(court, "j'habite à Lyon") == 0.0
    # Le long contient le court en entier : la proportion vaut 1 sur le plus
    # petit des deux, ce qui est bien « ils parlent de la meme chose ».
    assert moteur.recouvrement(court, long) == 1.0


# ══════════════════════════════════════════════════════════════════════════
#  7. L'OUBLI
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "oublie ça",
        "Nova, oublie ça",
        "supprime cette information de ta mémoire",
        "efface ça",
        "ne te souviens plus de mon adresse",
    ],
)
def test_une_demande_d_oubli_se_reconnait(phrase):
    assert moteur.demande_d_oubli(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        "n'oublie pas que je suis allergique aux arachides",
        "souviens-toi que mon projet s'appelle NOVA",
        "quelle heure est-il",
    ],
)
def test_ce_qui_n_est_pas_une_demande_d_oubli(phrase):
    """⚠️ « N'OUBLIE PAS QUE… » EST UNE DEMANDE DE RETENIR, PAS D'OUBLIER.

    Les deux motifs contiennent le mot « oublie ». Les confondre effacerait
    une information au moment precis ou l'on demandait de la garder — le pire
    contresens possible pour une memoire.
    """
    assert not moteur.demande_d_oubli(phrase), phrase


def test_retenir_et_oublier_ne_se_declenchent_jamais_ensemble():
    """La garde qui rend l'ordre des branchements sans importance."""
    for phrase in (
        "n'oublie pas que je suis allergique aux arachides",
        "souviens-toi de mon anniversaire",
        "oublie ça",
        "efface cette information",
    ):
        assert not (
            moteur.demande_de_retenir(phrase) and moteur.demande_d_oubli(phrase)
        ), phrase


# ══════════════════════════════════════════════════════════════════════════
#  12. LE COUT
# ══════════════════════════════════════════════════════════════════════════
def test_la_selection_ne_coute_presque_rien():
    """⚠️ LA MEMOIRE NE DOIT PAS RALENTIR NOVA — C'EST UNE EXIGENCE.

    La selection se fait EN MEMOIRE, sur la liste deja mise en cache par
    l'orchestrateur : aucun aller-retour en base, aucun appel de modele. Ce
    banc mesure trois cents faits, bien au-dela de ce que la table est censee
    contenir.
    """
    import time

    memoire = [
        _fait(i, f"fait numéro {i} avec un contenu de longueur raisonnable")
        for i in range(300)
    ]

    depart = time.perf_counter()
    for _ in range(50):
        moteur.pertinents("comment s'appelle mon projet ?", memoire, budget=1200)
    millisecondes = (time.perf_counter() - depart) * 1000 / 50

    assert millisecondes < 30, f"une selection coûte {millisecondes:.1f} ms"


# ══════════════════════════════════════════════════════════════════════════
#  LE SEUIL DE CONTRADICTION — MESURE, PAS CHOISI
#
#  ⚠️ LA PREMIERE VALEUR A ETE PRISE EN DEFAUT PAR UN BANC.
#
#  Elle valait 0,55. « j'habite a Lyon » contre « j'habite a Paris » vaut
#  0,50 : deux faits qui se contredisent evidemment, et qui coexistaient donc
#  en base. Le seuil a ete refait sur quatorze paires reelles.
#
#  Ce banc fige la mesure. Sans lui, quelqu'un peut deplacer le seuil pour
#  faire passer un cas et casser les treize autres sans le voir.
# ══════════════════════════════════════════════════════════════════════════
MEME_SUJET = (
    ("j'habite à Lyon", "j'habite à Paris"),
    ("le modèle principal de NOVA est llama", "le modèle principal de NOVA est qwen"),
    ("mon projet s'appelle NOVA", "mon projet s'appelle Sentinel"),
    ("je préfère les réponses courtes", "je préfère les réponses longues"),
    ("ma voiture est une Clio", "ma voiture est une Golf"),
    ("je travaille chez Renault", "je travaille chez Airbus"),
    ("mon anniversaire est le 3 mai", "mon anniversaire est le 4 juin"),
)

SUJETS_DIFFERENTS = (
    ("j'habite à Lyon", "mon projet s'appelle NOVA"),
    ("je suis allergique aux arachides", "je préfère les réponses courtes"),
    ("mon projet s'appelle NOVA", "je travaille sur un iMac M1"),
    ("ma soeur s'appelle Bérangère", "mon projet s'appelle NOVA"),
    ("je préfère les réponses courtes", "mon anniversaire est le 3 mai"),
    ("j'habite à Lyon", "je travaille chez Renault"),
    ("le modèle principal est llama", "mon projet s'appelle NOVA"),
)


@pytest.mark.parametrize(("a", "b"), MEME_SUJET)
def test_deux_faits_du_meme_sujet_depassent_le_seuil(a, b):
    assert moteur.recouvrement(a, b) >= moteur.SEUIL_CONTRADICTION, f"{a} / {b}"


@pytest.mark.parametrize(("a", "b"), SUJETS_DIFFERENTS)
def test_deux_sujets_sans_rapport_restent_sous_le_seuil(a, b):
    assert moteur.recouvrement(a, b) < moteur.SEUIL_CONTRADICTION, f"{a} / {b}"


def test_les_deux_classes_se_separent_avec_de_la_marge():
    """⚠️ CE N'ETAIT PAS ACQUIS, ET CA NE L'EST PAS TOUJOURS.

    Le rapprochement phonetique des fichiers, lui, n'a AUCUN seuil qui
    separe : « empeaux »→impots vaut 0,67 et « porsche »→impots aussi. C'est
    pour cela qu'il ne corrige jamais en silence, et qu'il annonce ce qu'il a
    compris.

    Ici, il y a un intervalle. Ce banc verifie qu'il existe encore — le jour
    ou une paire le referme, la reponse n'est pas de bouger le seuil, c'est de
    changer de methode.
    """
    plus_bas_des_memes = min(moteur.recouvrement(a, b) for a, b in MEME_SUJET)
    plus_haut_des_autres = max(moteur.recouvrement(a, b) for a, b in SUJETS_DIFFERENTS)

    assert plus_haut_des_autres < plus_bas_des_memes, (
        f"les deux classes se chevauchent : {plus_haut_des_autres:.2f} "
        f"contre {plus_bas_des_memes:.2f}"
    )
    assert plus_haut_des_autres < moteur.SEUIL_CONTRADICTION < plus_bas_des_memes
