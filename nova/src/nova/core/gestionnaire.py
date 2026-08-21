"""Le gestionnaire d'agents : qui va faire cette etape, et avec quoi.

LA PIECE QUI MANQUAIT ENTRE DEUX PIECES EXISTANTES

    planificateur  →  QUOI faire        (un plan)
    gestionnaire   →  QUI le fait       (ce module)
    executeur      →  parcourir, rendre compte

L'executeur reclame un `Executant` — une fonction qui prend une etape et rend
une valeur. Les agents, eux, se declarent avec `executer(etape, demande)`. Ces
deux contrats ne se rencontraient nulle part : l'executeur etait donc toujours
appele sans executant, et rendait « aucun executant » pour toutes les etapes.

⚠️ ET AUCUN AGENT N'ETAIT JAMAIS ENREGISTRE.

`Conversationnel` et `Documentaire` existent depuis longtemps, avec leurs
bancs. Personne ne les inscrivait au registre. `choisir_agent` rendait donc
`None` en toutes circonstances, et `/v1/capacites` annoncait sincerement zero
agent — un inventaire exact d'un systeme vide, alors que le code etait la.

Un module qui existe, qui est teste, et que rien n'appelle est plus trompeur
qu'un module absent : la revue du code le compte comme fait.

LA CHAINE DE RECOURS, ET SON DERNIER MAILLON

    1. un AGENT declare capable de cette capacite
    2. sinon un OUTIL de la meme capacite — celui qui s'appelle sans argument
       d'abord, les autres ensuite
    3. sinon RIEN — et on le nomme

Le troisieme maillon est le plus important. Il serait facile d'appeler un
outil au hasard pour eviter un trou dans le compte rendu ; ce serait
exactement le mensonge que l'executeur est fait pour rendre impossible.

CE MODULE NE DEDUIT PAS LES ARGUMENTS LUI-MEME — IL LES DEMANDE

Passer de « Rechercher la matiere » a `chercher_documents(question="…")`
demande un jugement, et parfois un modele : c'est le travail de
`core.arguments`, qui sait aussi REFUSER en nommant le parametre manquant.
Le gestionnaire l'appelle et transmet le resultat ; il ne devine rien.

⚠️ DEDUIRE N'EST PAS AUTORISER.

`core.arguments` produit un dictionnaire. `executer_outil` garde seul le
droit de decider si l'appel a lieu, en consultant le bareme de risque. Avoir
su deduire le chemin d'un fichier ne rend pas sa suppression autorisee.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from nova.core.contrats import Demande, Etape
from nova.logging_setup import get_logger

log = get_logger(__name__)


class SansExecutant(RuntimeError):
    """Personne ne sait faire cette etape, et on prefere le dire."""


def enregistrer_agents_standard(
    repondre: Callable[[str], str], racine: Path | None = None
) -> tuple[str, ...]:
    """Inscrit les agents du projet. Rend leurs noms.

    `repondre` est injecte plutot qu'importe : c'est ce qui permet
    d'enregistrer un agent conversationnel de test sans modele, et ce qui
    laissera l'agent intact le jour ou Ollama disparaitra.

    Idempotent — le registre refuse un doublon, et relancer l'application ne
    doit pas echouer sur un enregistrement deja fait.

    ⚠️ L'AGENT DE VISION EST INSCRIT MEME QUAND LA VISION EST DESACTIVEE.

    C'est l'inverse de ce qui semble prudent, et c'est deliberé. Un agent
    absent produit « aucun agent ni outil pour la capacite vision » — une
    phrase qui decrit le systeme comme incomplet. Un agent present qui leve
    `VisionIndisponible` produit « la vision est desactivee, voici comment
    l'activer ». Le premier se cherche, le second se corrige.

    C'est la lecon des deux agents qu'aucun code n'inscrivait : ce qui existe
    doit etre visible, y compris quand ca ne peut pas encore servir.
    """
    from nova.agents import Conversationnel, Documentaire, registre_agents
    from nova.agents.vision import Vision
    from nova.settings import get_settings

    racine = Path(racine) if racine is not None else get_settings().root / "data"

    inscrits: list[str] = []
    for agent in (Conversationnel(repondre), Documentaire(), Vision(racine)):
        if agent.nom in registre_agents:
            continue
        registre_agents.enregistrer(agent)
        inscrits.append(agent.nom)
    if inscrits:
        log.info("Agents enregistres : %s", ", ".join(inscrits))
    return tuple(inscrits)


def _sans_argument_obligatoire(outil: Any) -> bool:
    """Cet outil peut-il etre appele sans qu'on devine quoi que ce soit ?

    ⚠️ LA QUESTION N'EST PAS RHETORIQUE.

    `lire_l_heure()` s'appelle tel quel ; `lire_fichier(chemin)` non. Appeler
    le second sans argument produirait une erreur — donc une etape `echouee`,
    donc un compte rendu qui accuse l'outil alors que c'est nous qui n'avons
    pas su quoi lui donner. « Je ne sais pas deduire les arguments » est un
    diagnostic ; « TypeError: missing argument » n'en est pas un.
    """
    try:
        signature = inspect.signature(outil.executer)
    except (TypeError, ValueError):  # objet exotique : on s'abstient
        return False
    return not any(
        parametre.default is inspect.Parameter.empty
        and parametre.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        for nom, parametre in signature.parameters.items()
        if nom != "self"
    )


def _accepte_acquis(executer: Callable[..., Any]) -> bool:
    """Cet `executer(etape, demande, …)` accepte-t-il un troisieme argument ?

    Meme detection que du cote de l'executeur, meme repli : une signature
    illisible est supposee ne pas vouloir l'acquis. Ignorer un contexte coute
    moins cher qu'un `TypeError` qui fait echouer une etape executable.
    """
    import inspect

    try:
        parametres = list(inspect.signature(executer).parameters.values())
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parametres):
        return True
    return (
        len(
            [
                p
                for p in parametres
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
        )
        >= 3
    )


def choisir(etape: Etape) -> tuple[str, str] | None:
    """Qui traitera cette etape : `("agent", nom)`, `("outil", nom)`, ou rien.

    Rend un COUPLE plutot qu'un objet : le compte rendu doit pouvoir nommer
    l'executant sans avoir a le garder en memoire, et deux genres differents
    ne s'appellent pas de la meme facon.
    """
    from nova.agents import choisir_agent, registre_agents
    from nova.outils import registre_outils

    # ⚠️ UN EXECUTANT NOMME EST UN CHOIX, PAS UNE SUGGESTION.
    #
    # `choisir_agent` honorait deja `etape.executant`, mais seulement pour les
    # agents : une etape qui nommait un OUTIL se voyait attribuer le premier
    # venu de la meme capacite. Le defaut ne se voyait pas tant qu'une seule
    # brique couvrait chaque capacite — il est apparu des qu'un banc a
    # enregistre un second outil « action » a cote des actions systeme.
    #
    # Nommer sans etre suivi est pire que ne pas pouvoir nommer : l'appelant
    # croit avoir decide.
    if etape.executant:
        if agent := registre_agents.get(etape.executant):
            return ("agent", agent.nom)
        if outil := registre_outils.get(etape.executant):
            return ("outil", outil.nom)

    if agent := choisir_agent(etape):
        return ("agent", agent.nom)

    # ⚠️ CE FILTRE EST DEVENU UN DEPARTAGE, IL N'EXCLUT PLUS.
    #
    # Il ecartait les outils exigeant des arguments, faute de savoir les
    # deduire : mieux valait « aucun executant » qu'un TypeError accusant
    # l'outil. Maintenant que `core.arguments` sait deduire — ou refuser en
    # nommant ce qui manque — les ecarter reviendrait a se priver d'outils
    # utilisables.
    #
    # On prefere toujours celui qu'on peut appeler a coup sur, et on retombe
    # sur les autres. Un echec « je n'ai pas su deduire chemin » vaut mieux
    # qu'une capacite declaree non couverte alors qu'un outil existe.
    candidats = registre_outils.par_capacite(etape.capacite)
    for outil in candidats:
        if _sans_argument_obligatoire(outil):
            return ("outil", outil.nom)
    if candidats:
        return ("outil", candidats[0].nom)

    return None


def executant_pour(
    demande: Demande,
    *,
    confirmees: Iterable[int] = (),
    proposer: Callable[[str], str] | None = None,
) -> Callable[[Etape], Any]:
    """L'executant a passer a `executeur.executer(plan, executant=…)`.

    ⚠️ `confirmees` NE VIENT JAMAIS DU MODELE.

    Ce sont les numeros d'etapes que l'utilisateur a approuves. La regle est
    la meme qu'a tous les etages qui la manipulent — `executer_outil`,
    `executeur.executer` — et elle vaut ici pour la meme raison : un modele
    qui s'autorise lui-meme n'est pas un controle.
    """
    from nova.agents import registre_agents
    from nova.core.arguments import deduire
    from nova.outils import executer_outil, registre_outils

    accordees = set(confirmees)

    def traiter(etape: Etape, acquis: Any = None) -> Any:
        choix = choisir(etape)
        if choix is None:
            # ⚠️ ON LEVE PLUTOT QUE DE RENDRE `None`.
            #
            # L'executeur traite `None` comme « l'executant n'a rien
            # produit » — ce qui est vrai mais imprecis. Une exception porte
            # la raison jusqu'au compte rendu, et « aucun agent ni outil pour
            # la capacite vision » se corrige, alors que « rien produit » se
            # cherche.
            raise SansExecutant(
                f"aucun agent ni outil pour la capacite « {etape.capacite} »"
            )

        genre, nom = choix
        if genre == "agent":
            agent = registre_agents.exiger(nom)
            log.info("Etape %d confiee a l'agent « %s »", etape.numero, nom)
            # ⚠️ L'ACQUIS EST OPTIONNEL POUR LES AGENTS AUSSI.
            #
            # Meme raison que du cote de l'executeur : un agent qui n'en a pas
            # besoin — la vision regarde une image, pas un contexte — ne doit
            # pas etre force de declarer un parametre qu'il ignore. On le
            # passe a ceux qui l'acceptent, et le contrat `Agent` reste
            # satisfait par les deux formes.
            if acquis is not None and _accepte_acquis(agent.executer):
                return agent.executer(etape, demande, acquis)
            return agent.executer(etape, demande)

        outil = registre_outils.exiger(nom)
        # ⚠️ LA DEDUCTION PRECEDE LE CONTROLE, ELLE NE LE REMPLACE PAS.
        #
        # `deduire` produit un dictionnaire ; `executer_outil` garde seul le
        # droit de decider si l'appel a lieu, en consultant le bareme de
        # risque. Avoir su deduire le chemin d'un fichier ne rend pas sa
        # suppression autorisee.
        arguments = deduire(outil, etape, demande, proposer=proposer, acquis=acquis)
        log.info("Etape %d confiee a l'outil « %s »", etape.numero, nom)
        return executer_outil(
            outil.nom, confirme=etape.numero in accordees, **arguments
        )

    traiter.nom = "gestionnaire"  # type: ignore[attr-defined]
    return traiter


def inventaire() -> dict[str, list[str]]:
    """Qui sait faire quoi, capacite par capacite.

    Sert a deux choses, et la seconde est la vraie : afficher ce que Nova
    peut faire, et rendre VISIBLES les capacites que personne ne couvre. Une
    capacite sans executant n'est pas un detail d'implementation — c'est une
    promesse du planificateur que rien ne tiendra.
    """
    from nova.agents import registre_agents
    from nova.core.contrats import CAPACITES_CONNUES
    from nova.outils import registre_outils

    couverture: dict[str, list[str]] = {}
    for capacite in sorted(CAPACITES_CONNUES):
        noms = [a.nom for a in registre_agents.tout() if capacite in a.capacites]
        # Tous les outils de la capacite, y compris ceux qui exigent des
        # arguments : `core.arguments` sait les deduire, ou dire pourquoi il
        # n'a pas su. Les omettre declarerait une capacite non couverte alors
        # qu'un outil existe.
        noms += [o.nom for o in registre_outils.par_capacite(capacite)]
        couverture[capacite] = noms
    return couverture


def capacites_sans_executant() -> tuple[str, ...]:
    """Les capacites que le planificateur peut demander et que personne ne fait.

    Le dire tot evite la decouverte tardive : un plan de sept etapes dont
    deux ne seront jamais executees vaut mieux annonce qu'affiche comme
    complet.
    """
    return tuple(cap for cap, noms in inventaire().items() if not noms)
