"""Configuration de Nova.

Deux sources, deux roles distincts :
  - `.env`            : ce qui depend de la MACHINE (URL, mots de passe, modeles)
  - `config/nova.toml`: ce qui depend du METIER (seuils, tailles)

Tout est valide au demarrage : une faute de frappe fait echouer le lancement
plutot que de produire un comportement bizarre trois semaines plus tard.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_root() -> Path:
    """Racine du projet : le dossier qui contient `config/`.

    Deux contextes a couvrir : execution locale (depuis le depot) et execution
    dans Docker (WORKDIR /app). On cherche donc au lieu de coder un chemin en dur.
    """
    for candidate in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if (candidate / "config").is_dir():
            return candidate
    return Path.cwd()


ROOT = _find_root()


class Settings(BaseSettings):
    """Reglages machine, lus depuis l'environnement ou `.env`, prefixes NOVA_."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_prefix="NOVA_", extra="ignore"
    )

    database_url: str = "postgresql://nova:nova@localhost:5432/nova"

    # Ollama expose une API compatible OpenAI sur /v1. C'est notre frontiere
    # stable : changer de moteur d'inference = changer cette seule URL.
    ollama_url: str = "http://localhost:11434/v1"
    chat_model: str = "qwen3:8b"
    embedding_model: str = "bge-m3"

    # Doit correspondre a vector(N) dans migrations/002. Ne pas changer seul.
    embedding_dim: int = 1024

    temperature: float = 0.4
    request_timeout: float = 300.0
    log_level: str = "INFO"

    @property
    def root(self) -> Path:
        return ROOT

    @property
    def prompts_dir(self) -> Path:
        return ROOT / "config" / "prompts"

    @property
    def migrations_dir(self) -> Path:
        return ROOT / "migrations"


class Tuning:
    """Reglages metier, lus depuis `config/nova.toml`.

    Separes des Settings parce qu'ils se modifient souvent, a chaud, sans
    redemarrer quoi que ce soit d'autre que Nova.
    """

    def __init__(self, data: dict) -> None:
        self.extraits_max: int = data["recherche"]["extraits_max"]
        self.candidats_par_moteur: int = data["recherche"]["candidats_par_moteur"]
        self.chunk_size: int = data["decoupage"]["taille"]
        self.chunk_overlap: int = data["decoupage"]["recouvrement"]
        self.faits_max: int = data["memoire"]["faits_max_dans_prompt"]


@lru_cache
def get_settings() -> Settings:
    """Instance unique, mise en cache : la config ne se relit pas a chaque appel."""
    return Settings()


@lru_cache
def get_tuning() -> Tuning:
    path = ROOT / "config" / "nova.toml"
    with path.open("rb") as fh:
        return Tuning(tomllib.load(fh))
