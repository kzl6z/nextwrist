"""Application FastAPI — assemblage des routeurs.

Ce fichier reste volontairement minuscule. Une application dont le point
d'entree grossit est une application dont la logique a fui hors des modules.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from nova.api import admin, openai_compat
from nova.db import run_migrations
from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au demarrage : appliquer les migrations en attente.

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
    yield
    log.info("Nova s'arrete")


app = FastAPI(
    title="Nova",
    description="Assistant personnel local. Compatible OpenAI sur /v1.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(openai_compat.router)
app.include_router(admin.router)


@app.get("/")
def root() -> dict:
    return {"name": "Nova", "version": "0.1.0", "docs": "/docs"}
