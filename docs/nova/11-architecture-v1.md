# 11 — Architecture logicielle de la V1

> Ce document décrit **ce qui est construit maintenant** : l'arborescence, le rôle de
> chaque fichier, les dépendances, et les règles de code à tenir pendant des années.

---

## 1. Une amélioration par rapport au plan initial

Tu m'as demandé de proposer mieux quand je vois mieux. C'est le cas ici, et c'est la
décision la plus importante de la V1.

**Le plan initial** était : l'interface (LibreChat) parle à Ollama, et Nova ajoute des
capacités par des serveurs MCP que l'interface appelle.

**Le problème :** l'orchestration — décider quoi se rappeler, quoi chercher, quoi
injecter — vivrait alors **dans l'interface**. Or c'est précisément la partie qu'on a
déclarée jetable. On mettrait l'intelligence dans la pièce remplaçable, et on
dépendrait de la façon dont LibreChat décide d'appeler les outils.

**Ce que je propose : Nova Core se présente lui-même comme un modèle.**

```
Interface (Open WebUI, LibreChat, terminal, téléphone…)
        │  POST /v1/chat/completions        ← API OpenAI standard
        ▼
   ╔══════════════════════════════════════════════╗
   ║  NOVA CORE  (Python)                         ║
   ║  1. charge les faits te concernant           ║
   ║  2. cherche dans tes documents               ║
   ║  3. assemble le contexte                     ║
   ║  4. appelle Ollama                           ║
   ║  5. journalise l'échange                     ║
   ╚══════════════════════════════════════════════╝
        │  POST /v1/chat/completions
        ▼
      Ollama  (Qwen 3)
```

L'interface croit parler à un modèle nommé `nova`. En réalité elle parle à ton code.

**Pourquoi c'est nettement meilleur :**

| | Bénéfice |
|---|---|
| **Contrôle** | L'orchestration est en Python, chez toi, lisible et testable — pas dans la configuration YAML d'un produit tiers. |
| **Portabilité** | *N'importe quelle* interface compatible OpenAI marche instantanément. Changer d'interface devient une opération de 10 minutes, pas un projet. |
| **Apprentissage** | Tu vois et modifies exactement ce qui entre dans le prompt. C'est là qu'on apprend comment marche réellement un assistant. |
| **Testabilité** | On peut tester l'assemblage du contexte sans lancer aucune interface. |
| **Zéro enfermement** | Le standard OpenAI est le seul qui ne bougera pas. |

**Ce qu'on perd :** le modèle ne choisit pas encore *quand* chercher — c'est notre
code qui décide. C'est volontaire pour la V1 : déterministe, débogable, prévisible.
L'appel d'outils par le modèle (via MCP) s'ajoutera en V0.3 **par-dessus** cette base,
sans rien casser.

### Conséquence : le choix de l'interface devient secondaire → **Open WebUI**

Comme l'intelligence est dans Nova Core, le critère « MCP natif » qui faisait pencher
pour LibreChat ne tranche plus rien. Restent la légèreté et la simplicité, et là
Open WebUI gagne nettement : un conteneur, configuration par l'interface, CSS
personnalisable, excellent avec un point d'accès OpenAI-compatible.

*Réserve honnête :* sa licence est un BSD-3 modifié avec clause de marque — pas
strictement OSI. Sans conséquence pour un usage personnel, mais je te le signale
puisque l'open source est un de tes critères. **Et si un jour elle te gêne : tu
changes d'interface en 10 minutes, sans rien perdre.** C'est tout l'intérêt de
l'architecture.

---

## 2. Arborescence

```
nova/
├── pyproject.toml           dépendances + configuration des outils
├── docker-compose.yml       Postgres + Nova Core + Open WebUI
├── Dockerfile               image de Nova Core
├── .env.example             modèle de configuration (jamais de secret commité)
├── Makefile                 raccourcis : make up, make migrate, make test
├── README.md                démarrage en 5 minutes
│
├── config/
│   ├── nova.toml            réglages métier (seuils, tailles de morceaux)
│   └── prompts/
│       ├── identity.md      QUI est Nova — le fichier le plus important du projet
│       ├── mode_critique.md le prompt adversarial (critique n°2)
│       └── consolidation.md réservé V0.3
│
├── migrations/              schéma SQL, numéroté, jamais modifié après application
│   ├── 001_socle.sql        faits, conversations, messages
│   └── 002_documents.sql    documents, morceaux, index vectoriel + plein texte
│
├── src/nova/
│   ├── settings.py          configuration typée (pydantic-settings)
│   ├── logging_setup.py     journalisation lisible
│   ├── db.py                pool de connexions + exécution des migrations
│   ├── prompts.py           chargement des prompts depuis config/prompts/
│   │
│   ├── llm/
│   │   ├── client.py        client OpenAI-compatible → Ollama (avec flux)
│   │   └── embeddings.py    vectorisation des textes
│   │
│   ├── memory/
│   │   ├── models.py        les types (Fact, Chunk, SearchHit…)
│   │   ├── facts.py         mémoire sémantique — CRUD + rendu pour le prompt
│   │   └── conversations.py journal des échanges (la mémoire brute)
│   │
│   ├── documents/
│   │   ├── chunking.py      découpage — fonctions pures, donc testables
│   │   ├── ranking.py       fusion RRF — n'importe rien du tout (voir §4)
│   │   ├── ingest.py        fichier → morceaux → vecteurs → base
│   │   └── search.py        recherche hybride (vectorielle + plein texte)
│   │
│   ├── orchestrator.py      ★ le cœur : assemble le contexte, appelle le modèle
│   │
│   ├── api/
│   │   ├── app.py           application FastAPI
│   │   ├── openai_compat.py la passerelle /v1/chat/completions
│   │   └── admin.py         endpoints internes (faits, ingestion, recherche)
│   │
│   └── cli.py               commandes : migrate, ingest, ask, facts, search
│
├── scripts/
│   └── fake_ollama.py       faux moteur compatible OpenAI — teste toute la
│                            chaîne sans GPU ni modèle téléchargé
├── tests/                   pytest — fonctions pures + intégration
└── ui/
    └── orb.html             la sphère, composant autonome sans dépendance
```

### Rôle de chaque dossier

| Dossier | Responsabilité | Règle |
|---|---|---|
| `config/` | Ce qui change **sans** toucher au code | Versionné. Aucun secret. |
| `migrations/` | Le schéma, l'actif le plus durable | **Un fichier appliqué ne se modifie jamais** — on en ajoute un nouveau. |
| `src/nova/llm/` | Tout ce qui parle à un modèle | Seul endroit qui connaît Ollama. Changer de moteur = ne toucher qu'ici. |
| `src/nova/memory/` | Ce que Nova sait de toi | Ne connaît pas le LLM. |
| `src/nova/documents/` | Ce que Nova a lu | Ne connaît pas le LLM sauf pour vectoriser. |
| `src/nova/api/` | Les portes d'entrée | **Aucune logique métier** — uniquement traduire HTTP ↔ métier. |
| `orchestrator.py` | La décision | Le seul module qui a le droit de connaître tous les autres. |
| `tests/` | Le filet | Priorité aux fonctions pures. |
| `ui/` | Le visage | Autonome, remplaçable. |

**La règle de dépendance, à ne jamais enfreindre :**

```
api  →  orchestrator  →  memory · documents · llm  →  db
```

Les flèches ne remontent jamais. `memory` n'importe pas `orchestrator`, `db`
n'importe personne. C'est ce qui permet de remplacer une couche sans toucher aux
autres — et c'est ce qui rend le projet tenable sur plusieurs années.

---

## 3. Dépendances, et pourquoi chacune

| Paquet | Rôle | Pourquoi celui-là |
|---|---|---|
| `fastapi` | API HTTP | Standard, documentation automatique, validation intégrée |
| `uvicorn` | Serveur | Le serveur de référence pour FastAPI |
| `pydantic-settings` | Configuration typée | Une faute de frappe dans `.env` échoue au démarrage, pas en production |
| `psycopg[binary,pool]` | Postgres | Le pilote moderne. **Pas d'ORM** : tu écris du SQL, tu apprends SQL. |
| `pgvector` | Type vecteur | Adaptateur officiel pour psycopg |
| `httpx` | Client HTTP | Gère proprement le flux (streaming), indispensable ici |
| `typer` | CLI | Une fonction Python annotée devient une commande |
| `rich` | Affichage terminal | Rend la CLI lisible, donc utilisable |
| `pytest` | Tests | Standard |
| `ruff` | Lint + format | Un seul outil, très rapide |

**Ce qu'on n'installe pas, délibérément :** LangChain / LlamaIndex (couches
d'abstraction énormes, API instables — on ferait l'apprentissage d'un framework au
lieu de celui du problème), SQLAlchemy (le SQL direct est plus simple et se
transfère), Celery (`cron` suffit).

Dix dépendances. C'est peu, et c'est voulu : chacune est une chose qui peut casser
dans deux ans.

---

## 4. Décisions techniques de la V1, et leurs raisons

### Synchrone plutôt qu'asynchrone
FastAPI exécute automatiquement les fonctions `def` (non `async`) dans un pool de
threads. Pour un usage personnel, le code synchrone est **beaucoup** plus simple à
lire et à déboguer, sans perte mesurable. On passerait à l'asynchrone si Nova devait
servir plusieurs dizaines d'utilisateurs — ce qui n'arrivera pas.

### SQL écrit à la main, pas d'ORM
Un ORM cache la requête. Or la requête *est* le sujet : c'est là que vivent la
recherche vectorielle, la fusion de classements, les filtres temporels. Et SQL est
une compétence qui vaudra encore quelque chose dans vingt ans.

### Recherche hybride dès le premier jour
La recherche vectorielle seule échoue sur les termes rares : un nom propre, une
référence produit, un identifiant. Le plein texte seul échoue sur les reformulations.
On lance les deux et on fusionne par **RRF** (*Reciprocal Rank Fusion*) :

```
score(document) = Σ  1 / (k + rang dans le classement i)
```

Simple, sans paramètre à régler, et régulièrement meilleur que des combinaisons
savantes. C'est le genre de choix qu'il faut faire **maintenant**, parce que le
rattraper plus tard signifie tout re-vectoriser.

### Le calcul isolé de toute infrastructure
`ranking.py` n'importe **rien** — ni base, ni réseau, ni configuration. La leçon
a été apprise en écrivant les tests : une fonction pure placée dans un module qui
importe la base de données n'est plus testable sans base de données. **La pureté
se perd au niveau du module, pas de la fonction.** Le calcul central de la
recherche se teste donc en quelques millisecondes.

### Nova journalise les conversations, même si l'interface le fait déjà
Redondant en apparence — essentiel en réalité : la mémoire durable doit vivre dans
Nova Core, pas dans l'interface remplaçable. C'est cette table qui alimentera la
consolidation nocturne en V0.3. Le jour où tu changes d'interface, tu ne perds rien.

### Le prompt d'identité est un fichier, pas une chaîne dans le code
`config/prompts/identity.md` sera modifié cinquante fois. Dans un fichier : versionné
par git, comparable d'une version à l'autre, modifiable sans redémarrer. C'est le
principal levier de personnalisation de Nova — bien avant le choix du modèle.

---

## 5. Bonnes pratiques à tenir

**Code**
1. Un module = une responsabilité, ~150 lignes maximum. Si ça déborde, on découpe.
2. Toutes les fonctions publiques sont annotées de types.
3. `ruff check` et `ruff format` passent avant chaque commit.
4. **Tu ne fusionnes pas du code que tu ne peux pas expliquer à voix haute.**

**Base de données**
5. Une migration appliquée ne se modifie **jamais**. On en ajoute une.
6. Aucune requête écrite par concaténation de chaînes — toujours des paramètres
   (`%s`). C'est la protection contre l'injection SQL, et c'est non négociable.

**Configuration**
7. Aucun secret dans git. `.env` est ignoré, `.env.example` est versionné.
8. Versions d'images épinglées dans `docker-compose.yml`.

**Données**
9. `data/` n'entre jamais dans git.
10. Sauvegarde avant toute migration.

**Méthode**
11. Une chose à la fois. Commit après chaque chose qui marche.
12. On écrit un test dès qu'un bug est corrigé — c'est le meilleur moment.
13. **L'ordre des commandes fait partie du produit.** `nova db migrate` passe
    avant `pytest` : lancer les tests sur une base sans schéma produit quatre
    échecs incompréhensibles au lieu d'un saut propre. Un outil qui échoue mal
    est un outil qu'on apprend à ignorer.
14. **Exécuter, pas relire.** La V1 a été validée bout en bout contre une vraie
    base Postgres et un faux moteur (`scripts/fake_ollama.py`). Deux défauts
    que la relecture n'avait pas vus sont apparus en trente secondes d'exécution :
    les citations effacées par le balisage de `rich`, et la réponse perdue quand
    le client se déconnecte en cours de flux. Aucun des deux ne levait d'erreur.
