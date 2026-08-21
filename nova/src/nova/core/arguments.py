"""Deduire les arguments d'un outil a partir d'une etape ecrite en francais.

LA DERNIERE PIECE, ET LA PLUS DANGEREUSE

    « Rechercher la matiere »  →  chercher_documents(question="les trous noirs")
    « Ouvrir Spotify »         →  ouvrir_application(cible="Spotify")

C'est ce qui manquait pour que les outils exigeants deviennent utilisables.
C'est aussi le seul endroit du projet ou un modele de langue decide de ce
qu'on passe a du code qui agit.

⚠️ LA REGLE DU PROJET S'APPLIQUE ICI PLUS QU'AILLEURS

    Un modele de langue PROPOSE. Il n'AUTORISE jamais.

Ce module ne confirme rien, n'execute rien et ne contourne rien. Il produit un
dictionnaire d'arguments ; `executer_outil` conserve seul le droit de decider
si l'appel a lieu, en consultant le bareme de risque. Deduire les arguments
d'une suppression de fichier ne rend pas la suppression autorisee.

QUATRE ETAGES, DU MOINS CHER AU PLUS RISQUE

    1. l'INTENTION deja reconnue   « ouvre Spotify » → cible=Spotify
    2. l'ACQUIS des etapes d'avant  l'etape 1 a rendu chemin=… → chemin
    3. le NOM du parametre          question, requete, texte → la demande
    4. le MODELE                    tout le reste, et seulement lui

Le deuxieme etage est arrive avec la circulation des resultats, et il evite
le pire des gaspillages : redemander a un modele, par probabilite, ce qu'une
etape precedente a etabli de source sure. L'agent de vision rend
`{"chemin": "/…/piece.jpg"}` ; l'etape suivante attend un `chemin`. Le
deviner serait absurde.

Le premier etage n'est pas une optimisation : `voice/intentions.py` fait
exactement ce travail depuis longtemps, de facon deterministe et testee. Le
refaire avec un modele serait remplacer du code sur par du code probable.

L'ordre est aussi une PRECEDENCE : ce qu'un etage sur a etabli, le suivant ne
le corrige pas. Le modele complete ce qui manque, il ne revient pas sur ce
qu'on savait.

⚠️ TOLERANT SUR LA FORME, STRICT SUR LE FOND

Un petit modele entoure son JSON de texte, renomme les cles, invente des
parametres, rend « 3 » la ou on attend un entier. On accepte tout ce qui peut
se rattraper — et on REFUSE tout ce qui ne se verifie pas :

    un parametre inconnu        → rejete, jamais transmis
    un type non convertible     → rejete
    un parametre obligatoire absent → echec nomme, jamais d'appel partiel

Le dernier point est le plus important. Appeler `lire_fichier()` sans chemin
leve une erreur qui accuse l'outil ; refuser d'appeler et dire « je n'ai pas
su deduire `chemin` » designe le vrai probleme.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nova.core.contrats import Demande, Etape
from nova.logging_setup import get_logger

log = get_logger(__name__)


class ArgumentsIntrouvables(RuntimeError):
    """On n'a pas su remplir un parametre obligatoire, et on prefere le dire."""


@dataclass(frozen=True)
class Parametre:
    """Un parametre attendu par un outil, tel que sa signature le declare."""

    nom: str
    annotation: str
    obligatoire: bool


#: Parametres qu'on sait remplir sans modele, parce que leur nom dit ce qu'ils
#: attendent : le texte de la demande.
#:
#: ⚠️ CETTE LISTE EST COURTE A DESSEIN.
#:
#: Elle ne contient que des noms dont le sens ne depend pas de l'outil.
#: `chemin` ou `cible` n'y figurent pas : deviner un chemin de fichier a
#: partir d'une phrase demande un jugement, et se tromper de fichier n'est pas
#: rattrapable de la meme facon que se tromper de recherche.
NOMS_DE_LA_DEMANDE: frozenset[str] = frozenset(
    {"question", "requete", "recherche", "texte", "sujet", "demande"}
)


def parametres(outil: Any) -> tuple[Parametre, ...]:
    """Ce que l'outil attend. Lu dans sa signature, jamais declare a part.

    Une liste de parametres tenue a la main a cote du code finirait par mentir
    le jour ou quelqu'un ajoutera un argument sans y penser.
    """
    try:
        signature = inspect.signature(outil.executer)
    except (TypeError, ValueError):
        return ()

    trouves: list[Parametre] = []
    for nom, parametre in signature.parameters.items():
        if nom == "self" or parametre.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        annotation = parametre.annotation
        trouves.append(
            Parametre(
                nom=nom,
                annotation=annotation if isinstance(annotation, str) else "",
                obligatoire=parametre.default is inspect.Parameter.empty,
            )
        )
    return tuple(trouves)


def _convertir(valeur: Any, annotation: str) -> Any:
    """Ramene la valeur au type annonce. Leve `ValueError` si c'est impossible.

    ⚠️ ON REFUSE PLUTOT QUE D'APPROXIMER.

    Un modele rend volontiers « 3 » pour un entier — c'est rattrapable. Il
    rend aussi « trois », et la seule facon honnete de traiter ce cas est de
    refuser : passer 0, ou ignorer le parametre, produirait un appel qui a
    l'air correct et ne fait pas ce qui etait demande.
    """
    if valeur is None:
        return None
    base = annotation.split("|")[0].strip().lower()

    if base.startswith("int"):
        return int(str(valeur).strip())
    if base.startswith("float"):
        return float(str(valeur).strip())
    if base.startswith("bool"):
        texte = str(valeur).strip().lower()
        if texte in {"true", "vrai", "oui", "1"}:
            return True
        if texte in {"false", "faux", "non", "0"}:
            return False
        raise ValueError(f"« {valeur} » n'est ni vrai ni faux")
    if base.startswith("str") or not base:
        return str(valeur)
    # Type qu'on ne sait pas verifier (datetime, list[dict]…) : on ne le
    # fabrique pas. Mieux vaut un parametre non deduit qu'un objet invente.
    raise ValueError(f"type « {annotation} » non deductible")


def _retenir(propositions: dict[str, Any], attendus: tuple[Parametre, ...]) -> dict[str, Any]:
    """Ne garde que ce qui correspond a un parametre reel et convertible."""
    par_nom = {p.nom: p for p in attendus}
    retenus: dict[str, Any] = {}

    for nom, valeur in propositions.items():
        parametre = par_nom.get(nom)
        if parametre is None:
            # ⚠️ UN PARAMETRE INVENTE N'EST JAMAIS TRANSMIS.
            #
            # Un modele propose volontiers `path` la ou l'outil attend
            # `chemin`. Le transmettre leverait un TypeError qui accuserait
            # l'outil ; l'ignorer laisse le vrai parametre non rempli, ce que
            # la verification des obligatoires attrapera juste apres.
            log.debug("Argument « %s » ignore : ce parametre n'existe pas.", nom)
            continue
        if valeur is None:
            continue
        try:
            retenus[nom] = _convertir(valeur, parametre.annotation)
        except (TypeError, ValueError) as erreur:
            log.debug("Argument « %s » rejete : %s", nom, erreur)

    return retenus


def deduire_sans_modele(
    outil: Any, etape: Etape, demande: Demande, acquis: Any = None
) -> dict[str, Any]:
    """Les trois premiers etages : l'intention, l'acquis, puis le nom.

    Cout nul, resultat reproductible, testable sans moteur. Rend ce qu'il a
    trouve — possiblement rien, ce qui n'est pas un echec a ce stade.
    """
    from nova.voice import intentions

    attendus = parametres(outil)
    propositions: dict[str, Any] = {}

    # 1. L'intention deja reconnue. `voice/intentions.py` extrait la cible
    #    d'une demande depuis longtemps, de facon deterministe et testee.
    intention = intentions.reconnaitre(demande.texte)
    if intention.reconnue:
        if intention.cible:
            propositions["cible"] = intention.cible
        propositions.update(intention.arguments)

    # 2. Ce qu'une etape precedente a produit.
    #
    #    ⚠️ DE SOURCE SURE, DONC AVANT LE MODELE ET AVANT LA DEMANDE.
    #
    #    L'agent de vision rend `{"chemin": "/…/piece.jpg"}` ; l'etape
    #    suivante attend un `chemin`. Le redemander a un modele reviendrait a
    #    redecouvrir par probabilite ce qu'on tient deja.
    if acquis is not None:
        for parametre in attendus:
            if parametre.nom in propositions:
                continue
            if (valeur := acquis.champ(parametre.nom)) is not None:
                propositions[parametre.nom] = valeur

    # 3. Le nom du parametre, quand il dit lui-meme ce qu'il attend.
    for parametre in attendus:
        if parametre.nom in propositions:
            continue
        if parametre.nom in NOMS_DE_LA_DEMANDE:
            propositions[parametre.nom] = demande.texte

    return _retenir(propositions, attendus)


CONSIGNE = """Tu remplis les arguments d'un outil. Tu n'executes rien.

Renvoie UNIQUEMENT un objet JSON dont les cles sont EXACTEMENT les parametres
listes. N'invente aucune cle. Si tu ne sais pas, omets la cle.

Outil    : NOM — DESCRIPTION
Parametres :
PARAMETRES

Etape    : ETAPE
Demande  : DEMANDE
ACQUIS
Exemple de forme attendue : {"chemin": "/Users/x/notes.txt"}
"""


def consigne(outil: Any, etape: Etape, demande: Demande, acquis: Any = None) -> str:
    """La consigne donnee au modele.

    Construite par substitution de marqueurs et jamais par `str.format` : la
    consigne contient des accolades JSON, que `format` prendrait pour des
    champs. Ce piege a deja coute un tour dans `planificateur.py`, ou la
    consigne levait a chaque appel sans que personne le voie — le repli
    produisait un resultat correct.
    """
    lignes = "\n".join(
        f"  - {p.nom} : {p.annotation or 'texte'}"
        f"{' (obligatoire)' if p.obligatoire else ' (facultatif)'}"
        for p in parametres(outil)
    )
    # Ce que les etapes precedentes ont produit. Le modele n'a plus a deviner
    # ce qui est deja etabli — il lui reste a le reconnaitre, ce qui est une
    # tache beaucoup plus sure.
    contexte = acquis.texte() if acquis is not None else ""
    return (
        CONSIGNE.replace("NOM", outil.nom)
        .replace("DESCRIPTION", getattr(outil, "description", ""))
        .replace("PARAMETRES", lignes or "  (aucun)")
        .replace("ETAPE", etape.intitule)
        .replace("DEMANDE", demande.texte)
        .replace("ACQUIS", f"\nDeja etabli :\n{contexte}\n" if contexte else "")
    )


def lire_arguments(brut: str, outil: Any) -> dict[str, Any]:
    """Interprete la proposition du modele. Rend `{}` si elle est inexploitable.

    Tolerant sur la forme — texte autour, balises Markdown, cles en trop — et
    strict sur le fond, comme `planificateur.lire_plan`.
    """
    if not brut:
        return {}
    debut, fin = brut.find("{"), brut.rfind("}")
    if debut < 0 or fin < debut:
        return {}
    try:
        donnees = json.loads(brut[debut : fin + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(donnees, dict):
        return {}
    return _retenir(donnees, parametres(outil))


def deduire(
    outil: Any,
    etape: Etape,
    demande: Demande,
    *,
    proposer: Callable[[str], str] | None = None,
    acquis: Any = None,
) -> dict[str, Any]:
    """Les arguments a passer a l'outil. Leve si un obligatoire manque.

    `proposer(consigne)` est la seule porte vers un modele, et elle est
    INJECTEE — ce module reste donc testable sans moteur, sans reseau et sans
    machine, comme le planificateur.

    ⚠️ LE MODELE N'EST APPELE QUE S'IL RESTE QUELQUE CHOSE A TROUVER.

    Un outil sans parametre obligatoire non rempli n'a besoin de personne. Sur
    « ouvre Spotify », l'intention donne deja la cible : appeler un modele
    ajouterait une seconde d'attente pour reobtenir ce qu'on savait deja.
    """
    attendus = parametres(outil)
    trouves = deduire_sans_modele(outil, etape, demande, acquis)

    manquants = [p for p in attendus if p.obligatoire and p.nom not in trouves]
    if manquants and proposer is not None:
        try:
            propose = lire_arguments(
                proposer(consigne(outil, etape, demande, acquis)), outil
            )
            # ⚠️ LE MODELE COMPLETE, IL NE CORRIGE PAS.
            #
            # `trouves.update(propose)` laissait la proposition ecraser ce que
            # l'intention avait etabli de facon certaine. Sur « ouvre Spotify »
            # avec un profil a trouver, le modele repondait la cible en meme
            # temps que le profil — et ouvrait Terminal. Le premier etage
            # devenait decoratif : on payait son determinisme sans en garder
            # le benefice.
            trouves.update({c: v for c, v in propose.items() if c not in trouves})
        except Exception as erreur:  # noqa: BLE001
            # Un modele indisponible degrade la deduction, jamais le systeme.
            log.warning("Deduction par le modele impossible (%s).", erreur)
        manquants = [p for p in attendus if p.obligatoire and p.nom not in trouves]

    if manquants:
        noms = ", ".join(f"« {p.nom} »" for p in manquants)
        raise ArgumentsIntrouvables(
            f"« {outil.nom} » exige {noms} et je n'ai pas su le deduire "
            f"de « {etape.intitule} »"
        )

    log.info(
        "Arguments deduits pour « %s » : %s",
        outil.nom,
        ", ".join(f"{c}={v!r}" for c, v in trouves.items()) or "aucun",
    )
    return trouves
