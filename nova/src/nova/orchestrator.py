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

import time
from collections.abc import Iterator
from datetime import datetime

from nova import prompts
from nova.documents import search as document_search
from nova.llm.client import LLMClient, Message
from nova.logging_setup import get_logger
from nova.memory import conversations, facts
from nova.memory.models import SearchHit
from nova.settings import get_settings

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


def instant_present(maintenant: datetime | None = None) -> str:
    """Date et heure, en francais, pour le prompt systeme."""
    maintenant = maintenant or datetime.now().astimezone()
    return (
        f"{JOURS[maintenant.weekday()]} {maintenant.day} "
        f"{MOIS[maintenant.month - 1]} {maintenant.year}, il est "
        f"{maintenant.strftime('%H:%M')}"
    )


def _format_sources(hits: list[SearchHit]) -> str:
    """Met les extraits en forme pour le prompt.

    Chaque extrait est explicitement etiquete par sa source afin que le modele
    puisse citer. Sans cette etiquette, il invente les references — c'est
    systematique.
    """
    blocks = []
    for hit in hits:
        label = hit.heading or "sans titre"
        blocks.append(f'--- [{hit.document_title}, "{label}"]\n{hit.content}')
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
            log.warning("Modele %s : aucun mot produit en %.1f s.", get_settings().chat_model, total)

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
