"""Application FastAPI — assemblage des routeurs.

Ce fichier reste volontairement minuscule. Une application dont le point
d'entree grossit est une application dont la logique a fui hors des modules.
"""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from nova.api import actions, admin, anthropic_compat, audio_compat, noyau, openai_compat
from nova.core import plateforme
from nova.db import run_migrations
from nova.llm.client import LLMClient
from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)


# ── ENTRETIEN DU MODELE ───────────────────────────────────────────────────
#
# Un modele decharge doit etre relu depuis le disque avant de repondre. Mesure
# sur l'iMac M1 : un cout FIXE de 21 secondes, identique pour un prompt de 880
# et de 6573 caracteres. C'est cette independance a la taille de l'entree qui
# trahit un chargement — un vrai temps de lecture aurait ete sept fois moindre
# sur le petit prompt. Deux tours ont ete perdus a raccourcir le prompt.
#
# Ollama decharge apres cinq minutes d'inactivite, et plus tot quand la machine
# manque de memoire. Le champ `keep_alive` du point d'entree OpenAI-compatible
# est ignore en silence, et `OLLAMA_KEEP_ALIVE` demande une manipulation que
# l'utilisateur oubliera un jour de refaire.
#
# On n'en depend donc pas : Nova entretient elle-meme. Un jeton toutes les
# quatre minutes suffit, et ne coute rien de perceptible.
INTERVALLE_CHAUFFE = 240.0


def _prechauffer_la_voix() -> None:
    """Charge le modele de transcription AVANT qu'on en ait besoin.

    Sans ca, la premiere phrase prononcee paie le chargement — plusieurs
    secondes pendant lesquelles Nova parait sourde alors qu'elle demarre. Le
    faire en tache de fond, des le lancement, deplace ce cout la ou personne
    ne l'attend.

    C'est la forme la plus simple du principe de reactivite : le travail
    previsible se fait pendant que l'utilisateur ne regarde pas.
    """
    try:
        from nova.voice import transcribe

        if not transcribe.disponible():
            return
        depart = time.perf_counter()
        transcribe._modele()  # noqa: SLF001 — chargement volontaire
        log.info(
            "Transcription prete (%s) en %.1f s — la premiere phrase ne l'attendra pas.",
            get_settings().whisper_model,
            time.perf_counter() - depart,
        )
    except Exception as exc:  # noqa: BLE001
        # Une capacite facultative qui echoue ne doit jamais empecher Nova de
        # demarrer. C'est la regle du projet.
        log.warning("Prechauffage de la transcription impossible : %s", exc)


def _entretenir(arret: threading.Event) -> None:
    """Garde le modele resident, en tache de fond, jusqu'a l'arret."""
    client = LLMClient()
    premiere = True
    while not arret.is_set():
        # Le vocabulaire personnel se relit ICI, ou l'attente ne coute rien.
        # Dans une requete vocale, la meme lecture ferait attendre la parole
        # de Nova pour un enrichissement facultatif.
        try:
            from nova import orchestrator

            termes = orchestrator.rafraichir_le_vocabulaire()
            if premiere:
                log.info("Vocabulaire personnel : %d terme(s) connu(s).", len(termes))
        except Exception as exc:  # noqa: BLE001
            log.warning("Vocabulaire non rafraichi : %s", exc)

        # ── LA MESURE QUI DEPARTAGE DEUX PANNES OPPOSEES ─────────────────
        #
        # « Tout se fige pendant qu'elle repond, sauf la souris » a deux
        # causes possibles sur une puce a memoire unifiee, et elles se
        # corrigent a l'inverse l'une de l'autre : la contention GPU se regle
        # en ralentissant l'affichage, la pagination ne se regle QUE par un
        # modele plus leger. Le dire ici evite d'y passer une journee du
        # mauvais cote.
        pression = plateforme.pression_memoire()
        if pression.pagine and premiere:
            reglages = get_settings()
            log.warning(
                "La machine pagine (%s). Tout ralentit, Nova comprise, et aucun "
                "reglage d'interface n'y peut rien.",
                pression,
            )
            # Nova ne sait pas ce que pesent le navigateur ou la base. Elle
            # sait exactement ce qu'elle tient, elle — la seule part sur
            # laquelle quelqu'un peut agir en une ligne.
            for ligne in plateforme.empreinte_nova(
                reglages.chat_model, [reglages.whisper_model, reglages.whisper_wake_model]
            ).splitlines():
                log.warning("%s", ligne)
        elif premiere:
            log.info("Memoire : %s — pas de pagination.", pression)

        duree = client.chauffer()
        if duree is not None and (premiere or duree > 5.0):
            # Au-dela de cinq secondes, ce n'etait pas un simple aller-retour :
            # le modele venait d'etre recharge. Le dire permet de comprendre
            # une lenteur au lieu de l'attribuer au hasard.
            log.info(
                "Modele %s %s en %.1f s.",
                get_settings().chat_model,
                "charge" if premiere or duree > 5.0 else "maintenu",
                duree,
            )
        premiere = False
        arret.wait(INTERVALLE_CHAUFFE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au demarrage : migrations, puis mise en chauffe du modele.

    Nova doit pouvoir demarrer sur une base vide et se mettre en etat toute
    seule. C'est ce qui rend `docker compose up` reellement suffisant.
    """
    settings = get_settings()
    log.info("Nova demarre — modele %s", settings.chat_model)
    try:
        if applied := run_migrations():
            log.info("Migrations appliquees : %s", ", ".join(applied))
    except Exception as exc:  # noqa: BLE001
        log.error("Base de donnees injoignable : %s", exc)

    # ── Inventaire, puis prechauffage ────────────────────────────────────
    #
    # L'inventaire est instantane et dit ce que Nova sait faire aujourd'hui.
    # Le prechauffage est lent et se fait DERRIERE : le demarrage ne doit
    # jamais attendre un modele.
    log.info("Machine : %s", plateforme.resume())
    # Un modele trop lourd ne provoque aucune erreur : il pagine sur le
    # disque, en silence, et fait passer la machine pour un mauvais choix.
    # On le dit une fois, fort, plutot que de laisser chercher des heures.
    if alerte := plateforme.modele_trop_lourd(settings.chat_model):
        for ligne in alerte.splitlines():
            log.warning("%s", ligne)
    try:
        from nova.outils import enregistrer_outils_standard, registre_outils
        from nova.outils.systeme import enregistrer_actions_systeme

        enregistrer_outils_standard(settings.root / "data")
        # Les actions systeme sont enregistrees SEPAREMENT : ce sont les
        # seules qui modifient la machine, et on doit pouvoir les retirer
        # d'une ligne sans toucher au reste.
        enregistrer_actions_systeme(registre_outils)
        # Les outils de vision sont inscrits meme vision desactivee : ils
        # levent alors un message qui dit comment l'activer, ce qui vaut
        # mieux qu'une capacite annoncee non couverte.
        from nova.outils.vision import enregistrer_outils_vision

        enregistrer_outils_vision(registre_outils, settings.root / "data")
        # Retrouver un fichier ne charge aucun modele : ces outils-la
        # servent sur toute machine, et le reglage decide seulement de ce qui
        # se declenche tout seul dans la conversation.
        from nova.outils.fichiers import enregistrer_outils_fichiers

        enregistrer_outils_fichiers(registre_outils)
        log.info("Outils disponibles : %s", ", ".join(registre_outils.noms()))

        # ⚠️ LES AGENTS N'ETAIENT INSCRITS NULLE PART.
        #
        # `Conversationnel` et `Documentaire` existaient, avec leurs bancs, et
        # aucun code ne les enregistrait. `/v1/capacites` annoncait donc zero
        # agent : un inventaire exact d'un systeme vide, alors que le code
        # etait la. Un module teste que rien n'appelle est plus trompeur qu'un
        # module absent — la revue le compte comme fait.
        from nova.core.gestionnaire import (
            capacites_sans_executant,
            enregistrer_agents_standard,
        )

        # `orchestrator` est importe ICI et pas en tete : il tire la memoire,
        # la recherche documentaire et le client de modele. Le demarrage ne
        # doit pas les payer avant d'en avoir besoin.
        def repondre(question: str) -> str:
            from nova import orchestrator

            return orchestrator.answer(question)

        enregistrer_agents_standard(repondre, settings.root / "data")
        # La vision est desactivee par defaut : elle charge un modele qui
        # decharge celui de la langue sur cette machine. Le dire au demarrage
        # evite de chercher pourquoi « Nova ne voit pas ».
        from nova.vision.moteur import disponible as vision_disponible

        utilisable, raison = vision_disponible()
        log.info("Vision : %s", "active" if utilisable else raison.splitlines()[0])

        if manquantes := capacites_sans_executant():
            # Le planificateur peut produire ces capacites ; personne ne sait
            # les executer. Le dire au demarrage evite de le decouvrir au
            # milieu d'un plan de sept etapes.
            log.info(
                "Capacites sans executant : %s — les etapes correspondantes "
                "seront signalees, jamais simulees.",
                ", ".join(manquantes),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Outils indisponibles : %s", exc)

    arret = threading.Event()
    threading.Thread(target=_entretenir, args=(arret,), daemon=True, name="chauffe").start()
    threading.Thread(target=_prechauffer_la_voix, daemon=True, name="voix").start()
    # ⚠️ CE FIL EST LE SEUL QUI CHARGE UN MODELE SANS QU'ON LUI AIT RIEN
    #    DEMANDE — il attend donc deux minutes de silence avant d'oser.
    #
    # Il ne demarre pas du tout quand la vision est eteinte, ce qui est le
    # defaut : personne ne paie pour une capacite qu'il n'utilise pas.
    from nova.vision.indexation import entretenir as indexer_les_images

    threading.Thread(
        target=indexer_les_images, args=(arret,), daemon=True, name="images"
    ).start()
    # ⚠️ RESUMER COUTE UN APPEL DE MODELE — DONC JAMAIS PENDANT QU'ON PARLE.
    #
    # Ce fil ne touche qu'aux conversations silencieuses depuis deux minutes,
    # et n'en fait qu'une par passage. Sans lui, le resume de session
    # n'existerait qu'en theorie : la lecture est cablee dans l'orchestrateur
    # depuis le debut, mais rien n'aurait jamais ecrit une ligne.
    from nova.memory.resume import entretenir as resumer_les_sessions

    threading.Thread(
        target=resumer_les_sessions, args=(arret,), daemon=True, name="resumes"
    ).start()

    yield

    arret.set()
    log.info("Nova s'arrete")


app = FastAPI(
    title="Nova",
    description="Assistant personnel local. Compatible OpenAI et Anthropic sur /v1.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(openai_compat.router)
app.include_router(anthropic_compat.router)
app.include_router(audio_compat.router)
app.include_router(noyau.router)
app.include_router(actions.router)
app.include_router(admin.router)


@app.get("/")
def root() -> dict:
    return {"name": "Nova", "version": "0.1.0", "docs": "/docs"}
