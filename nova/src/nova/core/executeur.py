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
#:
#: ⚠️ DEUX FORMES ACCEPTEES, ET CE N'EST PAS DE LA COMPLAISANCE.
#:
#:     executant(etape)           ne regarde pas ce qui precede
#:     executant(etape, acquis)   en tient compte
#:
#: La premiere reste legitime : lire l'heure ne depend d'aucune etape
#: anterieure, et exiger un second parametre inutilise de tous les executants
#: du projet — bancs compris — pour le benefice de quelques-uns aurait ete du
#: bruit. La forme est detectee UNE FOIS, a l'entree de `executer`, jamais a
#: chaque etape.
Executant = Callable[..., Any]


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


#: Combien de caracteres d'acquis on transmet au plus.
#:
#: ⚠️ UN BUDGET, PARCE QUE LA CHAINE EST TRANSITIVE.
#:
#: Une etape voit ce dont elle depend, et ce dont CELA depend. Sur un plan de
#: sept etapes, la derniere voit les six precedentes — et si chacune a rendu
#: un paragraphe, le prompt double avant d'avoir commence. Le meme
#: raisonnement que `extraits_budget` et `faits_budget` : ce qui entre dans un
#: prompt se paie deux fois, en memoire puis en lenteur.
BUDGET_ACQUIS = 2000


@dataclass(frozen=True)
class Acquis:
    """Ce que les etapes precedentes ont REELLEMENT produit.

    ⚠️ LA PIECE QUI MANQUAIT POUR QUE LE PLAN SOIT UNE CHAINE.

    L'executeur parcourait les etapes dans l'ordre, mais chaque executant ne
    recevait que son etape. Un plan de cinq etapes n'etait donc pas une
    chaine : c'etaient cinq demandes independantes posees a la suite.
    « Rechercher les pannes connues » ne savait pas ce que « Observer l'objet »
    avait vu, et « Presenter le diagnostic » redigeait a partir de rien.

    Rien ne le signalait. Chaque etape rendait `faite`, le compte rendu etait
    complet, et le resultat final etait une reponse plausible sans rapport
    avec l'image. C'est exactement la forme de mensonge que l'executeur avait
    ete ecrit pour rendre impossible — et elle passait par le seul endroit
    qu'il ne regardait pas.

    ⚠️ ON N'Y MET QUE DES ETAPES `faite`.

    Une etape `echouee` ou `ignoree` n'a rien produit. La faire figurer avec
    une valeur vide donnerait a l'etape suivante l'impression d'avoir une base
    — et c'est le meme mensonge, deplace d'un cran.
    """

    resultats: tuple[Resultat, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.resultats)

    def valeur(self, numero: int) -> Any:
        """Ce qu'a rendu l'etape numero N, ou `None` si elle n'a rien rendu."""
        for resultat in self.resultats:
            if resultat.numero == numero:
                return resultat.valeur
        return None

    def champ(self, nom: str) -> Any:
        """La derniere valeur portant ce nom parmi les resultats structures.

        Les agents et outils du projet rendent des dictionnaires — la vision
        rend `{"image": …, "chemin": …, "description": …}`. Quand une etape
        suivante attend un `chemin`, il est deja la : le redemander a un
        modele serait redecouvrir par probabilite ce qu'on sait de source
        sure.

        La DERNIERE et non la premiere : sur une chaine, la valeur la plus
        recente est celle qui a ete calculee en connaissance des precedentes.
        """
        trouve = None
        for resultat in self.resultats:
            if isinstance(resultat.valeur, dict) and nom in resultat.valeur:
                trouve = resultat.valeur[nom]
        return trouve

    def texte(self, budget: int = BUDGET_ACQUIS) -> str:
        """Les acquis rendus lisibles, pour un modele ou pour un journal.

        Les etapes RECENTES d'abord quand il faut couper : sur une chaine,
        c'est la derniere qui porte le travail des precedentes.
        """
        if not self.resultats:
            return ""

        blocs: list[str] = []
        reste = budget
        for resultat in reversed(self.resultats):
            # ⚠️ ON TESTE LA VALEUR, PAS LE BLOC.
            #
            # Tester le bloc ne filtrait rien : l'en-tete « [Etape 1 — … ] »
            # n'est jamais vide. Une etape sans resultat produisait donc un
            # en-tete suivi de rien, ce qui laisse croire qu'elle a produit
            # quelque chose d'illisible plutot que rien.
            lisible = _lisible(resultat.valeur).strip()
            if not lisible:
                continue
            bloc = f"[Etape {resultat.numero} — {resultat.intitule}]\n{lisible}"
            if len(bloc) > reste:
                bloc = bloc[: max(reste, 0)]
            blocs.append(bloc)
            reste -= len(bloc)
            if reste <= 0:
                break
        return "\n\n".join(reversed(blocs))


def _lisible(valeur: Any) -> str:
    """Une valeur rendue lisible sans jamais lever.

    ⚠️ CETTE FONCTION EST APPELEE SUR CE QU'UN OUTIL A RENDU.

    Donc sur n'importe quoi : un dictionnaire, un objet, une exception mise en
    valeur par erreur. Elle ne doit pas pouvoir faire tomber une execution qui
    a par ailleurs reussi — sinon un defaut d'affichage detruit un travail
    reel.
    """
    if valeur is None:
        return ""
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, dict):
        return "\n".join(
            f"{cle} : {_lisible(v)}"
            for cle, v in valeur.items()
            if v not in (None, "")
        )
    if isinstance(valeur, (list, tuple)):
        return "\n".join(f"- {_lisible(v)}" for v in valeur)
    try:
        return str(valeur)
    except Exception:  # noqa: BLE001
        return "(valeur illisible)"


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


def socle(plan: Plan, rang: int) -> tuple[int, ...]:
    """Tous les rangs dont cette etape depend, directement ou non.

    ⚠️ TRANSITIF, ET C'EST LE COEUR DE LA DECISION.

    Le plan de diagnostic est une chaine :

        1. Observer l'objet          (vision)
        2. Identifier les composants (extraction)
        3. Rechercher les pannes     (recherche)
        4. Etablir les causes        (raisonnement)
        5. Presenter le diagnostic   (redaction)

    L'etape 5 ne declare qu'une dependance : l'etape 4. S'en tenir aux
    dependances DIRECTES lui donnerait les causes probables et lui cacherait
    l'observation d'origine — celle qui dit ce qu'on regarde. Elle redigerait
    un diagnostic sans savoir de quel objet il s'agit.

    Une etape depend de ce sur quoi son resultat repose. Ce que sa dependance
    a elle-meme consomme en fait partie : perdre l'observation initiale en
    cours de chaine est precisement le defaut qu'on repare.

    Sur un plan en losange — deux branches independantes qui se rejoignent —
    la fermeture ne rend que la branche concernee. C'est la difference avec
    « toutes les etapes precedentes », qui melangerait des travaux sans
    rapport et ferait passer un budget de prompt dans du bruit.
    """
    vus: set[int] = set()
    a_voir = list(plan.etapes[rang].depend_de) if 0 <= rang < len(plan.etapes) else []
    while a_voir:
        besoin = a_voir.pop()
        if besoin in vus or not (0 <= besoin < len(plan.etapes)):
            continue
        vus.add(besoin)
        a_voir.extend(plan.etapes[besoin].depend_de)
    return tuple(sorted(vus))


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
    appeler = _adapter(executant) if executant is not None else None

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
                    resultat = _tenter(etape, appeler, _acquis(plan, rang, par_rang))
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


def _acquis(plan: Plan, rang: int, par_rang: dict[int, Resultat]) -> Acquis:
    """Ce que cette etape a le droit de voir : son socle, et rien d'autre."""
    return Acquis(
        tuple(
            par_rang[besoin]
            for besoin in socle(plan, rang)
            # ⚠️ `accomplie` FILTRE ICI ET NON A L'AFFICHAGE.
            #
            # Une etape echouee dont on transmettrait la ligne donnerait a la
            # suivante l'impression d'avoir une base. En pratique ce cas ne se
            # presente pas — une dependance non aboutie fait deja passer
            # l'etape en `ignoree` avant qu'on arrive ici — mais s'appuyer sur
            # cet enchainement serait s'appuyer sur un ordre, pas sur une
            # regle.
            if besoin in par_rang and par_rang[besoin].accomplie
        )
    )


def _adapter(executant: Executant) -> Callable[[Etape, Acquis], Any]:
    """Ramene un executant a une forme unique, UNE FOIS pour toute l'execution.

    ⚠️ LA DETECTION EST FAITE ICI, PAS A CHAQUE ETAPE.

    `inspect.signature` n'est pas gratuit, et surtout : une forme qui pourrait
    changer d'une etape a l'autre serait un comportement, pas une compatibilite.

    Un executant dont la signature est illisible — un objet appelable exotique,
    un `functools.partial` sur du code natif — est suppose ne PAS vouloir les
    acquis. C'est le repli qui ne casse rien : au pire il ignore un contexte
    qu'il n'aurait peut-etre pas utilise, au lieu de lever un `TypeError` qui
    ferait echouer une etape parfaitement executable.
    """
    import inspect

    def sans_acquis(etape: Etape, _: Acquis) -> Any:
        return executant(etape)

    # ⚠️ LE NOM DOIT SURVIVRE A L'ENVELOPPE.
    #
    # `_tenter` lit `executant.nom` pour dire QUI a fait le travail, et le
    # gestionnaire pose ce nom sur sa fonction. Une enveloppe anonyme aurait
    # rendu « executant : None » sur toutes les etapes — un compte rendu qui
    # perd l'auteur du travail, pour un detail d'adaptation de signature.
    sans_acquis.nom = getattr(executant, "nom", None)  # type: ignore[attr-defined]

    try:
        parametres = list(inspect.signature(executant).parameters.values())
    except (TypeError, ValueError):
        return sans_acquis

    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parametres):
        return executant
    positionnels = [
        p
        for p in parametres
        if p.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return executant if len(positionnels) >= 2 else sans_acquis


def _tenter(etape: Etape, executant: Callable[[Etape, Acquis], Any], acquis: Acquis) -> Resultat:
    """Appelle l'executant et traduit ce qui en sort. Ne leve jamais.

    ⚠️ UN ECHEC EST UN RESULTAT, PAS UNE PANNE.

    Laisser l'exception remonter ferait perdre tout le compte rendu : les
    etapes deja accomplies, celles qui restaient, la raison de l'arret. Une
    execution qui casse en route doit pouvoir se raconter.
    """
    from nova.outils import ConfirmationRequise

    try:
        valeur = executant(etape, acquis)
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
