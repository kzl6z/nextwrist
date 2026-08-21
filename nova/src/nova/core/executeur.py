"""L'executeur : parcourir un plan sans jamais mentir sur ce qui a ete fait.

CE QU'IL AJOUTE AU PLANIFICATEUR

Le planificateur produit une donnee : ce que Nova COMPTE faire. Cette donnee
ne fait rien. L'executeur la parcourt, demande a chaque etape d'etre
accomplie, et rend un compte rendu — lui aussi une donnee.

    plan  →  executeur  →  execution
             (parcourt)     (ce qui s'est reellement passe)

⚠️ LA REGLE QUI GOUVERNE TOUT CE MODULE

    Une etape non accomplie ne doit JAMAIS ressembler a une etape accomplie.

C'est la contrainte la plus forte du cahier des charges, et c'est aussi la
plus facile a trahir par inadvertance. Un executeur qui rend « voyage
organise » alors qu'aucun billet n'existe ne se trompe pas un peu : il fait
croire a l'utilisateur qu'il peut partir. Toutes les decisions ci-dessous en
decoulent.

    aucun executant disponible   →  `ignoree`, avec la raison
    confirmation attendue        →  `a_confirmer`, l'execution S'ARRETE
    l'executant a leve           →  `echouee`, avec l'erreur
    une dependance a echoue      →  `ignoree`, jamais tentee

Aucun de ces quatre cas ne produit `faite`. Il n'y a qu'une facon d'obtenir
`faite` : qu'un executant ait rendu une valeur.

⚠️ L'EXECUTEUR N'EXECUTE RIEN LUI-MEME

Il ne connait ni les outils, ni les agents, ni les modeles. Il recoit un
`executant` — une fonction — et l'appelle. C'est le meme choix que
`planifier(proposer=…)`, et pour la meme raison : ce module reste testable
sans moteur, sans reseau et sans machine, donc encore verifiable quand les
moteurs d'aujourd'hui auront disparu.

Sans executant, il ne fait rien et le DIT : chaque etape porte « aucun
executant pour la capacite … ». Ni un succes, ni une erreur : un manque,
nomme. C'est le mode par defaut de `/v1/executer`.

`core.gestionnaire.executant_pour(demande)` fournit l'executant reel — agents
d'abord, outils ensuite, rien nomme en dernier recours. L'executeur ne le
connait pas et n'a pas a le connaitre.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from nova.core import chrono
from nova.core.contrats import Etape, Plan
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Ce qu'on demande a un executant : accomplir une etape, rendre une valeur.
#:
#: Il leve `ConfirmationRequise` (de `nova.outils`) si l'accord manque, et
#: n'importe quelle exception s'il echoue. Rien d'autre n'est impose : un
#: outil, un agent, un modele ou un double de test satisfont ce contrat.
Executant = Callable[[Etape], Any]


class Interrompue(RuntimeError):
    """L'execution s'arrete ici et attend quelque chose de l'utilisateur."""


@dataclass(frozen=True)
class Resultat:
    """Ce qu'est devenue UNE etape. Le compte rendu, pas la promesse."""

    numero: int
    intitule: str
    statut: str
    #: Pourquoi ce statut, en francais. Toujours renseigne quand le statut
    #: n'est pas `faite` — un « ignoree » sans raison est indebogable.
    detail: str = ""
    #: Ce que l'executant a rendu. `None` tant que rien n'a ete accompli.
    valeur: Any = None
    #: Qui a fait le travail. `None` = personne.
    executant: str | None = None

    @property
    def accomplie(self) -> bool:
        return self.statut == "faite"


@dataclass(frozen=True)
class Execution:
    """Le compte rendu complet. Une donnee, comme le plan.

    On peut donc l'afficher, la journaliser, la comparer au plan d'origine —
    et surtout la tester sans rien executer.
    """

    plan: Plan
    resultats: tuple[Resultat, ...]
    #: `terminee`, `a_confirmer`, `echouee` ou `incomplete`.
    statut: str
    #: Numeros des etapes qui attendent un accord explicite.
    a_confirmer: tuple[int, ...] = field(default_factory=tuple)

    @property
    def accomplie(self) -> bool:
        """Toutes les etapes ont-elles reellement ete faites ?

        ⚠️ SEUL `faite` COMPTE. Ni `ignoree`, ni `a_confirmer`, ni `echouee`
        ne s'en approchent — c'est ici que se joue la promesse du module.
        """
        return bool(self.resultats) and all(r.accomplie for r in self.resultats)

    def resume(self) -> str:
        """Une ligne qui dit la verite, meme quand elle est decevante."""
        compte: dict[str, int] = {}
        for resultat in self.resultats:
            compte[resultat.statut] = compte.get(resultat.statut, 0) + 1
        detail = ", ".join(f"{n} {statut}" for statut, n in sorted(compte.items()))
        return f"{self.statut} — {detail}" if detail else self.statut


# ══════════════════════════════════════════════════════════════════════════
#  L'ORDRE DE PARCOURS
# ══════════════════════════════════════════════════════════════════════════
def vagues(plan: Plan) -> tuple[tuple[int, ...], ...]:
    """Les etapes groupees par ce qui peut demarrer en meme temps.

    ⚠️ CE DECOUPAGE EXISTE AVANT LA PARALLELISATION, PAS APRES.

    Les plans d'aujourd'hui sont des chaines : chaque etape depend de la
    precedente, donc chaque vague contient une seule etape et l'execution est
    sequentielle. Rien n'y oblige — `depend_de` decrit un graphe. Le jour ou
    un plan proposera deux recherches independantes, elles se retrouveront
    dans la meme vague sans qu'une ligne change ici.

    Ecrire ce parcours maintenant coute vingt lignes. L'ecrire apres coup
    demanderait de retrouver tous les appelants qui supposaient l'ordre
    sequentiel.

    Les etapes prises dans un cycle ne figurent dans aucune vague : elles ne
    peuvent pas commencer, et le declarer vaut mieux que boucler.
    """
    restantes = {rang: set(etape.depend_de) for rang, etape in enumerate(plan.etapes)}
    faites: set[int] = set()
    resultat: list[tuple[int, ...]] = []

    while restantes:
        prete = tuple(
            sorted(rang for rang, besoins in restantes.items() if besoins <= faites)
        )
        if not prete:
            # Cycle, ou dependance vers une etape inexistante. On s'arrete :
            # boucler serait pire, et supposer un ordre serait un mensonge.
            log.warning(
                "Plan non parcourable : %d etape(s) bloquee(s) par leurs dependances.",
                len(restantes),
            )
            break
        resultat.append(prete)
        faites.update(prete)
        for rang in prete:
            del restantes[rang]

    return tuple(resultat)


def bloquees(plan: Plan) -> tuple[int, ...]:
    """Les rangs qu'aucune vague n'atteint : cycle ou dependance absente."""
    atteints = {rang for vague in vagues(plan) for rang in vague}
    return tuple(rang for rang in range(len(plan.etapes)) if rang not in atteints)


# ══════════════════════════════════════════════════════════════════════════
#  LE PARCOURS
# ══════════════════════════════════════════════════════════════════════════
def _sans_executant(etape: Etape) -> Resultat:
    return Resultat(
        numero=etape.numero,
        intitule=etape.intitule,
        statut="ignoree",
        detail=f"aucun executant pour la capacite « {etape.capacite} »",
    )


def executer(
    plan: Plan,
    *,
    executant: Executant | None = None,
    confirmees: Iterable[int] = (),
) -> Execution:
    """Parcourt le plan et rend ce qui s'est reellement passe. Ne leve jamais.

    ⚠️ `confirmees` NE DOIT JAMAIS VENIR DU MODELE.

    Ce sont les numeros d'etapes que l'UTILISATEUR a explicitement approuvees,
    transmis par l'interface. Laisser un modele remplir ce champ reviendrait a
    demander au renard s'il a le droit d'entrer dans le poulailler — c'est la
    formulation deja retenue pour `executer_outil(confirme=…)`, et elle vaut
    ici pour la meme raison.

    ⚠️ L'EXECUTION S'ARRETE A LA PREMIERE ETAPE NON CONFIRMEE.

    Elle ne saute pas l'etape pour continuer : les suivantes en dependent
    presque toujours, et les executer sur une base absente produirait un
    resultat qui a l'air complet. On s'arrete, on dit quoi confirmer, et on
    laisse l'utilisateur decider.
    """
    accordees = set(confirmees)
    resultats: list[Resultat] = []
    par_rang: dict[int, Resultat] = {}
    en_attente: list[int] = []
    arret = False

    with chrono.mesurer("executeur — parcours"):
        for vague in vagues(plan):
            if arret:
                break
            for rang in vague:
                etape = plan.etapes[rang]

                # Une etape dont une dependance n'a pas abouti n'est jamais
                # tentee : la lancer sur une base absente produirait un
                # resultat qui a l'air valide.
                manquantes = [
                    d for d in etape.depend_de if not par_rang[d].accomplie
                ]
                if manquantes:
                    numeros = ", ".join(str(par_rang[d].numero) for d in manquantes)
                    resultat = Resultat(
                        etape.numero,
                        etape.intitule,
                        "ignoree",
                        f"depend de l'etape {numeros}, qui n'a pas abouti",
                    )
                elif etape.confirmation_requise and etape.numero not in accordees:
                    resultat = Resultat(
                        etape.numero,
                        etape.intitule,
                        "a_confirmer",
                        "action aux consequences externes : accord explicite attendu",
                    )
                    en_attente.append(etape.numero)
                    arret = True
                elif executant is None:
                    resultat = _sans_executant(etape)
                else:
                    resultat = _tenter(etape, executant)
                    if resultat.statut == "a_confirmer":
                        en_attente.append(etape.numero)
                        arret = True

                par_rang[rang] = resultat
                resultats.append(resultat)
                if arret:
                    break

    # Les etapes jamais atteintes — arret en cours de route, ou cycle — sont
    # declarees telles quelles. Les omettre laisserait croire qu'un plan de
    # sept etapes n'en comptait que trois.
    for rang, etape in enumerate(plan.etapes):
        if rang in par_rang:
            continue
        raison = (
            "bloquee par ses dependances (cycle ou etape absente)"
            if rang in bloquees(plan)
            else "non atteinte : l'execution s'est arretee avant"
        )
        resultats.append(Resultat(etape.numero, etape.intitule, "ignoree", raison))

    resultats.sort(key=lambda r: r.numero)
    execution = Execution(
        plan=plan,
        resultats=tuple(resultats),
        statut=_statut_global(resultats, bool(en_attente)),
        a_confirmer=tuple(sorted(en_attente)),
    )
    log.info("Execution : %s", execution.resume())
    return execution


def _tenter(etape: Etape, executant: Executant) -> Resultat:
    """Appelle l'executant et traduit ce qui en sort. Ne leve jamais.

    ⚠️ UN ECHEC EST UN RESULTAT, PAS UNE PANNE.

    Laisser l'exception remonter ferait perdre tout le compte rendu : les
    etapes deja accomplies, celles qui restaient, la raison de l'arret. Une
    execution qui casse en route doit pouvoir se raconter.
    """
    from nova.outils import ConfirmationRequise

    try:
        valeur = executant(etape)
    except ConfirmationRequise as attente:
        return Resultat(
            etape.numero,
            etape.intitule,
            "a_confirmer",
            attente.question(),
        )
    except Exception as erreur:  # noqa: BLE001
        log.warning("Etape %d « %s » a echoue : %s", etape.numero, etape.intitule, erreur)
        return Resultat(etape.numero, etape.intitule, "echouee", str(erreur))

    if valeur is None:
        # ⚠️ RIEN RENDU N'EST PAS ACCOMPLI.
        #
        # Un executant qui ne rend rien n'a probablement rien fait — et dans
        # le doute, l'erreur qui coute le moins cher est de le dire.
        return Resultat(
            etape.numero,
            etape.intitule,
            "ignoree",
            "l'executant n'a rien produit",
            executant=getattr(executant, "nom", None),
        )
    return Resultat(
        etape.numero,
        etape.intitule,
        "faite",
        valeur=valeur,
        executant=getattr(executant, "nom", None),
    )


def _statut_global(resultats: Iterable[Resultat], attend: bool) -> str:
    """Le statut de l'ensemble. L'ordre des tests n'est pas indifferent.

    On annonce d'abord ce qui demande une decision de l'utilisateur, puis ce
    qui a casse, puis ce qui manque. Un plan a la fois interrompu et
    partiellement echoue doit se presenter comme interrompu : c'est l'action
    attendue de l'utilisateur qui prime sur le constat.
    """
    liste = list(resultats)
    if attend:
        return "a_confirmer"
    if any(r.statut == "echouee" for r in liste):
        return "echouee"
    if liste and all(r.accomplie for r in liste):
        return "terminee"
    return "incomplete"
