"""L'executeur : ce banc protege une seule promesse.

    Une etape non accomplie ne doit JAMAIS ressembler a une etape accomplie.

C'est la contrainte la plus forte du cahier des charges, et la plus facile a
trahir par inadvertance. Un executeur qui rend « voyage organise » alors
qu'aucun billet n'existe ne se trompe pas un peu : il fait croire a
l'utilisateur qu'il peut partir.

La plupart des tests ci-dessous verifient donc une ABSENCE — que `faite`
n'apparait pas — plutot qu'une presence. Ce sont les plus importants, et ce
sont ceux qu'on oublie d'ecrire.
"""

from __future__ import annotations

import time

import pytest

from nova.core.contrats import Etape, Plan
from nova.core.executeur import bloquees, executer, vagues
from nova.outils import ConfirmationRequise


def plan_de(*etapes: Etape) -> Plan:
    return Plan(demande="essai", etapes=etapes)


def chaine(*intitules: str, capacite: str = "raisonnement") -> Plan:
    """Un plan en chaine, comme ceux que produit le planificateur."""
    return plan_de(
        *(
            Etape(intitule, capacite, depend_de=(i - 1,) if i else ())
            for i, intitule in enumerate(intitules)
        )
    )


# ══════════════════════════════════════════════════════════════════════════
#  RIEN NE DOIT PASSER POUR ACCOMPLI
# ══════════════════════════════════════════════════════════════════════════
def test_sans_executant_rien_n_est_accompli():
    """⚠️ C'EST L'ETAT D'AUJOURD'HUI : LE GESTIONNAIRE D'AGENTS N'EXISTE PAS.

    Appeler l'executeur maintenant doit rendre un compte rendu honnete — un
    manque, nomme — et surtout pas un succes.
    """
    execution = executer(chaine("Chercher", "Rediger"))

    assert not execution.accomplie
    assert execution.statut == "incomplete"
    assert all(r.statut == "ignoree" for r in execution.resultats)
    assert "aucun executant" in execution.resultats[0].detail


def test_un_executant_qui_ne_rend_rien_n_accomplit_rien():
    """Un executant muet n'a probablement rien fait — et dans le doute,
    l'erreur qui coute le moins cher est de le dire."""
    execution = executer(chaine("Faire"), executant=lambda etape: None)

    assert not execution.accomplie
    assert execution.resultats[0].statut == "ignoree"
    assert "rien produit" in execution.resultats[0].detail


def test_une_etape_dont_la_dependance_a_echoue_n_est_jamais_tentee():
    """⚠️ LA LANCER PRODUIRAIT UN RESULTAT QUI A L'AIR VALIDE.

    Rediger des diapositives sur une recherche qui n'a pas eu lieu donne un
    texte — un texte faux, mais un texte. C'est exactement le genre de sortie
    qu'on ne peut plus distinguer d'un vrai resultat.
    """
    tentees: list[str] = []

    def executant(etape):
        tentees.append(etape.intitule)
        if etape.intitule == "Chercher":
            raise RuntimeError("reseau indisponible")
        return "fait"

    execution = executer(chaine("Chercher", "Rediger", "Presenter"), executant=executant)

    assert tentees == ["Chercher"], "une etape a ete tentee sur une base absente"
    assert execution.resultats[0].statut == "echouee"
    assert execution.resultats[1].statut == "ignoree"
    assert "n'a pas abouti" in execution.resultats[1].detail
    assert not execution.accomplie


def test_toutes_les_etapes_figurent_au_compte_rendu():
    """Omettre les etapes jamais atteintes laisserait croire qu'un plan de
    sept etapes n'en comptait que deux."""
    plan = chaine("Un", "Deux", "Trois", "Quatre")

    def executant(etape):
        raise RuntimeError("panne") if etape.intitule == "Deux" else "fait"

    execution = executer(plan, executant=lambda e: 1 / 0 if e.numero == 2 else "fait")

    assert len(execution.resultats) == len(plan.etapes)
    assert [r.numero for r in execution.resultats] == [1, 2, 3, 4]


def test_accomplie_exige_que_TOUT_soit_fait():
    fait = executer(chaine("Un", "Deux"), executant=lambda e: "ok")
    partiel = executer(chaine("Un", "Deux"), executant=lambda e: "ok" if e.numero == 1 else None)

    assert fait.accomplie and fait.statut == "terminee"
    assert not partiel.accomplie


# ══════════════════════════════════════════════════════════════════════════
#  LA CONFIRMATION
# ══════════════════════════════════════════════════════════════════════════
def test_une_action_a_confirmer_arrete_l_execution():
    """⚠️ ON S'ARRETE, ON NE SAUTE PAS.

    Sauter l'etape pour continuer executerait les suivantes sur une base
    absente — et produirait un compte rendu qui a l'air complet.
    """
    plan = plan_de(
        Etape("Preparer le fichier", "action"),
        Etape("Lancer l'impression", "action", depend_de=(0,), confirmation_requise=True),
        Etape("Ranger", "action", depend_de=(1,)),
    )
    tentees: list[int] = []

    execution = executer(plan, executant=lambda e: tentees.append(e.numero) or "fait")

    assert execution.statut == "a_confirmer"
    assert execution.a_confirmer == (2,)
    assert 3 not in tentees, "une etape a ete executee apres l'arret"
    assert execution.resultats[2].statut == "ignoree"
    assert not execution.accomplie


def test_une_action_confirmee_par_l_utilisateur_s_execute():
    plan = plan_de(
        Etape("Lancer l'impression", "action", confirmation_requise=True),
    )

    execution = executer(plan, executant=lambda e: "imprime", confirmees=[1])

    assert execution.statut == "terminee"
    assert execution.resultats[0].accomplie


def test_une_confirmation_venue_de_l_executant_arrete_aussi():
    """`ConfirmationRequise` peut venir d'un outil, pas seulement du plan.

    Le planificateur marque ce qu'il reconnait ; le registre d'outils marque
    ce qu'il sait de chaque outil. Les deux chemins doivent aboutir au meme
    arret — sinon un outil dangereux passerait parce que le plan ne l'avait
    pas devine.
    """
    def executant(etape):
        raise ConfirmationRequise("supprimer", 3, {"chemin": "/tmp/x"})

    execution = executer(chaine("Nettoyer", "Verifier"), executant=executant)

    assert execution.statut == "a_confirmer"
    assert execution.a_confirmer == (1,)
    assert execution.resultats[1].statut == "ignoree"


def test_le_statut_a_confirmer_prime_sur_l_echec():
    """Un plan a la fois interrompu et casse se presente comme interrompu :
    l'action attendue de l'utilisateur prime sur le constat."""
    # Deux etapes INDEPENDANTES : elles partagent la premiere vague, donc les
    # deux sont atteintes. L'une casse, l'autre attend un accord.
    plan = plan_de(
        Etape("Essayer", "action"),
        Etape("Envoyer", "action", confirmation_requise=True),
    )

    def executant(etape):
        if etape.numero == 1:
            raise RuntimeError("echec de l'essai")
        return "ok"

    execution = executer(plan, executant=executant)

    assert execution.resultats[0].statut == "echouee", "le banc ne teste pas ce qu'il annonce"
    assert execution.statut == "a_confirmer"


# ══════════════════════════════════════════════════════════════════════════
#  L'ORDRE DE PARCOURS
# ══════════════════════════════════════════════════════════════════════════
def test_une_chaine_donne_une_etape_par_vague():
    assert vagues(chaine("Un", "Deux", "Trois")) == ((0,), (1,), (2,))


def test_deux_etapes_independantes_partagent_une_vague():
    """⚠️ LE DECOUPAGE EXISTE AVANT LA PARALLELISATION, PAS APRES.

    Les plans d'aujourd'hui sont des chaines. Le jour ou un plan proposera
    deux recherches independantes, elles se retrouveront dans la meme vague
    sans qu'une ligne de l'executeur change.
    """
    plan = plan_de(
        Etape("Cerner", "raisonnement"),
        Etape("Chercher les vols", "recherche", depend_de=(0,)),
        Etape("Chercher les hotels", "recherche", depend_de=(0,)),
        Etape("Comparer", "raisonnement", depend_de=(1, 2)),
    )

    assert vagues(plan) == ((0,), (1, 2), (3,))


def test_un_cycle_ne_boucle_pas():
    """Boucler serait pire que refuser, et supposer un ordre serait mentir."""
    plan = plan_de(
        Etape("A", "raisonnement", depend_de=(1,)),
        Etape("B", "raisonnement", depend_de=(0,)),
    )

    assert vagues(plan) == ()
    assert bloquees(plan) == (0, 1)

    execution = executer(plan, executant=lambda e: "fait")

    assert not execution.accomplie
    assert all("bloquee" in r.detail for r in execution.resultats)


def test_une_dependance_vers_une_etape_absente_bloque_sans_planter():
    plan = plan_de(Etape("Seule", "raisonnement", depend_de=(7,)))

    assert bloquees(plan) == (0,)
    assert not executer(plan, executant=lambda e: "fait").accomplie


# ══════════════════════════════════════════════════════════════════════════
#  L'EXECUTEUR NE TOMBE JAMAIS
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "casse",
    [
        lambda e: 1 / 0,
        lambda e: (_ for _ in ()).throw(MemoryError("plus de memoire")),
    ],
)
def test_un_executant_qui_leve_ne_fait_pas_tomber_le_compte_rendu(casse):
    """⚠️ UNE EXECUTION QUI CASSE EN ROUTE DOIT POUVOIR SE RACONTER.

    Laisser l'exception remonter ferait perdre tout le compte rendu : les
    etapes deja accomplies, celles qui restaient, la raison de l'arret.
    """
    execution = executer(chaine("Un", "Deux"), executant=casse)

    assert execution.statut == "echouee"
    assert len(execution.resultats) == 2


def test_une_interruption_clavier_remonte_toujours():
    """⚠️ CTRL-C N'EST PAS UNE ETAPE QUI ECHOUE, C'EST UN ORDRE D'ARRETER.

    Ce banc a d'abord ete ecrit a l'envers : il exigeait que l'executeur
    attrape `KeyboardInterrupt` comme le reste. Lance, il a bloque pytest —
    ce qui est exactement le comportement qu'on obtiendrait en production en
    essayant d'interrompre Nova pendant un plan.

    `except Exception` ne capture pas `KeyboardInterrupt`, et c'est
    deliberement le bon comportement : une execution qu'on ne peut plus
    arreter est pire qu'une execution qui casse.
    """
    def interrompt(etape):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        executer(chaine("Un"), executant=interrompt)


def test_un_plan_vide_ne_pretend_rien():
    execution = executer(plan_de())

    assert execution.resultats == ()
    assert not execution.accomplie


# ══════════════════════════════════════════════════════════════════════════
#  LE COUT
# ══════════════════════════════════════════════════════════════════════════
def test_le_parcours_lui_meme_ne_coute_rien():
    """L'executeur ne doit rien ajouter au temps de ce qu'il orchestre.

    Mesure avec un executant instantane : ce qui reste est le parcours.
    """
    plan = chaine(*[f"Etape {i}" for i in range(7)])

    debut = time.perf_counter()
    for _ in range(500):
        executer(plan, executant=lambda e: "fait")
    par_plan_us = (time.perf_counter() - debut) / 500 * 1e6

    assert par_plan_us < 2000, f"{par_plan_us:.0f} µs pour parcourir sept etapes"
