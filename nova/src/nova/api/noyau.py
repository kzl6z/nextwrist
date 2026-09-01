"""API du noyau : ce que Nova a compris, avant qu'elle reponde.

POURQUOI CE POINT D'ENTREE EXISTE

L'exigence est la reactivite : pendant un traitement long, Nova doit
IMMEDIATEMENT montrer qu'elle a compris. Or comprendre et repondre n'ont pas
le meme cout :

    planifier + choisir l'espace   ~0 ms   (aucun appel au modele)
    repondre                        secondes

Les separer en deux points d'entree permet a l'interface d'afficher le plan
tout de suite, puis de laisser la reponse arriver. C'est la difference entre
« elle rame » et « elle travaille » — pour un temps total identique.

    POST /v1/plan        -> ce qu'elle compte faire        (immediat)
    GET  /v1/capacites   -> ce dont elle dispose           (immediat)
    POST /v1/messages    -> la reponse                     (le temps qu'il faut)

Aucun de ces points d'entree ne remplace les autres. Le chemin eprouve n'est
pas touche : c'est la condition pour qu'il n'y ait aucune regression.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from nova import orchestrator
from nova.core import plateforme
from nova.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["noyau"])


class DemandeEntrante(BaseModel):
    texte: str


@router.post("/plan")
def plan(entree: DemandeEntrante) -> dict:
    """Ce que Nova compte faire. Retourne en une milliseconde.

    Aucun appel au modele : le planificateur deterministe reconnait les
    familles connues, et tout le reste est une phrase a laquelle on repond.
    C'est ce qui permet a l'interface d'appeler ce point d'entree a CHAQUE
    demande sans rien ralentir.
    """
    plan, espace = orchestrator.analyser(entree.texte)
    return {
        "demande": plan.demande,
        "direct": plan.direct,
        "origine": plan.origine,
        # La NATURE de la demande. Elle etait calculee par le planificateur
        # puis jetee : l'interface devait redeviner a quoi elle avait affaire.
        "type": plan.type,
        # ⚠️ CE DRAPEAU EST UNE PROMESSE FAITE A L'UTILISATEUR.
        #
        # Un plan qui contient un envoi, un achat ou une suppression ne doit
        # pas s'executer sans accord explicite. Le planificateur ne peut pas
        # l'empecher — il ne s'execute pas. Il peut le DIRE, et l'interface
        # peut le montrer avant que quoi que ce soit ne parte.
        "confirmation_requise": plan.demande_confirmation,
        "memoire_utile": plan.memoire_utile,
        "espace": espace,
        "etapes": [
            {
                "numero": etape.numero,
                "intitule": etape.intitule,
                "capacite": etape.capacite,
                "depend_de": list(etape.depend_de),
                "statut": etape.statut,
                "priorite": etape.priorite,
                "resultat_attendu": etape.resultat_attendu,
                "confirmation_requise": etape.confirmation_requise,
            }
            for etape in plan.etapes
        ],
    }


class ExecutionEntrante(BaseModel):
    texte: str
    #: Numeros d'etapes que l'UTILISATEUR a approuvees. Jamais le modele.
    confirmees: list[int] = []
    #: ⚠️ FAUX PAR DEFAUT, ET CE DEFAUT NE CHANGERA PAS.
    #:
    #: Il l'etait d'abord faute de savoir deduire les arguments : executer
    #: pour de vrai revenait a appeler des outils au hasard. `core.arguments`
    #: sait maintenant les deduire — mais un chemin d'execution reelle
    #: s'ouvre sur demande explicite, jamais par defaut.
    executer_vraiment: bool = False


def _publiable(valeur: object) -> object:
    """Ce qu'un outil a rendu, ramene a ce que JSON sait porter.

    ⚠️ UN OUTIL PEUT RENDRE N'IMPORTE QUOI.

    Les outils du projet rendent des dictionnaires et des chaines, mais rien
    ne l'impose et rien ne le verifiera : un outil ajoute demain peut rendre
    un objet, un `Path`, une date. Laisser FastAPI s'en apercevoir au moment
    de serialiser transformerait un travail entierement reussi en erreur 500
    — le compte rendu perdu pour un detail d'encodage.
    """
    import json

    try:
        json.dumps(valeur)
    except (TypeError, ValueError):
        return str(valeur)
    return valeur


def _proposer_des_arguments(consigne: str) -> str:
    """Le troisieme etage de la deduction : le modele, appele en dernier.

    ⚠️ SANS CE BRANCHEMENT, `core.arguments` N'AURAIT QUE DEUX ETAGES EN VRAI.

    Le module accepte un `proposer` injecte pour rester testable sans moteur.
    L'oublier ici laisserait un troisieme etage complet, teste, et jamais
    appele en production — exactement le genre de code que la revue compte
    comme fait alors que rien ne l'exerce. C'est le defaut qui avait laisse
    `Conversationnel` inscrit nulle part.

    `temperature=0` : on ne veut pas de creativite pour remplir un chemin de
    fichier. Le mode JSON n'est pas demande — `lire_arguments` est deja
    tolerant sur la forme, et l'exiger reduirait le choix des modeles.

    ⚠️ ET C'EST ICI QUE LE GESTIONNAIRE D'AGENTS ATTEINT LE MODEL ROUTER.

    C'est le seul endroit de la chaine planificateur → executeur →
    gestionnaire qui ait besoin d'un modele. Il demandait `LLMClient()`
    directement, donc Ollama, donc un seul cerveau possible. Il demande
    maintenant un USAGE, et le routeur choisit.

    « extraction » exige le local : deduire un chemin de fichier travaille sur
    des noms de fichiers personnels, qui n'ont aucune raison de sortir de la
    machine. Ce n'est pas une preference de vitesse — c'est le champ
    `local_exige` de l'usage, et aucune panne ne le contourne.
    """
    from nova.modeles import routage

    return routage.generer(
        "extraction", [{"role": "user", "content": consigne}], temperature=0.0
    )


@router.post("/executer")
def executer_le_plan(entree: ExecutionEntrante) -> dict:
    """Parcourt le plan d'une demande et rend ce qui s'est reellement passe.

    ⚠️ CE POINT D'ENTREE NE MENT JAMAIS SUR CE QUI A ETE FAIT.

    En simulation — le defaut — aucune etape ne peut ressortir « faite » :
    chacune porte « aucun executant pour la capacite … ». C'est un compte
    rendu honnete de l'etat du systeme, pas un echec.

    Une etape aux consequences externes arrete le parcours et remonte dans
    `a_confirmer`. L'interface peut alors demander l'accord, puis rappeler ce
    point d'entree avec les numeros dans `confirmees`.
    """
    from nova.core.contrats import Demande
    from nova.core.executeur import executer, vagues
    from nova.core.gestionnaire import (
        capacites_sans_executant,
        executant_pour,
        inventaire,
    )

    plan, espace = orchestrator.analyser(entree.texte)
    # Le gestionnaire remplace le branchement provisoire par outils : il
    # cherche d'abord un agent, retombe sur un outil appelable sans argument,
    # et nomme le trou quand il n'y a ni l'un ni l'autre.
    executant = (
        executant_pour(
            Demande(texte=entree.texte),
            confirmees=entree.confirmees,
            proposer=_proposer_des_arguments,
        )
        if entree.executer_vraiment
        else None
    )
    execution = executer(plan, executant=executant, confirmees=entree.confirmees)

    return {
        "demande": plan.demande,
        "type": plan.type,
        "espace": espace,
        "simulation": not entree.executer_vraiment,
        "statut": execution.statut,
        "accomplie": execution.accomplie,
        "a_confirmer": list(execution.a_confirmer),
        # Les vagues disent ce qui pourrait demarrer en meme temps. Aujourd'hui
        # une etape par vague ; la structure n'attend que des executants.
        "vagues": [list(v) for v in vagues(plan)],
        # Qui sait faire quoi, et surtout ce que personne ne sait faire : une
        # capacite sans executant est une promesse du planificateur que rien
        # ne tiendra.
        "couverture": inventaire(),
        "sans_executant": list(capacites_sans_executant()),
        "resultats": [
            {
                "numero": r.numero,
                "intitule": r.intitule,
                "statut": r.statut,
                "detail": r.detail,
                "executant": r.executant,
                # ⚠️ CE CHAMP MANQUAIT, ET SON ABSENCE RENDAIT LE RESTE MUET.
                #
                # Le compte rendu disait qu'une etape etait `faite` sans
                # jamais dire CE QU'ELLE AVAIT PRODUIT. Une execution de cinq
                # etapes reussies ne rendait donc rien d'exploitable — la
                # description de l'image, le diagnostic, tout restait dans le
                # processus.
                "valeur": _publiable(r.valeur),
            }
            for r in execution.resultats
        ],
    }


@router.get("/capacites")
def capacites() -> dict:
    """L'inventaire de Nova : outils, agents, espaces, modeles, machine.

    Destine autant a l'interface — griser ce qui n'est pas disponible plutot
    que de l'offrir puis d'echouer — qu'au debogage : une seule requete dit
    ce que le systeme croit savoir faire.
    """
    from nova.agents import registre_agents
    from nova.espaces import registre_espaces
    from nova.outils import registre_outils
    from nova.vision import disponible as vision_disponible

    machine = plateforme.detecter()
    pression = plateforme.pression_memoire()
    return {
        "machine": {
            "systeme": machine.systeme,
            "architecture": machine.architecture,
            "memoire_go": machine.memoire_go,
            "profil": machine.profil,
            "budget_modele_go": machine.budget_modele_go,
            "menager_le_gpu": machine.menager_le_gpu,
        },
        # Mesure d'INSTANT, contrairement au bloc ci-dessus. C'est la premiere
        # chose a regarder quand la machine se fige : une pagination ne se
        # corrige par aucun reglage d'interface.
        "memoire": {
            "swap_utilise_go": pression.swap_utilise_go,
            "swap_total_go": pression.swap_total_go,
            "pagine": pression.pagine,
            "mesurable": pression.disponible,
        },
        "outils": [
            {"nom": o.nom, "description": o.description} for o in registre_outils.tout()
        ],
        "agents": [
            {"nom": a.nom, "description": a.description} for a in registre_agents.tout()
        ],
        "espaces": [
            {"nom": e.nom, "description": e.description} for e in registre_espaces.tout()
        ],
        # ⚠️ QUI SERT CE MODELE, ET S'IL SORT DE LA MACHINE.
        #
        # La liste ne portait que le nom, la vitesse et les capacites. Avec un
        # seul fournisseur, cela suffisait ; des qu'il y en a deux, « quel
        # modele est-ce » n'est plus la question — « qui repond, et est-ce que
        # mes donnees quittent l'ordinateur » l'est.
        "modeles": [
            {
                "nom": m.nom,
                "vitesse": m.vitesse,
                "capacites": sorted(m.capacites),
                "fournisseur": m.fournisseur,
                "distant": m.distant,
            }
            for m in orchestrator.routeur().modeles
        ],
        # Ce que le routeur ferait, usage par usage, sans rien appeler. C'est
        # la reponse a « pourquoi Nova a-t-elle repondu comme ca » — et elle
        # doit etre lisible AVANT la panne, pas reconstituee apres.
        "routage": _routage_par_usage(),
        "vision": vision_disponible(),
    }


def _routage_par_usage() -> dict[str, list[str]]:
    """Le classement des modeles pour chaque usage connu.

    Ne coute aucun appel : c'est le tri d'une liste sur des reglages deja en
    cache. Un usage sans candidat rend une liste vide plutot que de
    disparaitre — « code : rien » est une information, l'absence n'en est pas
    une.
    """
    from nova.core.routeur import USAGES, AucunModele

    catalogue = orchestrator.routeur()
    resultat: dict[str, list[str]] = {}
    for usage in sorted(USAGES):
        try:
            classes = catalogue.classer(usage)
        except AucunModele:
            resultat[usage] = []
            continue
        resultat[usage] = [f"{m.nom}@{m.fournisseur}" for m in classes]
    return resultat
