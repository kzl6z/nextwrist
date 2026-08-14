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
    # RETOUR A `base` — et l'aller-retour vaut d'etre raconte.
    #
    # `small` avec 5 hypotheses avait ete choisi pour corriger la
    # comprehension, en jugeant ses 2,5 secondes de plus negligeables devant
    # un modele qui mettait 25 secondes. Le raisonnement etait juste, mais il
    # reposait sur un chiffre faux : ces 25 secondes n'etaient pas le cout du
    # modele, c'etait le cout de la CONCURRENCE que Whisper lui faisait.
    #
    # Mesure au banc, application fermee :
    #
    #     llama3.2:3b   lecture 0,2 s   ecriture 28,8 jetons/s
    #
    # Les memes appels, avec l'application ouverte et `small` resident :
    #
    #     llama3.2:3b   lecture  21 s   ecriture  9,6 jetons/s
    #
    # Whisper ne coutait donc pas 2,5 secondes : il coutait 2,5 secondes DE
    # PLUS, et il divisait par trois la vitesse du modele. Sur 8 Go partages,
    # un modele resident se paie deux fois — en memoire, puis en lenteur de
    # tout le reste.
    #
    # Ce qui a reellement repare la comprehension, ce n'est pas la taille du
    # modele : c'est le decoupage par la parole (phrase entiere au lieu d'un
    # extrait au chronometre) et les 400 ms de pre-roll. Ca reste acquis.
    #
    # Pour revenir a `small` :  NOVA_WHISPER_MODEL=small  dans .env
    whisper_model: str = "base"
    whisper_compute: str = "int8"
    # Largeur de recherche. 5 explore plusieurs hypotheses et corrige des
    # erreurs comme « Quelheur est-il ? » — mais chaque hypothese est du calcul
    # pris au modele de langue qui tourne a cote. Sur cette machine, le
    # glouton redevient le bon compromis.
    whisper_beam: int = 1
    # Le mot de reveil, lui, doit rester glouton : il tourne en continu et ne
    # cherche qu'un seul mot. La finesse n'y apporte rien, le cout si.
    whisper_beam_reveil: int = 1
    # Filtre de detection de parole. Desactive par defaut : sur des
    # enregistrements courts declenches au clavier, il rejette parfois la
    # totalite de l'audio et Nova recoit une transcription vide. Le risque
    # qu'il evite (Whisper qui invente du texte sur du silence) concerne
    # surtout l'ecoute continue, qu'on ne fait pas encore.
    whisper_vad: bool = False
    # Meme modele que la dictee, volontairement. Deux modeles differents, ce
    # sont deux jeux de poids residents ; sur 8 Go partages avec le modele de
    # langue, chaque megaoctet resident se paie deux fois — en memoire, puis
    # en lenteur de tout ce qui tourne a cote.
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
    # Vocabulaire declare a la main, separe par des virgules. Sert aux noms
    # que Nova ne peut pas deviner : marques, personnes, jargon de metier.
    #
    #     NOVA_WHISPER_VOCABULAIRE=Sentinel, Aznavour, Kozlowski, pinata
    #
    # Les noms deja presents dans sa memoire s'y ajoutent automatiquement :
    # plus elle te connait, mieux elle t'entend.
    whisper_vocabulaire: str = ""
    # Vitesse d'ecriture MESUREE du modele, en jetons par seconde. Sert au
    # routeur pour ecarter un modele trop lent pour un usage donne.
    #
    #     uv run python scripts/bench_models.py
    #
    # La valeur par defaut est celle relevee sur l'iMac M1 de reference avec
    # llama3.2:3b. Une mesure fausse vaut mieux qu'une absence : elle se
    # corrige, alors qu'un champ vide oblige a deviner.
    vitesse_mesuree: float = 28.8
    # Delai de LECTURE accorde au moteur, en secondes.
    #
    # ⚠️ REGLE : CE DELAI DOIT RESTER PLUS COURT QUE CELUI DE L'APPELANT.
    #
    # L'application de bureau attend Nova Core pendant 120 s ; Nova Core
    # attendait Ollama pendant 300 s. Un appelant qui abandonne AVANT son
    # appele ne recoit jamais le vrai diagnostic : il rend le sien, qui est
    # faux. Releve en conditions reelles — Ollama etait eteint, Nova Core
    # l'attendait, et l'application a conclu « Nova Core est-il lance ? »
    # alors que Nova Core allait parfaitement bien. Puis elle a REESSAYE le
    # meme chemin mort : 2 x 120 s = quatre minutes pour une erreur que la
    # couche du dessous connaissait au bout de deux secondes.
    #
    # 90 s couvre largement la generation la plus lente observee (~30 s) et
    # le chargement d'un modele depuis le disque (~21 s), tout en laissant
    # 30 s de marge sous le plafond de l'application.
    request_timeout: float = 90.0
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
        # Defaut si la config vient d'une version anterieure : une ancienne
        # config ne doit jamais empecher Nova de demarrer.
        self.extraits_budget: int = data["recherche"].get("budget_caracteres_extraits", 2000)
        self.chunk_size: int = data["decoupage"]["taille"]
        self.chunk_overlap: int = data["decoupage"]["recouvrement"]
        self.faits_max: int = data["memoire"]["faits_max_dans_prompt"]
        # Valeur par defaut si le fichier vient d'une version anterieure : une
        # config plus ancienne ne doit jamais empecher Nova de demarrer.
        self.faits_budget: int = data["memoire"].get("budget_caracteres_prompt", 1200)


@lru_cache
def get_settings() -> Settings:
    """Instance unique, mise en cache : la config ne se relit pas a chaque appel."""
    return Settings()


@lru_cache
def get_tuning() -> Tuning:
    path = ROOT / "config" / "nova.toml"
    with path.open("rb") as fh:
        return Tuning(tomllib.load(fh))
