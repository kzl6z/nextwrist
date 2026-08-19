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
    # ⚠️ CE DEFAUT DOIT TENIR SUR LA MACHINE DE REFERENCE (iMac M1, 8 Go).
    #
    # Il valait « qwen3:8b » — 5,2 Go pour un budget de 3,6. Un modele trop
    # gros ne refuse pas de tourner : il pagine sur le disque, sans erreur ni
    # journal. La seule trace est le chronometre, et on accuse la machine.
    #
    # Pire, il contredisait `vitesse_mesuree` plus bas, dont la valeur (28,8
    # jetons/s) a ete relevee avec llama3.2:3b. Le routeur croyait donc que
    # qwen3:8b ecrivait a la vitesse d'un modele deux fois plus leger, et le
    # jugeait assez rapide pour tous les usages. Deux defauts qui se
    # decrivaient mutuellement de travers.
    #
    # Un defaut doit fonctionner sur la machine du projet. Qui a mieux le
    # declare dans .env — c'est ce que ce champ est fait pour.
    chat_model: str = "llama3.2:3b"
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
    # ── Coeurs laisses a la machine pendant que Nova transcrit ────────────
    #
    # ⚠️ ZERO N'EST PAS UN DEFAUT NEUTRE ICI.
    #
    # `faster-whisper` interprete `cpu_threads=0` comme « prends tous les
    # coeurs », et c'etait le comportement — jamais choisi, simplement herite
    # de l'absence d'argument. Pendant une transcription, la machine entiere
    # se retrouvait donc sans un seul coeur disponible pour l'interface.
    #
    # 0 signifie ici « decide pour moi » : tous les coeurs sauf deux. Deux,
    # parce qu'il en faut un pour le systeme et un pour ce que la personne est
    # en train de faire — c'est le minimum pour que la machine reste a elle
    # pendant que Nova travaille. Une valeur explicite l'emporte toujours.
    whisper_threads: int = 0
    # ── Deux modeles, deux metiers ────────────────────────────────────────
    #
    # Celui-ci tourne EN BOUCLE des que le micro depasse un seuil, et ne
    # cherche qu'un seul mot connu. Il doit etre le plus leger possible ; la
    # finesse n'y apporte rien.
    #
    # Il servait AUSSI a transcrire la question qui suit le mot de reveil —
    # un reglage choisi pour reconnaitre « Nova » decidait donc de ce que Nova
    # comprenait de toute la phrase. Releve en conditions reelles :
    #
    #     dit      « quel est le diametre de la Terre »
    #     entendu  « quelle est-il de germetre de la terre »
    #
    # Depuis, `/v1/audio/wake` RELIT le meme audio avec les reglages de
    # dictee des qu'une question suit. Les deux metiers sont separes, et
    # `whisper_model` peut donc grossir sans alourdir l'ecoute continue.
    # Pour choisir sur ta voix :  uv run python scripts/bench_whisper.py
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
    # Les ORDRES y figurent maintenant, et pas par decoration.
    #
    # Releve en conditions reelles : « monte le son à 80 % » transcrit
    # « MONTRE le son à 80 % ». Les deux mots ne different que d'une lettre et
    # « montre » est bien plus frequent en francais — Whisper choisit le mot
    # courant. Le rapprochement phonetique des declencheurs rattrape le cas
    # apres coup ; l'amorce s'attaque a la cause, en montrant a Whisper que
    # « monte le son » est une phrase attendue ici.
    #
    # Les deux valent mieux qu'un seul : l'amorce deplace une probabilite, le
    # rapprochement garantit le resultat.
    #
    # ⚠️ ELLE NE MONTRAIT QUE DES ORDRES — ET NOVA REPOND AUSSI A DES QUESTIONS.
    #
    # Huit exemples, huit commandes ou demandes sur l'utilisateur. Pas une
    # seule question de connaissance. Whisper IMITE ce qu'on lui montre : on
    # lui avait donc appris que les phrases attendues ici sont des ordres, et
    # une question de culture generale arrivait hors registre.
    #
    # Releve en conditions reelles, la MEME question posee deux fois :
    #
    #     dit      « Nova, qu'est-ce qu'un trou noir ? »
    #     entendu  « Nova, qu'est-ce qu'en trois noirs ? »
    #     entendu  « Nova, qu'est-ce qu'apprends moi ? »  -> « qu'est-ce qu'un pro-noir »
    #
    # Le mot massacre change a chaque fois, mais la CHARNIERE est toujours la
    # meme : « qu'est-ce qu'un ». C'est la construction interrogative la plus
    # courante du francais parle, et elle ne figurait nulle part ici — l'amorce
    # ne contenait que « quelle heure est-il », « que sais-tu », « quel jour ».
    #
    # On ajoute donc la CONSTRUCTION, pas les mots. Ecrire « trou noir » dans
    # l'amorce corrigerait les trous noirs et rien d'autre ; montrer trois
    # « qu'est-ce qu'un X » de domaines differents apprend a Whisper que cette
    # charniere est attendue, quel que soit le X qui suit.
    whisper_amorce_dictee: str = (
        "Nova, quelle heure est-il ? Nova, que sais-tu de moi ? "
        "Nova, ouvre un nouveau projet. Nova, resume-moi ce document. "
        "Nova, monte le son a 80 %. Nova, baisse le son. Nova, ferme Discord. "
        "Quel jour sommes-nous aujourd'hui ? "
        "Nova, qu'est-ce qu'un trou noir ? Nova, qu'est-ce qu'une eclipse ? "
        "Nova, qu'est-ce que la relativite ? Nova, explique-moi la photosynthese. "
        "Nova, pourquoi le ciel est-il bleu ?"
    )
    # ── Synthese vocale locale ────────────────────────────────────────────
    #
    # `ff_siwis` n'a pas ete choisie sur une fiche technique mais A L'OREILLE,
    # apres ecoute comparee de sept voix (`scripts/essayer-voix-locales.sh`) :
    # c'est celle qui se rapprochait le plus de la voix ElevenLabs d'origine.
    #
    # Le detail qui rend cette comparaison lisible : Kokoro et Piper proposent
    # tous deux une voix tiree du corpus `siwis`. Meme locutrice, meme
    # materiau, seul le moteur change — l'ecart entendu ne pouvait donc venir
    # que de la synthese, et pas du timbre de depart.
    #
    # ── DEUX MOTEURS, ET LE SECOND EST CELUI DE L'AVENIR ──────────────────
    #
    # `kokoro`  generaliste : 350 Mo + torch, ~1 Go resident, x0,25 temps reel
    # `piper`   une seule voix : 60 Mo sur onnx, sans torch, ~x0,02
    #
    # Sur 8 Go deja occupes par un modele de langue de 3,3 Go, ce gigaoctet se
    # paie deux fois — en memoire, puis en lenteur de tout le reste.
    #
    # Piper est aussi le format d'un modele AFFINE : une voix entrainee sur
    # mesure arrive sous forme de `.onnx`, et `voix_modele` accepte un chemin.
    # Le jour ou le clone existe, il n'y a rien a rebrancher :
    #
    #     NOVA_VOIX_MOTEUR=piper
    #     NOVA_VOIX_MODELE_PIPER=/chemin/vers/nova.onnx
    #
    # Le defaut reste `kokoro` : c'est ce qui est installe et ecoute
    # aujourd'hui, et un defaut ne doit pas changer sous les pieds de qui met
    # simplement le projet a jour.
    voix_moteur: str = "kokoro"
    # ⚠️ UN REGLAGE PAR MOTEUR, ET CE N'EST PAS DE LA SYMETRIE GRATUITE.
    #
    # Il n'y en avait qu'un au depart, lu par les deux moteurs. Passer de
    # `piper` a `kokoro` laissait donc un chemin `.onnx` comme NOM de voix
    # Kokoro — une valeur qui n'a aucun sens pour lui, dans un reglage qu'on
    # venait de renseigner exprès. Changer de moteur demandait de se souvenir
    # de changer aussi le modele, sans que rien ne le rappelle.
    #
    # Avec deux reglages, les deux voix restent configurees en permanence et
    # `NOVA_VOIX_MOTEUR` suffit a basculer. C'est ce qui permet de comparer a
    # l'oreille — la seule facon dont une voix a jamais ete choisie ici.
    voix_modele: str = "ff_siwis"          # nom de voix Kokoro
    voix_modele_piper: str = ""            # chemin .onnx, ou nom du catalogue
    # Code de langue de Kokoro : « f » pour le francais. Il choisit le
    # phonemiseur, pas seulement l'accent — se tromper ici ne donne pas une
    # voix a l'accent etranger, ca donne du charabia.
    voix_langue: str = "f"
    # Retire l'inspiration en tete et en queue de chaque enonce, puis fond les
    # extremites. Un modele affine reproduit ce que son corpus contenait, et le
    # corpus contenait un souffle avant chaque phrase : ce n'est pas un defaut
    # du moteur, c'est un motif appris — donc aucun reglage de synthese ne
    # l'enleve. Voir `voice/synthese.py`.
    #
    # Reglable pour une seule raison : pouvoir comparer a l'oreille avec et
    # sans, comme on a compare les voix.
    voix_nettoyer_bords: bool = True
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
        # ── DISTANCE COSINUS MAXIMALE POUR QU'UN EXTRAIT SOIT JUGE PERTINENT
        #
        # 0 = identique, 1 = sans rapport. Une recherche vectorielle rend
        # TOUJOURS ses plus proches voisins : sans ce seuil, une question de
        # culture generale reçoit les extraits les moins mauvais du corpus,
        # et le prompt double de taille pour rien.
        #
        # 0,55 est un point de depart, pas une verite : le bon seuil depend
        # du modele d'embeddings et de TES documents. Les distances sont
        # journalisees a chaque recherche — regarde-les, et ajuste.
        #
        # Trop bas : Nova cesse d'utiliser tes documents quand il le faudrait.
        # Trop haut : on revient au defaut d'origine.
        self.distance_max: float = data["recherche"].get("distance_max", 0.55)
        # Vectoriser meme quand aucun mot de la question ne figure dans les
        # documents. Coute ~2 s par question sur l'iMac M1 (bge-m3 est un
        # SECOND modele de 1,2 Go, qui decharge celui de conversation).
        # Faux par defaut : on paie le sens quand il y a une chance qu'il
        # serve, pas systematiquement.
        self.semantique_toujours: bool = data["recherche"].get(
            "recherche_semantique_toujours", False
        )
        self.chunk_size: int = data["decoupage"]["taille"]
        self.chunk_overlap: int = data["decoupage"]["recouvrement"]
        self.faits_max: int = data["memoire"]["faits_max_dans_prompt"]
        # Valeur par defaut si le fichier vient d'une version anterieure : une
        # config plus ancienne ne doit jamais empecher Nova de demarrer.
        self.faits_budget: int = data["memoire"].get("budget_caracteres_prompt", 1200)
        # Budget du CONTEXTE conversationnel, en caracteres. Meme discipline
        # que la memoire et les documents : borner le nombre de tours ne borne
        # pas leur taille, et chaque caractere du passe se paie sur chaque
        # question a venir (risque R13).
        self.historique_budget: int = data["memoire"].get("budget_caracteres_historique", 1200)


@lru_cache
def get_settings() -> Settings:
    """Instance unique, mise en cache : la config ne se relit pas a chaque appel."""
    return Settings()


@lru_cache
def get_tuning() -> Tuning:
    path = ROOT / "config" / "nova.toml"
    with path.open("rb") as fh:
        return Tuning(tomllib.load(fh))
