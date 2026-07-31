"""Journalisation.

Les logs sont le premier outil de debogage : quand quelque chose ne marche pas,
la reponse y est presque toujours. On les rend donc lisibles des le depart.
"""

from __future__ import annotations

import logging

from rich.logging import RichHandler

from nova.settings import get_settings

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    # httpx journalise chaque requete en INFO : trop bavard pour nous.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
