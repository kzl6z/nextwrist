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


def _termes_de_la_memoire() -> tuple[str, ...]:
    """Les noms propres des faits confirmes, avec un cache court.

    Ne leve jamais : memoire indisponible = vocabulaire vide, donc une
    transcription moins precise sur les noms propres. Jamais une panne.
    """
    global _vocabulaire_cache

    maintenant = time.monotonic()
    cache = _vocabulaire_cache
    if cache is not None and maintenant - cache[0] < DUREE_CACHE_VOCABULAIRE:
        return cache[1]

    with _verrou_vocabulaire:
        # Un autre fil a pu le calculer pendant qu'on attendait le verrou.
        cache = _vocabulaire_cache
        if cache is not None and time.monotonic() - cache[0] < DUREE_CACHE_VOCABULAIRE:
            return cache[1]
        try:
            contenus = [f.content for f in facts.list_facts(status="confirmed")]
            termes = tuple(vocabulaire.extraire_termes(contenus))
        except Exception as exc:  # noqa: BLE001
            log.warning("Vocabulaire de la memoire indisponible : %s", exc)
            termes = ()
        _vocabulaire_cache = (time.monotonic(), termes)
        return termes


def oublier_le_vocabulaire() -> None:
    """Force le prochain appel a relire la memoire.

    A appeler quand un fait vient d'etre confirme : le nom qu'il contient doit
    etre entendu correctement des la phrase suivante, pas dans une minute.
    """
    global _vocabulaire_cache
    _vocabulaire_cache = None


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
    if not get_settings().thinking and not contrat:
        # Interrupteur documente de Qwen 3. Inoffensif pour les modeles qui ne
        # le connaissent pas : ce n'est qu'une ligne de texte de plus.
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
    if len(user_message.strip()) >= MIN_QUERY_LENGTH:
        try:
            hits = document_search.search(user_message)
        except Exception as exc:  # noqa: BLE001
            # Une recherche en echec ne doit JAMAIS empecher Nova de repondre.
            # Chaque capacite est facultative : c'est ce qui rend le systeme
            # robuste quand on en ajoutera dix autres.
            log.warning("Recherche documentaire indisponible : %s", exc)

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
    full: list[Message] = [{"role": "system", "content": system_prompt}, *history]

    conversation_id = conversations.get_or_create(conversation_external_id)
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
