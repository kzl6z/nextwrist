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

    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="NOVA_", extra="ignore")

    database_url: str = "postgresql://nova:nova@localhost:5432/nova"

    # Ollama expose une API compatible OpenAI sur /v1. C'est notre frontiere
    # stable : changer de moteur d'inference = changer cette seule URL.
    ollama_url: str = "http://localhost:11434/v1"
    chat_model: str = "qwen3:8b"
    embedding_model: str = "bge-m3"

    # Doit correspondre a vector(N) dans migrations/002. Ne pas changer seul.
    embedding_dim: int = 1024

    temperature: float = 0.4

    # Qwen 3 est un modele "hybride" : par defaut il produit une longue phase de
    # reflexion AVANT de repondre. Sur un petit modele local, cela se traduit par
    # 30 a 90 secondes de silence total — l'utilisateur croit que rien ne marche.
    # On la desactive par defaut ; mets NOVA_THINKING=true pour l'analyse lourde.
    thinking: bool = False

    # Plafond de longueur de reponse. C'est LE levier sur la latence percue :
    # un modele local genere ~15-25 mots/seconde, donc une reponse de 600 mots
    # prend 30 secondes quoi qu'on fasse. Limiter la longueur est plus efficace
    # que n'importe quelle optimisation technique.
    max_tokens: int = 500

    # ── Transcription locale (optionnelle) ────────────────────────────────
    #
    # `base` avait ete choisi contre `small` pour la vitesse : 1,2 s au lieu
    # de ~3 s. Ce raisonnement etait juste isolement et faux dans l'ensemble.
    # Mesure reelle du cycle complet sur M1 8 Go :
    #
    #     transcription   1,2 s
    #     modele          8,9 s a 27,6 s      ← le vrai cout
    #
    # Gagner 1,8 s sur la transcription ne se remarque pas ; se tromper sur
    # les mots gache tout ce qui suit, car le modele repond alors a une
    # question que personne n'a posee. On paie donc la precision.
    #
    # `medium` reste exclu : trop de memoire sur 8 Go, et il faudrait le
    # garder resident a cote du modele de langue.
    whisper_model: str = "small"
    whisper_compute: str = "int8"
    # Largeur de recherche. 1 = glouton : le modele garde le premier mot venu
    # et ne revient jamais dessus, ce qui produit exactement les erreurs
    # observees (« Quelheur est-il ? »). 5 explore plusieurs hypotheses et
    # retient la plus vraisemblable une fois la phrase entiere connue — c'est
    # le reglage qui corrige le plus d'erreurs pour le moins de temps.
    whisper_beam: int = 5
    # Le mot de reveil, lui, doit rester glouton : il tourne en continu et ne
    # cherche qu'un seul mot. La finesse n'y apporte rien, le cout si.
    whisper_beam_reveil: int = 1
    # Filtre de detection de parole. Desactive par defaut : sur des
    # enregistrements courts declenches au clavier, il rejette parfois la
    # totalite de l'audio et Nova recoit une transcription vide. Le risque
    # qu'il evite (Whisper qui invente du texte sur du silence) concerne
    # surtout l'ecoute continue, qu'on ne fait pas encore.
    whisper_vad: bool = False
    # Modele dedie au mot de reveil. `tiny` (~75 Mo) suffit largement :
    # reconnaitre un seul mot ne demande aucune finesse, et il tourne en
    # ~150 ms — indispensable puisqu'il est appele en continu.
    whisper_wake_model: str = "base"
    # Amorce donnee au modele : elle oriente le vocabulaire attendu.
    # Sans elle, « Nova » — qui n'est pas un mot francais courant — est
    # transcrit « Nouveau », « Au revoir », « No va »… Constate en conditions
    # reelles. Avec elle, le modele sait que ce mot existe et le reconnait.
    whisper_amorce: str = "Nova. Nova, quelle heure est-il ? Nova, ouvre un projet."
    # Amorce de la DICTEE. Elle ne joue pas le meme role que celle du reveil :
    # ici on ne cherche pas un mot, on transcrit une phrase entiere. L'amorce
    # sert alors a fixer le registre — francais soutenu, ponctuation complete,
    # questions bien formees — parce que Whisper imite ce qu'on lui montre.
    # Sans elle il produit du texte sans accents ni ponctuation, que le modele
    # de langue comprend nettement moins bien.
    whisper_amorce_dictee: str = (
        "Nova, quelle heure est-il ? Nova, que sais-tu de moi ? "
        "Nova, ouvre un nouveau projet. Nova, resume-moi ce document. "
        "Quel jour sommes-nous aujourd'hui ?"
    )
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
