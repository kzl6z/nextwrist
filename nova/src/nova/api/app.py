"""Application FastAPI — assemblage des routeurs.

Ce fichier reste volontairement minuscule. Une application dont le point
d'entree grossit est une application dont la logique a fui hors des modules.
"""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from nova.api import admin, anthropic_compat, audio_compat, noyau, openai_compat
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

        enregistrer_outils_standard(settings.root / "data")
        log.info("Outils disponibles : %s", ", ".join(registre_outils.noms()))
    except Exception as exc:  # noqa: BLE001
        log.warning("Outils indisponibles : %s", exc)

    arret = threading.Event()
    threading.Thread(target=_entretenir, args=(arret,), daemon=True, name="chauffe").start()
    threading.Thread(target=_prechauffer_la_voix, daemon=True, name="voix").start()

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
app.include_router(admin.router)


@app.get("/")
def root() -> dict:
    return {"name": "Nova", "version": "0.1.0", "docs": "/docs"}
