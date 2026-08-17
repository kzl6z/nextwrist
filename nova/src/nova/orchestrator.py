"""Le coeur de Nova : assembler le contexte, puis interroger le modele.

C'est le seul module autorise a connaitre tous les autres. Tout le reste
respecte la regle de dependance :

    api -> orchestrator -> memory / documents / llm -> db

Ce que fait l'orchestrateur, dans l'ordre :
  1. charge l'identite de Nova (config/prompts/identity.md)
  2. y ajoute les faits confirmes te concernant     <- la memoire
  3. cherche des extraits pertinents                <- les documents
  4. assemble le message systeme
  5. appelle le modele en flux
  6. journalise l'echange

Choix de conception V1 : c'est NOTRE code qui decide de chercher, pas le modele.
C'est deterministe, debogable et previsible. L'appel d'outils par le modele
(MCP) s'ajoutera en V0.3 par-dessus cette base, sans la remplacer.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from nova import prompts
from nova.core import plateforme
from nova.core.contrats import Demande, Modele, Plan
from nova.core.planificateur import planifier
from nova.core.routeur import Routeur
from nova.documents import search as document_search
from nova.llm.client import LLMClient, Message
from nova.logging_setup import get_logger
from nova.memory import conversations, facts
from nova.memory.models import SearchHit
from nova.settings import get_settings, get_tuning
from nova.voice import vocabulaire

if TYPE_CHECKING:
    # Importes UNIQUEMENT pour les annotations. A l'execution, ces modules
    # sont charges tard, dans les fonctions qui s'en servent : la couche voix
    # est facultative, et Nova doit demarrer sans elle.
    from nova.voice import comprehension as voice_comprehension
    from nova.voice import lexique as voice_lexique

log = get_logger(__name__)

# En dessous, la question ne porte pas assez d'information pour qu'une recherche
# documentaire soit utile ("ok", "merci", "et ensuite ?").
MIN_QUERY_LENGTH = 12

# Noms francais ecrits en dur plutot que via la locale du systeme : `strftime`
# renvoie « Saturday » sur une machine configuree en anglais, et Nova annoncerait
# la date en anglais sans que personne ne comprenne pourquoi.
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)


# ══════════════════════════════════════════════════════════════════════════
#  LE NOYAU, VU DEPUIS L'ORCHESTRATEUR
#
#  `core` ne connait ni la base, ni le moteur, ni l'interface : il ne
#  manipule que des descriptions et des decisions. C'est l'orchestrateur qui
#  lui fournit la matiere et qui execute ce qu'il decide. La fleche ne
#  remonte jamais.
#
#  L'integration est volontairement OBSERVABLE avant d'etre agissante : le
#  plan est calcule et journalise, la reponse continue de passer par le
#  chemin eprouve. Brancher l'execution des agents le meme jour aurait mis en
#  jeu tout ce qui fonctionne pour une capacite que rien n'attend encore.
# ══════════════════════════════════════════════════════════════════════════


def routeur() -> Routeur:
    """Le catalogue des modeles, tel que la configuration le decrit.

    Les capacites et la vitesse viennent de `.env`, donc de la MESURE faite
    par `scripts/bench_models.py`, jamais d'une reputation. Un seul modele est
    declare aujourd'hui : c'est celui qui tourne. Le jour ou il y en aura
    trois, le routeur choisira sans qu'aucun appelant ne change.
    """
    reglages = get_settings()
    machine = plateforme.detecter()
    return Routeur(
        (
            Modele(
                nom=reglages.chat_model,
                capacites=frozenset({"conversation", "raisonnement", "extraction", "redaction"}),
                vitesse=reglages.vitesse_mesuree,
                # Une estimation prudente vaut mieux qu'une valeur absente :
                # elle sert a departager, pas a decider seule.
                poids=min(machine.budget_modele_go, 2.0),
            ),
        )
    )


def analyser(texte: str) -> tuple[Plan, str | None]:
    """Le plan de Nova et l'espace de travail concerne, sans rien executer.

    Ne fait AUCUN appel au modele : le planificateur deterministe suffit pour
    les familles connues, et le reste est une phrase a laquelle on repond.
    C'est ce qui permet d'appeler cette fonction a chaque demande sans en
    payer le prix.
    """
    from nova.espaces import choisir_espace  # tard : evite un cycle a l'import

    demande = Demande(texte=texte)
    plan = planifier(demande)
    espace = choisir_espace(demande)
    nom_espace = espace.nom if espace else None

    if not plan.direct:
        log.info(
            "Plan (%s) — %d etapes%s : %s",
            plan.origine,
            len(plan.etapes),
            f", espace « {nom_espace} »" if nom_espace else "",
            " → ".join(e.intitule for e in plan.etapes),
        )
    return plan, nom_espace


#: Duree de vie du vocabulaire deduit de la memoire, en secondes.
#:
#: POURQUOI UN CACHE, ET POURQUOI COURT
#:
#: Chaque phrase dictee declenchait DEUX lectures de la memoire — une pour
#: l'amorce de transcription, une pour le lexique de correction — avant meme
#: que Whisper ne commence. Sur une base distante ou indisponible, c'est du
#: temps d'attente pur, paye a chaque mot prononce.
#:
#: Les faits confirmes changent quelques fois par jour ; le vocabulaire qu'on
#: en tire, encore moins. Une minute de cache supprime la quasi-totalite de ces
#: lectures et retarde d'au plus une minute la prise en compte d'un nom
#: nouveau — un delai qu'aucun usage ne remarque. `oublier_le_vocabulaire()`
#: est la pour les cas ou on ne veut pas attendre du tout.
DUREE_CACHE_VOCABULAIRE = 60.0

#: (instant de calcul, termes). Volontairement un simple tuple protege par un
#: verrou plutot qu'un `lru_cache` : il faut pouvoir l'invalider a la demande.
_vocabulaire_cache: tuple[float, tuple[str, ...]] | None = None
_verrou_vocabulaire = threading.Lock()

#: Empeche dix requetes simultanees de lancer dix relectures de la base.
_rafraichissement_en_cours = False
_verrou_demande = threading.Lock()


def rafraichir_le_vocabulaire() -> tuple[str, ...]:
    """Relit la memoire MAINTENANT, en bloquant. Ne leve jamais.

    Appele par le fil d'entretien, jamais depuis une requete : c'est ici que
    l'attente est acceptable, parce que personne ne la subit.
    """
    global _vocabulaire_cache

    with _verrou_vocabulaire:
        try:
            contenus = [f.content for f in facts.list_facts(status="confirmed")]
            termes = tuple(vocabulaire.extraire_termes(contenus))
        except Exception as exc:  # noqa: BLE001
            # Memoire indisponible : vocabulaire vide, donc une transcription
            # moins fine sur les noms propres. Jamais une panne.
            log.warning("Vocabulaire de la memoire indisponible : %s", exc)
            termes = ()
        _vocabulaire_cache = (time.monotonic(), termes)
        return termes


def _termes_de_la_memoire() -> tuple[str, ...]:
    """Le vocabulaire connu, SANS JAMAIS ATTENDRE.

    ⚠️ CETTE FONCTION EST DANS LE CHEMIN VOCAL. ELLE NE DOIT RIEN BLOQUER.

    Elle lisait la base directement. Tant que la base repond en dix
    millisecondes, personne ne le voit. Le jour ou elle tarde — reveil de
    veille, disque occupe, service arrete — c'est la PAROLE de Nova qui
    attend. Mesure avec une base injoignable : 30 secondes avant la premiere
    transcription, pour un enrichissement facultatif.

    Un travail previsible doit se faire pendant que personne ne regarde. On
    rend donc ce qu'on a, et on demande une relecture EN FOND si c'est vieux.
    Le pire cas devient « Nova entend un peu moins bien les noms propres
    pendant une minute », au lieu de « Nova ne repond pas ».
    """
    cache = _vocabulaire_cache
    if cache is None:
        # Rien encore : on demande une lecture de fond et on repond tout de
        # suite. La toute premiere phrase perd les noms propres ; le
        # prechauffage au demarrage fait que ce cas n'arrive quasiment jamais.
        _demander_un_rafraichissement()
        return ()

    if time.monotonic() - cache[0] >= DUREE_CACHE_VOCABULAIRE:
        _demander_un_rafraichissement()
    return cache[1]


def _demander_un_rafraichissement() -> None:
    """Lance une relecture en fond, sauf s'il y en a deja une."""
    global _rafraichissement_en_cours

    with _verrou_demande:
        if _rafraichissement_en_cours:
            return
        _rafraichissement_en_cours = True

    def travailler() -> None:
        global _rafraichissement_en_cours
        try:
            rafraichir_le_vocabulaire()
        finally:
            with _verrou_demande:
                _rafraichissement_en_cours = False

    threading.Thread(target=travailler, name="nova-vocabulaire", daemon=True).start()


def oublier_le_vocabulaire() -> None:
    """Le vocabulaire a change : on le relit, en fond, tout de suite.

    A appeler quand un fait vient d'etre confirme. La relecture est lancee
    immediatement plutot qu'a la prochaine phrase : entre le moment ou tu
    confirmes un fait et celui ou tu prononces le nom qu'il contient, il
    s'ecoule des secondes — largement de quoi la terminer sans que personne
    n'attende.
    """
    global _vocabulaire_cache
    _vocabulaire_cache = None
    _demander_un_rafraichissement()


def lexique_personnel() -> voice_lexique.Lexique:
    """Le vocabulaire personnel de Nova, assemble depuis ses trois sources.

    C'EST ICI PAR RESPECT DE LA REGLE DE DEPENDANCE

    `voice/lexique.py` sait indexer et comparer des mots ; il ne sait pas d'ou
    ils viennent, et c'est ce qui le rend testable en trois lignes. Aller les
    chercher dans les reglages puis dans la memoire est le travail de
    l'orchestrateur, seul module autorise a connaitre les autres.

    Trois sources, par ordre de confiance decroissante :

        declare   NOVA_WHISPER_VOCABULAIRE, ecrit a la main
        memoire   noms propres des faits confirmes
        appris    corrections que tu as confirmees (a venir)

    L'ordre compte : un terme declare a la main l'emporte sur un terme deduit,
    a ressemblance phonetique egale.
    """
    from nova.voice import lexique as voice_lexique

    lex = voice_lexique.Lexique()
    reglages = get_settings()

    if declares := reglages.whisper_vocabulaire.strip():
        lex.ajouter_tous([t.strip() for t in declares.split(",") if t.strip()], "declare")

    lex.ajouter_tous(list(_termes_de_la_memoire()), "memoire")
    return lex


def comprendre_la_parole(transcription) -> voice_comprehension.Comprehension:
    """Transforme une transcription brute en demande sure — ou en question.

    Assemble le pipeline complet : nettoyage, correction lexicale, intention,
    puis la decision d'agir, de demander confirmation, ou de faire repeter.

    Ne leve jamais : une comprehension qui echoue rendrait Nova muette, alors
    qu'une comprehension degradee la rend seulement moins fine.
    """
    from nova.voice import comprehension as voice_comprehension

    texte = getattr(transcription, "texte", transcription) or ""
    logprob = getattr(transcription, "logprob", None)

    try:
        comprise = voice_comprehension.comprendre(
            texte, lexique=lexique_personnel(), logprob=logprob
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Comprehension indisponible, texte brut conserve : %s", exc)
        from nova.voice.intentions import AUCUNE

        return voice_comprehension.Comprehension(
            texte=texte, origine=texte, confiance=1.0, intention=AUCUNE,
        )

    niveau = "sûre" if comprise.sure else ("à confirmer" if comprise.a_confirmer else "incomprise")
    log.info(
        "Parole %s (%.2f) : « %s »%s",
        niveau,
        comprise.confiance,
        comprise.texte,
        f" — {' · '.join(comprise.raisons)}" if comprise.raisons else "",
    )
    return comprise


def amorce_dictee() -> str:
    """L'amorce de transcription, enrichie des noms propres que Nova connait.

    C'EST ICI ET PAS DANS `voice/` PAR RESPECT DE LA REGLE DE DEPENDANCE

    `voice/vocabulaire.py` ne connait rien du projet : il transforme des
    phrases en termes. Aller chercher ces phrases dans la memoire est le
    travail de l'orchestrateur, seul module autorise a connaitre les autres.
    Sans ca, la couche voix dependrait de la couche memoire et la fleche
    remonterait.

    POURQUOI CA MARCHE

    Whisper se trompe sur ce qui est rare dans la langue — les noms propres.
    Releve en conditions reelles : « pinata » entendu « pierre pienita ».
    Une amorce contenant le mot le fait reconnaitre ; le meme mot absent est
    massacre, quelle que soit la taille du modele.

    Or les noms que l'utilisateur prononce sont exactement ceux que Nova a
    deja en memoire. Plus elle te connait, mieux elle t'entend.
    """
    reglages = get_settings()
    base = reglages.whisper_amorce_dictee

    termes: list[str] = []
    # Le vocabulaire declare a la main passe en premier : c'est un choix
    # explicite de l'utilisateur, il ne doit pas etre evince par la memoire.
    if declares := reglages.whisper_vocabulaire.strip():
        termes.extend(t.strip() for t in declares.split(",") if t.strip())

    # Meme source, meme cache que le lexique de correction : les deux etages
    # de la chaine vocale lisent desormais la memoire une fois pour deux.
    termes.extend(_termes_de_la_memoire())

    return vocabulaire.construire_amorce(base, termes)


def instant_present(maintenant: datetime | None = None) -> str:
    """Date et heure, en francais, pour le prompt systeme."""
    maintenant = maintenant or datetime.now().astimezone()
    return (
        f"{JOURS[maintenant.weekday()]} {maintenant.day} "
        f"{MOIS[maintenant.month - 1]} {maintenant.year}, il est "
        f"{maintenant.strftime('%H:%M')}"
    )


def _format_sources(hits: list[SearchHit], budget: int | None = None) -> str:
    """Met les extraits en forme pour le prompt, dans un budget de caracteres.

    Chaque extrait est explicitement etiquete par sa source afin que le modele
    puisse citer. Sans cette etiquette, il invente les references — c'est
    systematique.

    POURQUOI UN BUDGET, ET PAS SEULEMENT UN NOMBRE D'EXTRAITS

    Exactement la meme raison que pour la memoire (R13), et le meme defaut
    trouve au meme endroit : borner le NOMBRE ne borne pas la TAILLE, et le
    temps de lecture d'un modele local est proportionnel a la taille.

    Mesure en conditions reelles, pour « Dis bonjour en une phrase » :

        identite 1495 + memoire 260 + instant 183 + documents 4825
        -> prompt 6805 car. -> premier mot 10,4 s

    Les documents pesaient 71 % du prompt, sur une demande qui n'en appelait
    aucun. Les extraits arrivent deja classes par pertinence : couper par la
    fin sacrifie donc les moins utiles.
    """
    budget = get_tuning().extraits_budget if budget is None else budget
    blocks: list[str] = []
    total = 0
    for hit in hits:
        label = hit.heading or "sans titre"
        bloc = f'--- [{hit.document_title}, "{label}"]\n{hit.content}'
        if total + len(bloc) > budget:
            # On saute plutot que d'arreter : un extrait anormalement long ne
            # doit pas faire taire les suivants, qui tiendraient tres bien.
            continue
        blocks.append(bloc)
        total += len(bloc)

    if len(blocks) < len(hits):
        log.info(
            "Documents : %d extraits sur %d injectes (budget %d caracteres). "
            "Au-dela, chaque caractere ajoute ~1,5 ms d'attente a CHAQUE question.",
            len(blocks), len(hits), budget,
        )
    return "\n\n".join(blocks)


def build_system_prompt(
    user_message: str, *, mode: str = "normal", contrat: str | None = None
) -> tuple[str, list[SearchHit]]:
    """Construit le message systeme complet. Retourne aussi les sources utilisees.

    Renvoyer les sources permet de les journaliser et, plus tard, de les
    afficher dans l'interface : une reponse verifiable est une reponse a
    laquelle on peut faire confiance.
    """
    # `contrat` : consigne imposee par une application cliente (format de sortie,
    # role attendu). On la RESPECTE au lieu de la remplacer.
    #
    # Nuance importante, apprise en branchant une vraie application : pour une
    # interface de conversation, ignorer le prompt du client est le bon choix —
    # l'identite de Nova ne se delegue pas. Mais un client STRUCTURE attend un
    # format precis ; ecraser sa consigne casse l'application sans un mot.
    # On distingue donc les deux cas, et dans les deux la memoire est injectee.
    # ── ORDRE DES MORCEAUX : DU PLUS STABLE AU PLUS VOLATIL ───────────────
    #
    # Ce n'est pas une question de lisibilite, c'est une question de temps.
    # Le moteur d'inference garde en cache le travail deja fait sur un debut
    # de prompt identique. Ce cache vaut jusqu'au PREMIER caractere qui
    # change : tout ce qui suit est relu de zero.
    #
    # L'instant present contient les minutes. Place en deuxieme position,
    # comme il l'etait, il invalidait donc la memoire et les documents a
    # chaque nouvelle minute — c'est-a-dire presque toujours. Relegue a la
    # fin, il ne coute plus que lui-meme.
    #
    # Mesure qui motive tout ce bloc, sur l'iMac M1 :
    #     prompt 6573 car.  ->  21,4 s avant le premier mot
    # Le modele n'etait pas lent : il relisait tout, a chaque question.
    parts: list[tuple[str, str]] = []

    def ajouter(nom: str, contenu: str) -> None:
        if contenu:
            parts.append((nom, contenu))

    # 1. Stable — ne change jamais d'une question a l'autre.
    ajouter("contrat" if contrat else "identite",
            contrat or prompts.load("identity"))
    if mode == "critique" and not contrat:
        ajouter("mode critique", prompts.load("mode_critique"))
    if not get_settings().thinking:
        # Interrupteur documente de Qwen 3. Inoffensif pour les modeles qui ne
        # le connaissent pas : ce n'est qu'une ligne de texte de plus.
        #
        # ⚠️ IL ETAIT CONDITIONNE A `not contrat`, ET C'ETAIT L'INVERSE DE CE
        # QU'IL FALLAIT.
        #
        # L'application de bureau envoie TOUJOURS son contrat (le JSON a une
        # clef `response`). Le seul chemin qui n'en envoie pas est la CLI. Le
        # coupe-monologue etait donc actif exactement la ou personne ne parle a
        # Nova, et desactive sur le chemin vocal — celui ou quelqu'un attend en
        # silence devant une sphere qui tourne.
        #
        # Ca ne se voyait pas tant que le modele n'etait pas un raisonneur.
        # Avec une base Qwen 3.x, ca se compte en dizaines de secondes de
        # silence avant le premier mot. `ThinkFilter` cache le monologue, il ne
        # le rembourse pas : « Ce filtre ne rend pas le modele plus rapide : le
        # temps est deja depense » (llm/client.py).
        #
        # Un contrat decrit la FORME de la reponse. `/no_think` decide s'il y a
        # un monologue AVANT. Les deux ne parlent pas de la meme chose et n'ont
        # aucune raison de s'exclure. Qui veut le raisonnement met
        # NOVA_THINKING=true — c'est le champ prevu pour, et il vaut maintenant
        # pour les deux chemins.
        #
        # ⚠️ CETTE LIGNE N'EST PLUS L'INTERRUPTEUR. ELLE NE L'A JAMAIS ETE
        # POUR LE MODELE DU PROJET.
        #
        # `/no_think` appartient a Qwen 3. Sur la base Qwen 3.5 de `nova`, il
        # est ignore — verifie sur la machine : le modele raisonnait alors que
        # `/no_think` etait le message systeme ENTIER. Le vrai interrupteur est
        # `reasoning_effort: "none"`, envoye dans la requete par
        # `llm/client.py`, sous la meme condition `NOVA_THINKING`.
        #
        # On garde la ligne : elle coute neuf caracteres et reste le seul
        # levier pour un Qwen 3 servi par un Ollama trop ancien pour connaitre
        # `reasoning_effort`. Mais elle ne garantit rien, et c'est ecrit ici
        # pour que personne ne la croie sur parole une deuxieme fois.
        ajouter("no_think", "/no_think")

    # 2. Lent — ne bouge que quand la memoire evolue.
    ajouter("memoire", facts.render_for_prompt())

    # 3. Volatil — change a chaque minute, puis a chaque question.
    #
    # Un modele n'a AUCUNE notion du temps : sans cette ligne, « quelle heure
    # est-il » recoit une heure inventee, avec aplomb. C'est la premiere
    # question que tout le monde pose a un assistant vocal, et le premier
    # endroit ou il perd la confiance de son utilisateur.
    ajouter(
        "instant present",
        f"## Instant present\nNous sommes {instant_present()}.\n"
        "Utilise cette information telle quelle pour toute question de date ou "
        "d'heure. Ne la recalcule pas, ne l'estime pas.",
    )

    hits: list[SearchHit] = []
    ms_recherche = 0.0
    if len(user_message.strip()) >= MIN_QUERY_LENGTH:
        debut_recherche = time.perf_counter()
        try:
            hits = document_search.search(user_message)
        except Exception as exc:  # noqa: BLE001
            # Une recherche en echec ne doit JAMAIS empecher Nova de repondre.
            # Chaque capacite est facultative : c'est ce qui rend le systeme
            # robuste quand on en ajoutera dix autres.
            log.warning("Recherche documentaire indisponible : %s", exc)
        ms_recherche = (time.perf_counter() - debut_recherche) * 1000

    if hits:
        ajouter(
            "documents",
            "## Extraits de tes documents\n\n"
            "Appuie-toi dessus en priorite et cite la source entre crochets. "
            "S'ils ne repondent pas a la question, dis-le explicitement.\n\n"
            + _format_sources(hits),
        )

    # De quoi voir, en un coup d'oeil, quel morceau coute cher. Sans ce
    # detail, « le prompt fait 6573 caracteres » ne dit pas quoi couper.
    log.info(
        "Prompt systeme : %s",
        " + ".join(f"{nom} {len(contenu)}" for nom, contenu in parts),
    )
    # ── LE TEMPS PASSE AVANT MEME D'APPELER LE MODELE ────────────────────
    #
    # Ce chiffre manquait, et son absence a coute un tour entier. Le filtre
    # de pertinence a divise le prompt par deux (3376 -> 1812) sans changer
    # le temps avant le premier mot (5,1 -> 5,2 s) : la taille du prompt
    # n'etait donc pas le goulot. Il fallait chercher AILLEURS, et rien ne
    # disait ou.
    #
    # La recherche documentaire embarque un appel a bge-m3 pour vectoriser
    # la question — un second modele, de 1,2 Go, sur une machine de 8 Go. Ce
    # cout-la est paye meme quand AUCUN extrait n'est retenu.
    if ms_recherche >= 50:
        log.info(
            "Assemblage du prompt : recherche documentaire %.0f ms "
            "(vectorisation de la question comprise)%s",
            ms_recherche,
            "" if hits else " — pour zero extrait retenu",
        )
    return "\n\n".join(contenu for _, contenu in parts), hits


def answer_stream(
    messages: list[Message],
    *,
    conversation_external_id: str | None = None,
    mode: str = "normal",
    contrat: str | None = None,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Produit la reponse morceau par morceau, et journalise l'echange.

    `messages` est l'historique fourni par l'interface (format OpenAI). On
    remplace tout message systeme qu'elle aurait ajoute par le notre : l'identite
    de Nova ne doit pas dependre de l'interface.
    """
    user_messages = [m for m in messages if m.get("role") == "user"]
    last_user = user_messages[-1]["content"] if user_messages else ""

    system_prompt, hits = build_system_prompt(last_user, mode=mode, contrat=contrat)
    history = [m for m in messages if m.get("role") != "system"]

    conversation_id = conversations.get_or_create(conversation_external_id)

    # ── LE CONTEXTE CONVERSATIONNEL ──────────────────────────────────────
    #
    # Les echanges partaient en base et n'en revenaient jamais : ce module
    # savait ecrire, pas relire. Nova avait donc une memoire parfaite de ce
    # qui s'etait dit, et aucun moyen de s'en servir.
    #
    #     — « Parle-moi de Mars. »        Nova repond.
    #     — « Et on pourrait y vivre ? »  « y » ne renvoie a rien.
    #
    # On relit ICI, avant de journaliser la question en cours — sinon elle
    # figurerait deux fois dans le prompt, une fois comme passe et une fois
    # comme present.
    #
    # LA GARDE : un client qui envoie DEJA son historique fait foi.
    #
    # L'application de bureau n'envoie qu'un message ; un autre client
    # pourrait envoyer toute la conversation. Injecter le notre par-dessus le
    # sien donnerait deux versions du meme passe, dans le desordre — et le
    # modele n'aurait aucun moyen de trancher.
    passe: list[Message] = []
    if len(history) <= 1:
        try:
            passe = conversations.derniers_echanges(
                conversation_id, budget_caracteres=get_tuning().historique_budget
            )
        except Exception as exc:  # noqa: BLE001
            # Un contexte indisponible degrade la conversation ; il ne doit
            # jamais empecher de repondre. Chaque capacite est facultative.
            log.warning("Historique de conversation indisponible : %s", exc)

    full: list[Message] = [{"role": "system", "content": system_prompt}, *passe, *history]
    if passe:
        log.info(
            "Contexte : %d message(s) precedent(s) rappeles (%d caracteres).",
            len(passe),
            sum(len(m["content"]) for m in passe),
        )

    conversations.log_message(conversation_id, "user", last_user)

    client = LLMClient()
    collected: list[str] = []
    completed = False

    # ── Ou passent les secondes ? ────────────────────────────────────────
    #
    # « C'est lent » n'est pas un diagnostic : un modele local peut etre lent
    # a lire la question (prefill) ou lent a ecrire la reponse (generation), et
    # les deux se corrigent a l'oppose l'un de l'autre. Raccourcir le prompt
    # d'un cote, reduire le plafond de jetons de l'autre.
    #
    # On separe donc les deux, en clair, a chaque appel. Sans cette ligne on
    # optimise a l'aveugle — ce qui a deja coute deux tours ici.
    taille_prompt = sum(len(m.get("content", "")) for m in full)
    depart = time.perf_counter()
    premier_morceau: float | None = None

    try:
        for piece in client.stream(full, json_mode=json_mode, max_tokens=max_tokens):
            if premier_morceau is None:
                premier_morceau = time.perf_counter() - depart
            collected.append(piece)
            yield piece
        completed = True
    finally:
        total = time.perf_counter() - depart
        sortie = "".join(collected)
        if premier_morceau is not None:
            # ~4 caracteres par jeton en francais : approximation grossiere,
            # mais suffisante pour distinguer 3 jetons/s de 15.
            jetons = max(1, len(sortie) / 4)
            generation = max(total - premier_morceau, 1e-6)
            log.info(
                "Modele %s : prompt %d car. → premier mot %.1f s, total %.1f s "
                "(%d car. produits, ~%.1f jetons/s)",
                get_settings().chat_model,
                taille_prompt,
                premier_morceau,
                total,
                len(sortie),
                jetons / generation,
            )
        else:
            log.warning(
                "Modele %s : aucun mot produit en %.1f s.",
                get_settings().chat_model,
                total,
            )

        # `finally` est indispensable ici, et la raison n'est pas theorique :
        # si l'utilisateur ferme l'onglet en cours de reponse, Python ferme le
        # generateur (GeneratorExit) et tout code place APRES la boucle ne
        # s'executerait jamais. La reponse serait perdue — inacceptable pour un
        # systeme dont la memoire est justement la raison d'etre.
        # Bug constate en coupant reellement un flux, pas en relisant le code.
        if collected:
            conversations.log_message(
                conversation_id,
                "assistant",
                "".join(collected),
                model=get_settings().chat_model,
                meta={
                    "sources": [h.document_path for h in hits],
                    "mode": mode,
                    "interrompu": not completed,
                },
            )


def answer(question: str, *, mode: str = "normal") -> str:
    """Reponse complete en un bloc. Pour la CLI et les traitements de fond."""
    return "".join(answer_stream([{"role": "user", "content": question}], mode=mode))


# ══════════════════════════════════════════════════════════════════════════
#  EXECUTER UNE INTENTION
#
#  C'est ici, et nulle part ailleurs, que Nova passe de la parole a l'acte.
#  L'orchestrateur est le seul module autorise a connaitre a la fois la
#  couche voix (qui reconnait) et la couche outils (qui agit) — les deux
#  s'ignorent, et c'est ce qui permet d'ajouter une action sans toucher a la
#  reconnaissance vocale.
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Resultat:
    """Ce qu'il est advenu d'une intention.

    Quatre issues, et il faut les quatre. Rendre un simple booleen forcerait
    l'appelant a deviner POURQUOI rien ne s'est passe — et il devinerait mal.
    """

    etat: str            # executee | a_confirmer | ignoree | echouee
    message: str
    outil: str | None = None
    niveau: int | None = None
    arguments: dict | None = None

    @property
    def agie(self) -> bool:
        return self.etat == "executee"


def _niveau_de(nom_outil: str) -> int | None:
    """Le niveau de risque declare par un outil, ou `None` s'il est illisible."""
    from nova.outils import registre_outils

    niveau = getattr(registre_outils.get(nom_outil), "niveau", None)
    if isinstance(niveau, bool) or not isinstance(niveau, int):
        return None
    return niveau


#: En dessous, un nom n'evoque rien d'installe et il vaut mieux le dire.
#:
#: CE CHIFFRE EST MESURE, PAS CHOISI. Sur un catalogue macOS realiste :
#:
#:     Fineur      -> Finder        0,600   a proposer
#:     Messagerie  -> Messages      0,625   a proposer
#:     Blender     -> Calendrier    0,556   rien d'installe, on le dit
#:     Slack       -> Plans         0,500   rien d'installe, on le dit
#:     Excel       -> TextEdit      0,500   rien d'installe, on le dit
SEUIL_APPLICATION = 0.60

#: Ecart minimal avec le deuxieme candidat pour parler de certitude. Une
#: ressemblance parfaite avec DEUX applications a la fois n'en designe aucune.
MARGE_APPLICATION = 0.15


@dataclass(frozen=True)
class _Cible:
    """Ce qu'on a pu faire d'une cible entendue.

    `candidats` existe pour le seul etat qui en a besoin : « Adobe » designe
    Photoshop ET Illustrator, et rendre le premier trouve reviendrait a tirer
    au sort. Une ambiguite doit se POSER, pas se trancher en silence.
    """

    nom: str
    etat: str                       # exact | propose | ambigu | inconnu
    candidats: tuple[str, ...] = ()


def _resoudre_application(cible: str) -> _Cible:
    """Confronte une cible entendue au catalogue reel.

        exact     on sait de quelle application il s'agit
        propose   on a un candidat, pas une certitude — il faut demander
        ambigu    plusieurs applications portent ce mot
        inconnu   rien de ressemblant n'est installe

    ⚠️ POURQUOI UNE RESSEMBLANCE ELEVEE NE SUFFIT PAS A AGIR

    Mesure sur un catalogue macOS realiste, cas devant passer et cas devant
    echouer melanges :

        Écoledirecte -> EcoleDirecte  1,000   il fallait ouvrir
        Gogol Chrome -> Google Chrome 0,875   il fallait ouvrir
        Discorde     -> Discord       0,857   il fallait ouvrir
        Photoshop    -> Photo Booth   0,833   IL NE FALLAIT PAS
        Photo bousse -> Photo Booth   0,714   il fallait ouvrir
        Fineur       -> Finder        0,600   il fallait ouvrir

    « Photoshop » n'est pas installe et ressemble davantage a « Photo Booth »
    que « Fineur » ne ressemble a « Finder ». AUCUN seuil ne separe donc les
    deux colonnes — le chercher aurait produit un chiffre arbitraire et une
    application ouverte a tort un jour sur dix.

    La regle qui en decoule est plus simple et plus honnete : on n'agit sans
    demander que sur une correspondance ECRITE (`resoudre`, qui ignore casse
    et accents) ou sur un son IDENTIQUE et sans rival. Tout le reste se
    PROPOSE. Le cout est une question de temps en temps ; le cout de l'autre
    choix etait d'ouvrir la mauvaise application en silence.

    C'EST ICI PAR RESPECT DE LA REGLE DE DEPENDANCE

    `outils/applications.py` sait lire un disque, `voice/phonetique.py` sait
    comparer des sons, et aucun des deux ne connait l'autre. L'orchestrateur
    est le seul module autorise a les faire se rencontrer.

    LE CAS QUI DECIDE DE TOUT : UN CATALOGUE VIDE

    Sur une machine qui n'est pas un Mac, ou si les dossiers sont illisibles,
    `installees()` rend un tuple vide. Il serait tentant d'en conclure
    « aucune application n'existe » et de tout refuser. Ce serait remplacer
    une capacite imparfaite par une panne franche. On laisse passer la cible
    telle quelle : le comportement redevient celui d'avant ce fichier, ce qui
    est le pire acceptable.
    """
    from nova.outils import applications
    from nova.voice import phonetique

    catalogue = applications.installees()
    if not catalogue:
        return _Cible(cible, "exact")

    if reel := applications.resoudre(cible):
        return _Cible(reel, "exact")

    # ── LE SOUS-NOM ──────────────────────────────────────────────────────
    #
    # Personne ne dit « ouvre Adobe Photoshop 2025 » : on dit « Photoshop ».
    # La forme longue est sur le disque, la forme courte est prononcee, et
    # l'ecart est la regle. Un mot ECRIT pareil est une correspondance aussi
    # sure qu'un nom entier — a condition qu'il n'en designe qu'une.
    if sous_noms := applications.par_sous_nom(cible):
        if len(sous_noms) == 1:
            log.info("Application « %s » reconnue comme « %s ».", cible, sous_noms[0])
            return _Cible(sous_noms[0], "exact")
        log.info("Application « %s » : %d candidates.", cible, len(sous_noms))
        return _Cible(cible, "ambigu", sous_noms)

    # Rien d'ecrit pareil : reste l'oreille. On classe TOUT le catalogue —
    # et rien d'autre. La memoire et le vocabulaire declare n'ont pas a
    # concourir ici, ou « Adam » finirait par designer « Adobe ».
    #
    # Chaque application est jugee sur son MEILLEUR angle : son nom entier ou
    # l'un de ses mots. « Crome » ne ressemble pas a « Google Chrome » (0,43)
    # et sonne exactement comme son mot « Chrome » (1,00).
    def note(nom: str) -> float:
        angles = (nom, *applications.jetons(nom))
        return max(phonetique.ressemblance(cible, angle) for angle in angles)

    classement = sorted(((note(nom), nom) for nom in catalogue), reverse=True)
    meilleur, nom = classement[0]

    if meilleur < SEUIL_APPLICATION:
        return _Cible(cible, "inconnu")

    # Les candidats que rien ne separe du premier.
    #
    # « Fotochop » sonne EXACTEMENT autant comme « Photo Booth » que comme
    # « Adobe Photoshop 2025 » — 0,667 des deux cotes. J'ai cherche un
    # departage : longueur du fragment retenu, position du mot. Aucun ne
    # separait ces deux-la sans en melanger d'autres. La conclusion honnete
    # est qu'il n'y a pas de signal, et proposer le premier par ordre
    # alphabetique aurait maquille un tirage au sort en decision.
    ex_aequo = tuple(n for score, n in classement if meilleur - score < MARGE_APPLICATION)
    if len(ex_aequo) > 1:
        log.info("Application « %s » : %d lectures aussi vraisemblables.", cible, len(ex_aequo))
        return _Cible(cible, "ambigu", ex_aequo)

    if meilleur >= 1.0:
        # Meme son exactement, et un seul candidat : « Saffari » pour
        # « Safari », « Crome » pour « Google Chrome ». Demander ici
        # n'apprendrait rien a personne.
        log.info("Application « %s » reconnue comme « %s ».", cible, nom)
        return _Cible(nom, "exact")

    log.info(
        "Application « %s » : « %s » ressemble (%.2f) sans certitude — je demande.",
        cible, nom, meilleur,
    )
    return _Cible(nom, "propose")


#: Au-dela, une liste dite a voix haute ne s'ecoute plus. Trois noms tiennent
#: dans une phrase ; huit ne sont plus une question mais un inventaire.
CANDIDATS_CITES = 3


def _enumerer(noms: tuple[str, ...]) -> str:
    """« A, B ou C », et « A, B ou 4 autres » au-dela.

    Ecrit pour l'OREILLE : cette phrase sera prononcee, pas lue. Une liste a
    puces ne s'entend pas, et une enumeration sans « ou » final laisse croire
    que Nova s'est interrompue.
    """
    cites = list(noms[:CANDIDATS_CITES])
    reste = len(noms) - len(cites)
    if reste > 0:
        cites.append(f"{reste} autre{'s' if reste > 1 else ''}")
    if len(cites) == 1:
        return f"« {cites[0]} »"
    debut = ", ".join(f"« {n} »" for n in cites[:-1])
    dernier = cites[-1]
    fin = dernier if dernier[0].isdigit() else f"« {dernier} »"
    return f"{debut} ou {fin}"


def _confronter_au_reel(
    action, cible: str, *, confirme: bool
) -> tuple[dict | None, Resultat | None]:
    """Valide la cible avant qu'elle n'atteigne l'outil.

    Rend soit les arguments a utiliser, soit le `Resultat` qui interrompt.
    """
    from nova.core import actions, contrats

    if action.catalogue != actions.CATALOGUE_APPLICATIONS or not action.argument:
        return {action.argument: cible} if action.argument else {}, None

    trouvee = _resoudre_application(cible)
    retenu, etat = trouvee.nom, trouvee.etat

    if etat == "ambigu":
        # On NE tranche PAS a la place de l'utilisateur. La question est posee
        # en `echouee` et non en `a_confirmer` a dessein : « oui » ne saurait
        # pas designer laquelle. Elle se repond en nommant l'application, ce
        # qui repart comme une demande neuve — sans etat a garder.
        return None, Resultat(
            "echouee",
            f"« {cible} » peut désigner {_enumerer(trouvee.candidats)}. Laquelle ?",
            outil=action.outil, arguments={action.argument: cible},
        )

    if etat == "inconnu":
        # Dire ce qu'on ne trouve pas vaut mieux que laisser `open` echouer
        # avec un message en anglais sur un nom que Nova a peut-etre mal
        # entendu.
        return None, Resultat(
            "echouee",
            f"Je ne trouve pas d'application « {cible} » sur cette machine.",
            outil=action.outil, arguments={action.argument: cible},
        )

    if etat == "propose":
        # ⚠️ DEUX QUESTIONS NE PEUVENT PAS TENIR DANS UN SEUL « OUI ».
        #
        # La confirmation remonte par un unique champ booleen. Si un outil
        # dangereux avait AUSSI une cible incertaine, le « oui » de
        # l'utilisateur repondrait aux deux a la fois — il croirait valider un
        # nom et validerait une action irreversible. On refuse plutot que de
        # confondre : aujourd'hui aucun outil n'est dans ce cas, et le jour ou
        # l'un le sera, il trouvera cette garde au lieu du piege.
        if contrats.exige_confirmation(_niveau_de(action.outil) or contrats.IRREVERSIBLE):
            return None, Resultat(
                "echouee",
                f"Je ne suis pas sûre de « {cible} » — je ne devine pas sur une "
                "action de cette importance.",
                outil=action.outil, arguments={action.argument: cible},
            )
        if not confirme:
            return None, Resultat(
                "a_confirmer",
                f"Je ne connais pas « {cible} ». Tu veux dire « {retenu} » ?",
                outil=action.outil, niveau=_niveau_de(action.outil),
                arguments={action.argument: retenu},
            )

    return {action.argument: retenu}, None


def executer_intention(comprise, *, confirme: bool = False) -> Resultat:
    """Passe a l'acte, si et seulement si tout concorde. Ne leve jamais.

    `confirme` vient de l'UTILISATEUR, jamais du modele : c'est la reponse
    a une question posee, pas un champ qu'une IA peut remplir elle-meme.
    """
    from nova.core import actions
    from nova.outils import ConfirmationRequise, executer_outil

    intention = comprise.intention
    if not intention.reconnue:
        return Resultat("ignoree", "Aucune intention reconnue.")

    # ── LES DEUX CONFIANCES, ET POURQUOI IL EN FAUT DEUX ─────────────────
    #
    # « Sur quelle planete pour lui en ouvrir » etait une transcription
    # bancale contenant « ouvrir » : intention nette, parole douteuse. Agir
    # sur ce seul signal aurait lance une application au milieu d'une
    # question d'astronomie.
    #
    # Dans le doute, Nova PARLE au lieu d'AGIR. C'est rattrapable dans ce
    # sens-la, jamais dans l'autre.
    if not actions.executable(intention.nom, intention.confiance, comprise.sure):
        raison = (
            "action inconnue" if actions.action_pour(intention.nom) is None
            else "parole ou intention trop incertaine"
        )
        log.info(
            "Intention « %s » NON executee (%s) : parole %s (%.2f), intention %.2f.",
            intention.nom, raison,
            "sûre" if comprise.sure else "douteuse",
            comprise.confiance, intention.confiance,
        )
        return Resultat("ignoree", f"Intention reconnue mais non executee : {raison}.")

    action = actions.action_pour(intention.nom)

    # La cible est confrontee au reel AVANT d'atteindre l'outil. Un nom
    # d'application mal entendu doit se rattraper ici, ou il deviendra un
    # echec de `open` sur lequel personne ne peut rien.
    arguments, interruption = _confronter_au_reel(
        action, intention.cible, confirme=confirme
    )
    if interruption is not None:
        log.info(
            "Cible « %s » non retenue pour « %s » : %s",
            intention.cible, action.outil, interruption.etat,
        )
        return interruption

    try:
        message = executer_outil(action.outil, confirme=confirme, **arguments)
        return Resultat("executee", str(message), outil=action.outil, arguments=arguments)
    except ConfirmationRequise as attente:
        return Resultat(
            "a_confirmer", attente.question(),
            outil=action.outil, niveau=attente.niveau, arguments=arguments,
        )
    except Exception as exc:  # noqa: BLE001
        # Une action qui echoue doit le DIRE. Un echec silencieux laisse
        # croire que Nova a agi, ce qui est la pire des issues.
        log.warning("Action « %s » en echec : %s", action.outil, exc)
        return Resultat("echouee", str(exc), outil=action.outil, arguments=arguments)
