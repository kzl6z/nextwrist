# 02 — Technologies : choix, avantages, inconvénients

Format identique pour chaque brique : rôle · verdict · avantages · inconvénients ·
alternatives écartées. Quand une licence n'est pas OSI, c'est signalé.

---

## 1. Interface — LibreChat ou Open WebUI

**Rôle :** interface de conversation principale.

> **Avant tout :** c'est la décision **la moins importante** du projet. Elle est
> réversible en une journée, parce que la valeur vit dans Nova Core (Postgres +
> serveurs MCP), pas dans l'interface. Ne passe pas deux semaines à hésiter.

### Comparaison

| Critère | LibreChat | Open WebUI |
|---|---|---|
| Licence | **MIT**, propre | BSD-3 **modifiée** (clause de marque depuis 2025) — pas strictement OSI |
| Poids | Lourd (Mongo + Meilisearch + rag_api) | Léger, mono-conteneur possible |
| Prise en main | Dense (`librechat.yaml`) | Plus simple, tout par l'interface |
| Ollama | Via endpoint OpenAI-compatible | **Intégration native**, excellente |
| Outils | **MCP natif** | Outils/Fonctions **en Python** dans l'interface ; MCP via un pont |
| Agents | Framework d'agents intégré | Plus limité |
| RAG | Service `rag_api` séparé | Intégré, très simple |
| Recherche web | À brancher | Intégrée |
| Voix | STT/TTS configurables sur services locaux | Idem |

### Verdict : **LibreChat**, pour trois raisons

1. **MCP natif.** C'est ta frontière de portabilité (doc 01). Tes outils écrits une
   fois fonctionneront ailleurs. Open WebUI y accède, mais par un pont supplémentaire.
2. **Licence MIT franche.** Ton critère « open source dès que possible » est explicite ;
   la clause de marque d'Open WebUI n'est pas bloquante pour un usage personnel, mais
   elle est une entorse.
3. **Le framework d'agents** te porte jusqu'à la V0.8 sans écrire d'orchestrateur.

### L'argument honnête en faveur d'Open WebUI

Il est réel : **ses outils s'écrivent en Python directement dans l'interface**, sans
serveur séparé ni protocole. Pour un débutant qui a choisi Python, c'est une boucle
d'apprentissage beaucoup plus courte — on écrit une fonction, elle est utilisable
immédiatement. Il est aussi nettement plus léger, ce qui compte sur une machine
modeste.

Si après une semaine `librechat.yaml` te décourage, **bascule sans état d'âme**. Tu
ne perdras rien : ta mémoire, tes documents et tes outils MCP sont en dehors.

### Détail de LibreChat

**Avantages**
- Multi-modèles : Ollama et n'importe quel service OpenAI-compatible cohabitent.
- Couvre déjà énormément de ton cahier des charges sans écrire une ligne : upload de
  fichiers, RAG intégré (service `rag_api`), agents avec outils, support **MCP**,
  voix (STT/TTS) branchable sur des services locaux, multi-utilisateurs, PWA mobile.
- Très actif, documentation sérieuse, `docker compose` officiel.
- MIT : aucune contrainte de licence sur ce que tu construis autour.

**Inconvénients**
- **Lourd** : MongoDB + Meilisearch + rag_api + l'app. ~2-3 Go de RAM à vide. Pour un
  usage mono-utilisateur c'est surdimensionné, mais c'est le prix du « tout intégré ».
- Configuration par `librechat.yaml` : puissante mais dense. Compter une soirée pour
  s'y retrouver la première fois.
- Rythme de sortie rapide → les mises à jour cassent parfois la config. **Épingle une
  version précise** (`:v0.x.y`), ne reste pas sur `:latest`.
- Fonctionnalités inégales selon les versions (la mémoire native notamment). Vérifie
  le CHANGELOG de la version que tu installes plutôt que de te fier à un tutoriel.

**Autres alternatives**
- *AnythingLLM* : RAG excellent clé en main, mais moins ouvert comme socle d'agent.
- *Une interface écrite par toi* : tentant, et c'est un piège. Tu passerais six mois
  sur du CSS au lieu de construire la mémoire. À reconsidérer seulement en V2.0, et
  seulement pour une vue que rien d'existant ne couvre (la navigation du graphe, par
  exemple).

> **Rappel :** LibreChat reste remplaçable par construction. Si tu la remplaces un
> jour, tu ne perds ni ta mémoire, ni tes projets, ni tes documents.

---

## 2. Moteur d'inférence — Ollama ✅ (ton choix, confirmé pour démarrer)

**Licence :** MIT.

**Avantages**
- Le plus simple qui existe : `ollama pull qwen3:14b` et c'est fini. Pour un
  débutant, il n'y a pas de débat.
- API OpenAI-compatible → pas d'enfermement.
- Gère automatiquement la mémoire, le déchargement, le partage CPU/GPU.
- Multi-plateforme (Linux, macOS, Windows), y compris Apple Silicon.

**Inconvénients**
- **Moins performant que vLLM** en requêtes simultanées. Sans importance à 1
  utilisateur, bloquant à 20.
- Couche d'abstraction : moins de contrôle fin sur les paramètres que llama.cpp brut.
- Le rechargement de modèle est coûteux. Si tu alternes texte ↔ vision ↔ embeddings
  sur une machine juste dimensionnée, tu passeras du temps à attendre. Parades :
  `OLLAMA_KEEP_ALIVE=30m`, et un modèle d'embeddings petit qui reste résident.

**Alternatives**
- *llama.cpp (llama-server)* : plus rapide, plus paramétrable, plus austère.
- *vLLM* : la référence en débit, mais GPU obligatoire et configuration exigeante.
- *LM Studio* : agréable mais l'application n'est pas open source.

**Verdict :** Ollama pour la V0.1 à V1.0. Passe à vLLM/llama.cpp seulement si tu
mesures un problème de vitesse — pas par principe.

---

## 3. Le modèle — la décision la plus dépendante de ton matériel

C'est le seul choix que je ne peux pas trancher sans connaître ta machine. Voici la
grille de décision complète ; trouve ta ligne.

| Ton matériel | Cerveau principal | Vision | Ressenti |
|---|---|---|---|
| CPU seul, 16 Go RAM | `qwen3:4b` | `gemma3:4b` | 5-15 tok/s. Utilisable, limité en raisonnement. |
| CPU seul, 32 Go+ RAM | `qwen3:30b-a3b` (MoE) | `gemma3:12b` | ⭐ Le meilleur rapport qualité/CPU : 30 Md de paramètres, 3 Md actifs. Tourne bien sans GPU. |
| GPU 8-12 Go VRAM | `qwen3:14b` (Q4) | `gemma3:12b` | 30-50 tok/s. Très confortable. |
| GPU 16 Go VRAM | `qwen3:30b-a3b` (Q4) | `qwen3-vl:8b` | ⭐ Excellent équilibre. |
| GPU 24 Go+ (3090/4090) | `qwen3:32b` ou `gpt-oss:20b` | `gemma3:27b` | Qualité proche du haut de gamme commercial. |
| Mac Apple Silicon 32 Go+ | `qwen3:30b-a3b` | `gemma3:12b` | ⭐ La mémoire unifiée est idéale pour les MoE. |

### Pourquoi Qwen 3 comme choix par défaut

**Avantages**
- **Excellent en français** — c'est décisif ici, beaucoup de modèles ouverts sont
  nettement plus faibles hors anglais.
- Très bon en appel d'outils (*function calling*) : indispensable, c'est la mécanique
  sur laquelle repose toute la couche MCP. Un modèle qui appelle mal les outils rend
  Nova inutilisable, quelle que soit sa culture générale.
- Gamme complète 0,6 Md → 235 Md : tu changes de taille sans changer de famille, donc
  sans réécrire tes prompts.
- Licence Apache 2.0 (usage commercial libre, aucune clause piège).
- Longue fenêtre de contexte (32k natif, extensible) — précieux pour le RAG.
- La variante **MoE `30b-a3b`** est la vraie bonne surprise : qualité d'un gros
  modèle, coût de calcul d'un petit.

**Inconvénients**
- Les variantes « thinking » sont bavardes et lentes ; pour l'assistant du quotidien
  prends la variante *instruct*, garde le raisonnement pour les tâches d'analyse.
- Culture générale francophone un cran en dessous des meilleurs modèles commerciaux —
  compensé, justement, par ta base documentaire.

**Alternatives sérieuses**
- *Llama 3.3 70B* : très bon, mais exige 40 Go+ de VRAM, et sa licence Meta impose
  des conditions (mention « Built with Llama », seuil d'utilisateurs). Peu adapté à
  ton cas.
- *Mistral Small 3.x (24B)* : Apache 2.0, français natif excellent (équipe
  française), très bon compromis. **C'est le concurrent le plus légitime de Qwen 3
  pour toi** — si le français te semble bancal avec Qwen, teste-le.
- *Gemma 3* : multimodal nativement (texte+image dans un seul modèle) et très bon en
  français, mais licence Google avec clauses d'usage. Je le recommande **pour la
  vision uniquement**, où il excelle.
- *GPT-OSS 20B/120B* : Apache 2.0, très fort en raisonnement et en outils, plus
  faible en français.
- *Kimi K2 (Moonshot)* : tu le cites, et il le mérite — c'est l'un des meilleurs
  modèles ouverts pour l'appel d'outils et les tâches agentiques. **Mais il est hors
  de portée en local** : architecture MoE de très grande taille, plusieurs centaines
  de Go même quantifiée. Il n'existe pas de machine personnelle capable de le faire
  tourner. Le seul accès est une API — ce qui contredit ta contrainte principale. À
  garder en tête uniquement si tu retiens la doctrine « pragmatique » (voir
  [`06-critique-de-la-vision.md`](06-critique-de-la-vision.md#les-trois-questions-que-je-te-renvoie-avant-de-valider)).
  Moonshot publie aussi des modèles nettement plus petits, dont des modèles de
  vision : vérifie ce qui est disponible dans Ollama au moment où tu installes.

**Verdict :** Qwen 3 comme cerveau, Gemma 3 comme œil. Deux familles, deux rôles.
Et surtout : **teste 3 modèles sur tes vraies questions** avant de figer. Les
classements publics ne prédisent pas ton usage.

---

## 4. Embeddings — `bge-m3`

**Rôle :** transformer un texte en vecteur pour la recherche sémantique. Licence MIT.

**Avantages**
- **Multilingue de premier plan, dont le français** — critère décisif. Un modèle
  d'embeddings anglophone sur un corpus français dégrade la recherche de façon
  spectaculaire, et le symptôme est sournois : Nova « ne trouve pas » sans jamais
  dire pourquoi.
- 8192 tokens de contexte : accepte de gros morceaux sans découpage agressif.
- Disponible dans Ollama, léger (~1,2 Go), reste chargé en permanence sans gêner.

**Inconvénients**
- Plus lourd que `nomic-embed-text` ou `all-minilm`.
- 1024 dimensions → index un peu plus gros (sans importance à ton échelle).

**Alternatives :** `nomic-embed-text` (léger, anglais surtout), `qwen3-embedding`
(très bon, plus récent), `multilingual-e5-large`.

> ⚠️ **Règle absolue :** changer de modèle d'embeddings oblige à **tout re-vectoriser**.
> Choisis-le bien maintenant, note-le dans ta config, et n'y touche plus sans raison.

---

## 5. Base de données — PostgreSQL + pgvector

**Licence :** PostgreSQL (permissive) / pgvector : PostgreSQL License.

**Avantages**
- Une seule base pour le relationnel **et** le vectoriel → une seule sauvegarde, une
  seule source de vérité, pas de synchronisation à maintenir.
- Déjà requis par le service RAG de LibreChat : brique gratuite dans ton budget de
  complexité.
- Fiabilité éprouvée depuis 30 ans, tes données seront lisibles dans 20 ans.
- SQL : compétence réutilisable toute ta vie, contrairement à une API propriétaire.

**Inconvénients**
- Recherche vectorielle un peu moins rapide qu'une base spécialisée à très grande
  échelle (des millions de vecteurs — hors de portée pour toi).
- Il faut choisir le bon index (HNSW) et penser à le créer ; oubli fréquent chez les
  débutants, et la recherche devient lente sans erreur visible.

**Alternatives :** *Qdrant* (Apache 2.0, excellent, mais c'est **un système de plus**
à gérer et sauvegarder), *Chroma* (simple mais fragile en production), *SQLite +
sqlite-vec* (séduisant pour la simplicité, insuffisant pour l'accès concurrent).

**Verdict :** Postgres. Le gain de simplicité d'avoir *une* base surpasse largement
le gain de performance d'une base dédiée à ton échelle.

---

## 6. Reconnaissance vocale (STT) — faster-whisper via Speaches

**Licence :** modèle Whisper MIT, faster-whisper MIT.

**Avantages**
- Whisper `large-v3` est l'état de l'art en français, y compris en conditions
  bruitées. `large-v3-turbo` : ~8× plus rapide pour une qualité quasi identique.
- 100 % local. Speaches expose une API **OpenAI-compatible** → LibreChat s'y branche
  par simple configuration, sans code.
- Fonctionne sur CPU (`small`/`base`) si tu n'as pas de GPU.

**Inconvénients**
- `large-v3` sur CPU : lent (plusieurs secondes par phrase). Prévois `small` ou un GPU.
- Consomme de la VRAM en concurrence avec ton modèle principal — planifie l'allocation.
- Hallucine sur les silences (Whisper invente du texte sur du blanc). Corrigé par une
  détection d'activité vocale (VAD) en amont.

**Alternatives :** *whisper.cpp* (très portable), *WhisperX* (ajoute l'identification
des locuteurs), *Vosk* (léger, temps réel, moins précis).

---

## 7. Synthèse vocale (TTS) — Kokoro, puis Piper en secours

**Kokoro-82M** — licence Apache 2.0.

**Avantages :** qualité remarquable pour 82 M de paramètres, rapide même sur CPU,
voix françaises disponibles, `Kokoro-FastAPI` fournit une API OpenAI-compatible.

**Inconvénients :** choix de voix limité, pas de clonage vocal, projet jeune.

**Piper** — MIT. Extrêmement rapide et léger (tourne sur un Raspberry Pi), beaucoup
de voix françaises, mais rendu plus robotique. **C'est le bon choix pour un satellite
vocal embarqué.**

**Alternative à connaître :** *XTTS-v2* (Coqui) clone une voix à partir de 6 secondes
d'audio — techniquement impressionnant, mais **licence CPML non commerciale** : à
n'utiliser que pour un usage strictement personnel, et à ne jamais intégrer dans
quelque chose que tu diffuserais.

**Verdict :** Kokoro pour Nova sur ordinateur, Piper pour l'embarqué.

---

## 8. Analyse de documents — Docling

**Licence :** MIT (IBM).

**Avantages :** convertit PDF, DOCX, PPTX, HTML en Markdown structuré en préservant
**les tableaux, les titres et la mise en page** — ce que la plupart des extracteurs
détruisent, et c'est précisément ce qui fait la qualité d'un RAG. OCR intégré pour
les scans. 100 % local.

**Inconvénients :** lourd (modèles de mise en page à télécharger), lent sur les gros
PDF, jeune donc en évolution rapide.

**Alternatives :** *Unstructured* (très complet, licence mixte à surveiller),
*PyMuPDF* (rapide, AGPL, perd la structure), *Apache Tika* (robuste, sans finesse).

**Note pratique :** LibreChat sait déjà ingérer des fichiers via son `rag_api`.
Commence par ça en V0.1. Docling arrive en V0.2 pour les documents complexes, quand
tu constateras les limites de l'ingestion basique — pas avant.

---

## 9. Recherche web — SearXNG

**Licence :** AGPL-3.0.

**Avantages :** méta-moteur auto-hébergé qui agrège Google/Bing/DuckDuckGo **sans clé
API, sans traçage, sans coût**. Sortie JSON directement exploitable par un outil MCP.

**Inconvénients :** se fait parfois bloquer par les moteurs (limitation de débit) ;
il faut ajuster la liste des sources. Qualité inférieure à une API payante comme
Brave ou Tavily. C'est le seul endroit de l'architecture où du trafic sort vers
l'extérieur — assume-le consciemment.

**Alternative :** *Brave Search API* (gratuite jusqu'à 2000 requêtes/mois, meilleure
qualité, mais tes requêtes partent chez un tiers).

---

## 10. Protocole d'outils — MCP

**Licence :** spécification ouverte, SDK MIT.

**Avantages :** standard adopté largement en 2025 ; supporté par LibreChat, Claude,
et de plus en plus de clients. Écosystème déjà fourni de serveurs prêts à l'emploi.
SDK Python très simple (un décorateur par outil). **Tes outils te survivent aux
changements d'interface** — c'est l'argument principal.

**Inconvénients :** encore jeune, la spécification bouge. La qualité des serveurs
tiers est inégale (n'en installe aucun sans lire son code : un serveur MCP a accès à
ta machine). Le débogage est moins confortable qu'une simple fonction Python.

**Verdict :** c'est le bon pari architectural. Il n'y a pas de meilleure option
aujourd'hui pour rendre des capacités portables entre interfaces.

---

## 11. Langage — Python ✅ (ton choix, confirmé)

**Avantages**
- Écosystème IA sans équivalent : SDK MCP, clients Ollama, Docling, traitement de
  texte — tout est en Python d'abord.
- Lisible : tu pourras relire ton code de 2026 en 2029, ce qui compte plus que tu ne
  le crois sur un projet de plusieurs années.
- Compétence transférable bien au-delà de Nova.

**Inconvénients**
- Lent à l'exécution — sans importance ici : ton code ne fait qu'orchestrer, tout le
  calcul lourd est dans Ollama et Postgres.
- La gestion des environnements et des dépendances est le cauchemar classique du
  débutant. **Parade : `uv`** (gestionnaire moderne, rapide, un seul outil) et un
  conteneur par service. Ne fais jamais de `pip install` global.

**Bibliothèques du projet, et rien de plus au départ**

| Besoin | Choix | Pourquoi pas autre chose |
|---|---|---|
| Serveurs MCP | SDK MCP officiel | Un décorateur par outil, ~80 lignes/serveur |
| API HTTP | FastAPI | Standard, documentation automatique |
| Postgres | psycopg | Direct, du vrai SQL — tu apprends SQL, pas un ORM |
| Appels HTTP | httpx | — |
| Tâches planifiées | `cron` système | Pas de Celery : tu n'as pas ce problème |

**Ce qu'on n'utilise pas, et c'est délibéré :** ni ORM (SQLAlchemy) — écris du SQL,
c'est plus simple et c'est une compétence durable ; ni LangChain/LlamaIndex — voir
la section « déconseillé ».

---

## 12. Socle — Docker Compose, Caddy, Tailscale, restic

| Brique | Avantages | Inconvénients |
|---|---|---|
| **Docker Compose** (Apache 2.0) | Tout le système en un fichier ; installation reproductible ; isolation. Indispensable ici. | Une couche de plus à comprendre ; surcoût GPU sous Windows ; les volumes sont le piège n°1 des débutants (données perdues par un `down -v`). |
| **Caddy** (Apache 2.0) | HTTPS automatique, configuration de 3 lignes. | Moins de documentation que Nginx. |
| **Tailscale** (client BSD) | Accès à Nova depuis ton téléphone n'importe où, **sans ouvrir un port sur Internet**. Chiffré de bout en bout. | Le serveur de coordination est un service tiers (les données ne transitent pas par lui). Alternative 100 % libre : *Headscale*. |
| **restic** (BSD-2) | Sauvegardes chiffrées, incrémentales, déduplication, restauration vérifiable. | Ligne de commande uniquement. |

> **La règle la plus importante de tout ce document :** une sauvegarde jamais
> restaurée n'est pas une sauvegarde. Teste une restauration complète le premier
> mois, puis tous les 6 mois. La mémoire de Nova est la seule chose que tu ne peux
> pas re-télécharger.

---

## 13. Ce que je te déconseille explicitement pour l'instant

| Techno | Pourquoi pas maintenant |
|---|---|
| **LangChain / LlamaIndex** | Couches d'abstraction énormes, API instables. Tu apprendrais LangChain au lieu d'apprendre ton problème. Les SDK MCP + `requests` suffisent largement. À reconsidérer si un jour tu écris des chaînes vraiment complexes. |
| **n8n** | Excellent produit, mais licence *fair-code* non OSI (restrictions d'usage). Contredit ton critère open source. Équivalents libres : *Windmill* (AGPL), ou simplement `cron` + Python. |
| **Kubernetes** | Aucune justification pour une machine. Compose suffit jusqu'à ~15 services. |
| **Affiner un modèle (*fine-tuning*)** | Le réflexe du débutant, et l'erreur classique : coûteux, complexe, et **la mémoire + le RAG résolvent 95 % de ce que tu crois vouloir en affinant**. Personnaliser Nova = un bon prompt système + une bonne mémoire. Pas de fine-tuning avant la V1.0, si jamais. |
| **Un framework multi-agents** (CrewAI, AutoGen…) | Séduisant, mais multiplie les modes de panne. Un seul agent bien outillé bat cinq agents mal coordonnés. |
