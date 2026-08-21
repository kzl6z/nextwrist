"""Le planificateur : ce que Nova compte faire, avant de le faire.

LA PIECE CENTRALE, ET CE QU'ELLE CHANGE

Jusqu'ici Nova recevait une phrase et produisait une reponse. Une seule
etape, invisible, impossible a inspecter. Desormais elle produit d'abord un
PLAN — une donnee — puis l'execute.

    « Prepare-moi un expose sur Donald Trump »

        1. comprendre le sujet          (raisonnement)
        2. rechercher                   (recherche)
        3. construire le plan           (raisonnement)
        4. rediger les diapositives     (redaction)
        5. illustrer                    (vision)
        6. verifier                     (raisonnement)
        7. presenter l'espace de travail (action)

Un plan est une donnee : on peut l'afficher, le journaliser, le faire valider
avant execution, le rejouer a l'identique. Une chaine d'appels enfouie dans
du code ne permet aucune de ces quatre choses.

LE PIEGE QU'ON EVITE

Faire planifier un modele a chaque phrase serait ruineux et absurde : « quelle
heure est-il » n'a pas besoin d'un plan en sept etapes. La regle est donc :

    on planifie quand la demande le merite, jamais par principe.

`Plan.direct` distingue les deux cas, et l'orchestrateur court-circuite tout
le reste dans le cas frequent.

TROIS ORIGINES POSSIBLES, TOUJOURS UN PLAN

    deterministe  motifs reconnus, zero appel, zero milliseconde
    modele        le modele a propose un decoupage
    repli         le modele a echoue ou repondu n'importe quoi

La derniere ligne est la plus importante : **le planificateur ne peut pas
echouer**. Un modele absent, lent ou incoherent degrade la finesse du plan,
jamais la capacite de Nova a repondre. C'est la regle du projet — chaque
capacite est facultative, son absence n'empeche jamais le reste.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable

from nova.core.contrats import CAPACITES_CONNUES, Demande, Etape, Plan
from nova.logging_setup import get_logger

log = get_logger(__name__)

# Au-dela, une demande ne se traite plus en une phrase. En dessous, planifier
# coute plus que ca ne rapporte. Seuil grossier, mais mesurable et modifiable.
LONGUEUR_COMPLEXE = 40

#: Patrons deterministes : une famille de demandes, sa NATURE, ses
#: declencheurs, son plan.
#:
#: Les ecrire ici plutot que de les faire deviner a un modele donne trois
#: choses qu'aucun modele local ne donne : la vitesse, la reproductibilite,
#: et la possibilite de les tester.
#:
#: La nature a ete ajoutee apres coup : le planificateur reconnaissait la
#: famille, s'en servait pour choisir les etapes, puis la jetait. L'appelant
#: qui voulait savoir a quoi il avait affaire devait redeviner ce que le
#: planificateur savait deja.
PATRONS: tuple[tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]], ...] = (
    (
        "presentation",
        "creation",
        ("expose", "presentation", "diapo", "powerpoint", "slide", "soutenance"),
        (
            ("Comprendre le sujet et l'angle attendu", "raisonnement"),
            ("Rechercher la matiere", "recherche"),
            ("Construire le plan", "raisonnement"),
            ("Rediger les diapositives", "redaction"),
            ("Illustrer", "vision"),
            ("Verifier la coherence", "raisonnement"),
            ("Presenter l'espace de travail", "action"),
        ),
    ),
    (
        "developpement",
        "creation",
        ("application", "appli", "site web", "programme", "logiciel", "coder", "developper"),
        (
            ("Clarifier le besoin et les contraintes", "raisonnement"),
            ("Choisir l'architecture", "raisonnement"),
            ("Ecrire le code", "code"),
            ("Verifier et corriger", "code"),
            ("Presenter l'espace de travail", "action"),
        ),
    ),
    (
        "voyage",
        "tache_multi_etapes",
        ("voyage", "partir a", "vol", "hotel", "sejour", "itineraire", "je pars"),
        (
            ("Preciser dates, budget et contraintes", "raisonnement"),
            ("Rechercher les options", "recherche"),
            ("Construire l'itineraire", "raisonnement"),
            ("Presenter l'espace de travail", "action"),
        ),
    ),
    (
        "document",
        "analyse",
        ("resume", "resumer", "pdf", "rapport", "document", "relire", "corriger le texte"),
        (
            ("Lire le document", "extraction"),
            ("En degager la structure", "raisonnement"),
            ("Produire le texte demande", "redaction"),
        ),
    ),
    (
        "recherche",
        "recherche",
        ("cherche", "recherche", "compare", "qui est", "qu'est-ce que", "explique"),
        (
            ("Cerner la question", "raisonnement"),
            ("Rechercher", "recherche"),
            ("Synthetiser", "redaction"),
        ),
    ),
    (
        "analyse_media",
        "analyse",
        ("video", "image", "photo", "camera", "filme", "scanne"),
        (
            ("Analyser le media", "vision"),
            ("En extraire les elements utiles", "extraction"),
            ("Repondre", "redaction"),
        ),
    ),
    (
        "impression_3d",
        "tache_multi_etapes",
        ("impression 3d", "imprimante 3d", "modele 3d", "stl", "piece a imprimer"),
        (
            ("Comprendre la piece voulue", "raisonnement"),
            ("Verifier les contraintes d'impression", "raisonnement"),
            ("Preparer le fichier", "action"),
            ("Lancer l'impression", "action"),
        ),
    ),
    (
        # ⚠️ CETTE FAMILLE COMBLE UNE CONTRADICTION MESUREE.
        #
        # « Nova, analyse cette trottinette et dis-moi pourquoi elle ne
        # fonctionne plus » passait la porte `merite_un_plan` — soixante-
        # seize caracteres — et ne correspondait a aucun patron. Le
        # planificateur declarait donc que la demande meritait un plan, puis
        # rendait une seule etape « Repondre ». Rien ne signalait l'ecart :
        # le plan direct est un resultat parfaitement valide.
        #
        # `analyse_media` ne l'attrapait pas : elle se declenche sur le
        # SUPPORT (video, photo), pas sur l'INTENTION de diagnostiquer.
        "diagnostic",
        "analyse",
        (
            "ne fonctionne plus", "ne marche plus", "en panne", "diagnostic",
            "diagnostique", "pourquoi elle ne", "pourquoi il ne", "repare",
            "reparer", "analyse cette", "analyse ce ", "analyse mon",
        ),
        (
            ("Observer l'objet et son etat", "vision"),
            ("Identifier l'objet et ses composants", "extraction"),
            ("Rechercher les pannes connues", "recherche"),
            ("Etablir les causes probables", "raisonnement"),
            ("Presenter le diagnostic", "redaction"),
        ),
    ),
    (
        "automatisation",
        "automatisation",
        ("automatise", "automatiser", "chaque jour", "chaque semaine", "rappelle-moi", "planifie"),
        (
            ("Comprendre le declencheur et l'action", "raisonnement"),
            ("Verifier la faisabilite avec les outils disponibles", "raisonnement"),
            ("Mettre en place", "action"),
        ),
    ),
)

def _normaliser(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sans_accents.lower()).strip()


# ══════════════════════════════════════════════════════════════════════════
#  LES ACTIONS QUI SORTENT DE LA MACHINE
#
#  ⚠️ LA CAPACITE « action » NE SUFFIT PAS A DECIDER.
#
#  « Presenter l'espace de travail » est une action : elle affiche quelque
#  chose. « Envoyer le message a Paul » aussi. La premiere est annulable d'un
#  clic, la seconde ne l'est pas — un message parti est parti.
#
#  Ce qui les separe n'est pas la capacite mais la CONSEQUENCE : est-ce que
#  quelqu'un d'autre que l'utilisateur voit le resultat, ou est-ce que quelque
#  chose disparait ? On liste donc les verbes de consequence, et on marque
#  toute etape qui en porte un.
#
#  On prefere marquer a tort que laisser passer : une confirmation inutile
#  coute un clic, un achat non voulu coute de l'argent.
CONSEQUENCES_EXTERNES: tuple[str, ...] = (
    "envoy", "envoie", "ecris a", "message a", "mail", "courriel", "sms",
    "appel", "appelle", "telephon",
    "reserv", "achet", "commande", "paie", "payer", "paiement",
    "supprim", "efface", "detruit", "desinstall",
    "publie", "publier", "poste sur", "partage avec",
    # ⚠️ « imprim » NE COUVRE PAS « impression » : le radical change.
    # « Lancer l'impression » n'etait pas marquee, et c'est pourtant l'etape
    # qui met une machine en mouvement. Attrapee par le banc de la famille
    # impression 3d.
    "imprim", "impress",
    "installe",
)


def action_a_confirmer(intitule: str, capacite: str) -> bool:
    """Cette etape modifie-t-elle quelque chose hors de la machine ?

    Deux conditions, et les deux sont necessaires. La capacite « action »
    seule marquerait « presenter l'espace de travail » ; un verbe de
    consequence seul marquerait « comprendre ce qu'il faut envoyer », qui ne
    fait rien du tout.
    """
    if capacite != "action":
        return False
    normalise = _normaliser(intitule)
    return any(verbe in normalise for verbe in CONSEQUENCES_EXTERNES)


CONVERSATION = Plan(demande="", etapes=(Etape("Repondre", "conversation"),))


#: Marques d'une demande qui porte sur l'utilisateur lui-meme.
#:
#: ⚠️ « -moi » ACCROCHE A UN VERBE N'EN EST PAS UNE.
#:
#: « parle-moi de Mars » ne parle pas de toi : le pronom y est le complement
#: du verbe, pas le sujet de la demande. Sans cette exclusion, la moitie des
#: questions de culture generale seraient marquees comme personnelles, et le
#: signal ne signalerait plus rien.
_PERSONNEL = re.compile(
    r"(?<!-)\b(mon|ma|mes|mien|mienne|je|j'|m'appelle|nous|notre|nos)\b|(?<!-)\bmoi\b",
    re.IGNORECASE,
)


def memoire_utile(demande: str) -> bool:
    """La memoire personnelle sert-elle a repondre a ceci ?

    « quel est mon prenom » oui, « qu'est-ce qu'un trou noir » non. Signal
    deterministe, sans appel ni lecture : c'est ce qui permet de le calculer
    a chaque demande sans en payer le prix.
    """
    return bool(_PERSONNEL.search(demande))


def plan_direct(demande: str) -> Plan:
    """Le plan d'une simple reponse. Pas d'orchestration.

    ⚠️ « question_simple » ET « conversation » NE SONT PAS LE MEME PLAN.

    Les deux tiennent en une etape et se repondent pareil, mais l'appelant a
    besoin de les distinguer : « merci » n'appelle ni memoire, ni recherche,
    ni espace de travail, alors qu'une question peut appeler les trois plus
    tard. Un seul type pour les deux forcerait a redeviner lequel c'est.
    """
    texte = demande.strip()
    interrogative = texte.endswith("?") or bool(
        re.match(
            # ⚠️ LA BORNE DE MOT N'EST PAS DECORATIVE : sans elle, « ou »
            # correspond au debut de « oui », et une approbation devenait une
            # question. Le banc des civilites l'a attrape.
            r"^(qu|quel|quelle|quels|quelles|qui|quand|ou|comment|pourquoi"
            r"|combien|est-ce)\b",
            _normaliser(texte),
        )
    )
    return Plan(
        demande=demande,
        etapes=(Etape("Repondre", "conversation", resultat_attendu="Une reponse dite"),),
        type="question_simple" if interrogative else "conversation",
        memoire_utile=memoire_utile(demande),
    )


def planifier_deterministe(demande: Demande) -> Plan:
    """Un plan sans modele : reconnaissance de motifs, cout nul.

    Couvre les familles de demandes qu'on sait nommer. Le reste tombe sur le
    plan direct, ou sera confie au modele.
    """
    texte = _normaliser(demande.texte)

    for famille, nature, declencheurs, etapes in PATRONS:
        if any(d in texte for d in declencheurs):
            construites = tuple(
                Etape(
                    intitule,
                    capacite,
                    depend_de=(i - 1,) if i else (),
                    confirmation_requise=action_a_confirmer(intitule, capacite),
                )
                for i, (intitule, capacite) in enumerate(etapes)
            )
            plan = Plan(
                demande=demande.texte,
                etapes=construites,
                origine="deterministe",
                type=nature,
                memoire_utile=memoire_utile(demande.texte),
            )
            log.info(
                "Plan deterministe « %s » (%s) — %d etapes%s",
                famille,
                nature,
                len(etapes),
                " · confirmation requise" if plan.demande_confirmation else "",
            )
            return plan

    return plan_direct(demande.texte)


def merite_un_plan(demande: Demande) -> bool:
    """Cette demande vaut-elle qu'on fasse reflechir un modele ?

    Deux signaux suffisent et se defendent : une demande longue, ou une
    demande qui tombe dans une famille connue. Tout le reste est une phrase,
    et une phrase se repond.
    """
    if len(demande.texte.strip()) >= LONGUEUR_COMPLEXE:
        return True
    texte = _normaliser(demande.texte)
    return any(d in texte for _, _, declencheurs, _ in PATRONS for d in declencheurs)


def lire_plan(brut: str, demande: str) -> Plan | None:
    """Interprete la proposition du modele. `None` si elle est inexploitable.

    Volontairement tolerante sur la forme — un petit modele entoure son JSON
    de texte, oublie un champ, invente un nom de cle — et stricte sur le
    fond : une capacite inconnue est refusee, parce qu'une etape que personne
    ne sait executer n'est pas une etape.
    """
    if not brut:
        return None

    debut, fin = brut.find("["), brut.rfind("]")
    if debut < 0 or fin < debut:
        debut, fin = brut.find("{"), brut.rfind("}")
        if debut < 0 or fin < debut:
            return None
    try:
        donnees = json.loads(brut[debut : fin + 1])
    except json.JSONDecodeError:
        return None

    if isinstance(donnees, dict):
        # Le modele a enveloppe la liste : on prend la premiere liste trouvee.
        donnees = next((v for v in donnees.values() if isinstance(v, list)), None)
    if not isinstance(donnees, list) or not donnees:
        return None

    etapes: list[Etape] = []
    for rang, brute in enumerate(donnees):
        if isinstance(brute, str):
            intitule, capacite = brute, "raisonnement"
        elif isinstance(brute, dict):
            intitule = str(brute.get("intitule") or brute.get("etape") or brute.get("step") or "")
            capacite = str(brute.get("capacite") or brute.get("capacity") or "raisonnement")
        else:
            continue
        intitule = intitule.strip()
        if not intitule:
            continue
        if capacite not in CAPACITES_CONNUES:
            log.debug("Etape ignoree : capacite inconnue « %s »", capacite)
            capacite = "raisonnement"
        etapes.append(Etape(intitule, capacite, depend_de=(rang - 1,) if rang else ()))

    if not etapes:
        return None
    return Plan(demande=demande, etapes=tuple(etapes), origine="modele")


# La consigne contient du JSON, donc des accolades. `str.format` y voit des
# champs a remplacer et echoue — ou pire, reussit en mangeant une accolade.
# On substitue donc un marqueur explicite, jamais `.format`.
#
# Ce piege a ete attrape par le test du chemin nominal : la consigne levait a
# CHAQUE appel, et le repli du planificateur masquait l'erreur en produisant
# un plan correct. Un systeme qui ne peut pas echouer peut aussi cacher ses
# pannes — d'ou l'importance de tester aussi ce qui doit reussir.
CONSIGNE = """Tu decoupes une demande en etapes, sans y repondre.

Renvoie UNIQUEMENT un tableau JSON. Chaque element a deux champs :
  "intitule"  : l'etape, en une courte phrase a l'infinitif
  "capacite"  : une seule valeur parmi CAPACITES

Trois a sept etapes. Pas de texte autour, pas de balise Markdown.

Demande : « Prepare-moi un expose sur Rome »
[{"intitule": "Comprendre l'angle attendu", "capacite": "raisonnement"},
 {"intitule": "Rechercher la matiere", "capacite": "recherche"},
 {"intitule": "Rediger les diapositives", "capacite": "redaction"}]
"""


def consigne() -> str:
    """La consigne donnee au modele planificateur."""
    return CONSIGNE.replace("CAPACITES", ", ".join(sorted(CAPACITES_CONNUES)))


def planifier(
    demande: Demande,
    proposer: Callable[[str, str], str] | None = None,
) -> Plan:
    """Produit un plan. Ne peut pas echouer.

    `proposer(consigne, demande)` est la seule porte vers un modele, et elle
    est INJECTEE. Le planificateur reste donc testable sans moteur, sans
    reseau et sans machine — et c'est ce qui le rendra encore verifiable
    quand le moteur d'aujourd'hui aura disparu.
    """
    if not merite_un_plan(demande):
        return plan_direct(demande.texte)

    if proposer is not None:
        try:
            propose = lire_plan(proposer(consigne(), demande.texte), demande.texte)
            if propose is not None:
                log.info("Plan du modele — %d etapes", len(propose.etapes))
                return propose
            log.info("Proposition du modele inexploitable : repli deterministe.")
        except Exception as exc:  # noqa: BLE001
            # Un planificateur qui tombe ne doit jamais empecher de repondre.
            log.warning("Planification par le modele impossible (%s) : repli.", exc)

    plan = planifier_deterministe(demande)
    return Plan(demande=plan.demande, etapes=plan.etapes, origine="repli"
                ) if proposer is not None else plan
