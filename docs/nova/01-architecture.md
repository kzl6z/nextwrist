# 01 — Architecture complète

## 1. Vue d'ensemble : 6 couches

L'architecture est volontairement organisée en couches empilées, chacune ne parlant
qu'à sa voisine via une **interface standard**. C'est ce qui rend le système
évolutif : on remplace une couche sans toucher aux autres.

```
┌──────────────────────────────────────────────────────────────────────┐
│  COUCHE 1 — INTERFACES                                               │
│  LibreChat (web/mobile PWA)   ·   Satellite vocal   ·   CLI          │
└───────────────────────────┬──────────────────────────────────────────┘
                            │  HTTP (API OpenAI-compatible)
┌───────────────────────────▼──────────────────────────────────────────┐
│  COUCHE 2 — ORCHESTRATION                                            │
│  Agent Nova : décide quand répondre, quand chercher, quand se        │
│  souvenir, quel outil appeler. Assemble le contexte.                 │
│  (LibreChat Agents en V0.x → service dédié en V1.0)                  │
└──────┬──────────────────────────────────────┬────────────────────────┘
       │ API OpenAI                           │ protocole MCP
┌──────▼───────────────────────┐   ┌──────────▼───────────────────────┐
│  COUCHE 3 — INFÉRENCE        │   │  COUCHE 4 — CAPACITÉS (MCP)      │
│  Ollama .......... texte     │   │  nova-memory ..... souvenirs     │
│  Ollama .......... vision    │   │  nova-projects ... projets/but   │
│  Ollama .......... embeddings│   │  nova-search ..... web           │
│  Speaches ........ STT       │   │  nova-files ...... documents     │
│  Kokoro .......... TTS       │   │  nova-vision ..... caméra        │
└──────────────────────────────┘   └──────────┬───────────────────────┘
                                              │ SQL / FS
┌─────────────────────────────────────────────▼───────────────────────┐
│  COUCHE 5 — DONNÉES  ★ le cœur, la seule partie irremplaçable ★     │
│  PostgreSQL + pgvector ... faits, projets, résumés, vecteurs        │
│  Système de fichiers ..... documents sources (PDF, images, audio)   │
│  MongoDB ................. interne LibreChat (jetable)              │
│  Redis ................... cache et files d'attente                 │
└─────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│  COUCHE 6 — SOCLE                                                   │
│  Docker Compose · Caddy (HTTPS) · Tailscale (accès distant)         │
│  restic (sauvegardes chiffrées) · Prometheus/Grafana (plus tard)    │
└─────────────────────────────────────────────────────────────────────┘
```

### Pourquoi ce découpage précis

Deux frontières font tout le travail, et ce sont les deux seules choses à retenir :

**Frontière A — API OpenAI-compatible (couches 2 ↔ 3).** C'est le standard de fait de
l'industrie. Ollama l'expose (`/v1/chat/completions`). vLLM aussi, llama.cpp aussi,
LM Studio aussi. Résultat : le jour où Ollama devient trop lent pour toi, tu changes
une URL et tout continue de fonctionner. Tu n'es marié à rien.

**Frontière B — MCP, Model Context Protocol (couches 2 ↔ 4).** Standard ouvert
(Anthropic, 2024) devenu l'interface universelle entre un agent et ses outils.
LibreChat le supporte nativement, ainsi que la plupart des clients IA. Tes capacités
écrites en MCP fonctionneront dans LibreChat aujourd'hui, dans un autre client
demain, dans ton propre code après-demain. **C'est ce qui rend Nova portable.**

C'est aussi la réponse à ta question implicite « comment ne pas repartir de zéro plus
tard » : tu ne construis pas dans LibreChat, tu construis *à côté*, et LibreChat s'y
branche.

## 2. Couche 1 — Interfaces

| Interface | Quand | Rôle |
|---|---|---|
| LibreChat (navigateur) | V0.1 | Interface principale. Aussi installable en PWA sur téléphone. |
| Satellite vocal | V0.4 | Micro + haut-parleur dans une pièce. Mot de réveil « Nova ». |
| CLI / script | V0.5+ | Pour les automatisations et le débogage. |

LibreChat est explicitement traité comme **jetable** : c'est un visage, pas un
cerveau. Cette posture n'est pas une critique du produit (il est excellent), c'est
une assurance.

## 3. Couche 2 — Orchestration

C'est le chef d'orchestre. À chaque message il doit décider :

1. **Faut-il se souvenir ?** → interroger `nova-memory` et injecter les faits utiles
2. **Faut-il chercher ?** → dans les documents (RAG) ou sur le web
3. **Faut-il agir ?** → appeler un outil MCP
4. **Que garder ?** → écrire les nouveaux faits en mémoire

**Stratégie en deux temps, et c'est important :**

- **V0.1 → V0.5 : LibreChat Agents.** Configuration déclarative dans
  `librechat.yaml`, zéro code d'orchestration à écrire. Tu avances vite, tu apprends
  le domaine sans écrire de logique complexe. C'est le bon choix pour un débutant.
- **V1.0 : service `nova-orchestrator` dédié** (Python/FastAPI). Tu ne l'écriras que
  lorsque tu buteras sur une limite réelle de LibreChat — pas avant. À ce moment-là
  tu sauras exactement ce dont tu as besoin, parce que tu auras vécu le manque.

Ne pas écrire l'orchestrateur en V0.1 est une décision d'ingénierie, pas de la
paresse : on n'écrit pas d'abstraction avant d'avoir trois cas concrets.

## 4. Couche 3 — Inférence

| Service | Rôle | Sortie |
|---|---|---|
| Ollama (texte) | Le raisonnement de Nova | tokens |
| Ollama (vision) | Comprendre images et captures d'écran | tokens |
| Ollama (embeddings) | Transformer texte → vecteur pour la recherche | vecteur 1024d |
| Speaches (faster-whisper) | Voix → texte | texte |
| Kokoro-FastAPI | Texte → voix | audio |

Les trois usages d'Ollama tournent dans **un seul conteneur** ; Ollama charge et
décharge les modèles à la demande. Simple, mais attention : sur une machine modeste,
alterner entre un modèle de 20 Go et un modèle de vision provoque des rechargements
lents. La parade est dans `02-technologies-choix.md` (variable `OLLAMA_KEEP_ALIVE` et
choix de modèles compacts pour les tâches secondaires).

## 5. Couche 4 — Les capacités (serveurs MCP)

Chaque capacité de Nova = un petit serveur MCP autonome, en Python. C'est le travail
que **toi** tu écris, et c'est là que Nova devient Nova.

| Serveur | Outils exposés | Version |
|---|---|---|
| `nova-memory` | `remember(fait)`, `recall(sujet)`, `forget(id)` | V0.3 |
| `nova-projects` | `list_projects()`, `project_status(nom)`, `log_decision(...)` | V0.3 |
| `nova-files` | `search_docs(requête)`, `read_doc(id)`, `ingest(chemin)` | V0.2 |
| `nova-search` | `web_search(requête)`, `fetch_page(url)` | V0.4 |
| `nova-vision` | `capture_camera()`, `describe_image(chemin)` | V0.6 |
| `nova-system` | `schedule(tâche)`, `daily_brief()` | V0.7 |

Un serveur MCP simple, c'est ~80 lignes de Python. C'est délibérément petit :
chacun est indépendant, testable seul, et **une panne de l'un ne casse pas les
autres**. Tu peux en développer un pendant que Nova continue de tourner.

## 6. Couche 5 — Données : la conception de la mémoire

C'est la partie qui distingue réellement un Jarvis d'un chatbot, et donc la partie
qui mérite le plus de réflexion. Une seule grande base vectorielle où l'on jette tout
ne fonctionne pas : on ne peut pas chercher « quel est mon objectif de l'année »
avec la même mécanique que « que disait le PDF page 12 ».

**Quatre types de mémoire, quatre traitements différents :**

### Type 1 — Mémoire de travail
Le fil de conversation courant. Vit dans la fenêtre de contexte du modèle.
Durée de vie : la session. Stockage : MongoDB (LibreChat).

### Type 2 — Mémoire sémantique (les faits) ★ la plus importante
Faits stables et curés sur toi : préférences, contraintes, méthodes de travail,
personnes de ton entourage, objectifs.

```
Table facts
  id · catégorie · contenu · confiance · source · créé_le · révisé_le
```

Caractéristique clé : **elle est petite** (quelques centaines de lignes max) et donc
**injectée intégralement, ou presque, dans le prompt système** — pas cherchée
vectoriellement. C'est ce qui donne l'impression que Nova *te connaît* dès le premier
mot, sans avoir à fouiller. Les grands systèmes échouent souvent ici en noyant les
faits importants dans une recherche sémantique bruitée.

### Type 3 — Mémoire épisodique (l'histoire)
Ce qui s'est passé et quand. Pas les transcriptions brutes — des **résumés
structurés** produits chaque nuit par un travail de consolidation :

```
Table episodes
  id · date · résumé · sujets[] · décisions[] · projets_liés[] · embedding
```

Recherchée vectoriellement + filtrée par date. C'est ce qui permet « on avait parlé
de ça en mars, qu'est-ce qu'on avait décidé ? ».

### Type 4 — Base documentaire
Tes PDF, notes, contrats, articles. Découpés, vectorisés, recherchés par RAG.

```
Table documents      → fichier source, métadonnées
Table chunks         → morceau · embedding · référence page/section
```

### Le travail de consolidation nocturne

C'est **le mécanisme le plus « Jarvis »** de toute l'architecture, et il est
étonnamment simple à implémenter :

```
Chaque nuit à 3h :
  1. lire les conversations du jour
  2. demander au modèle : « résume, extrais les faits nouveaux,
     les décisions prises, les tâches implicites »
  3. écrire le résumé dans `episodes`
  4. proposer les faits nouveaux dans `facts` (statut : à valider)
  5. le matin, Nova te dit : « J'ai retenu 3 choses hier, tu confirmes ? »
```

Cette boucle — **dormir, digérer, valider** — est ce qui transforme un outil en
partenaire. Sans elle, la mémoire pourrit : elle se remplit d'approximations que
personne ne corrige. L'étape de validation humaine est non négociable ; c'est ce qui
maintient la qualité de la mémoire dans la durée.

### Pourquoi Postgres et pas une base vectorielle dédiée

Parce que tes données sont **relationnelles ET vectorielles**. « Les décisions du
projet X du dernier trimestre, classées par pertinence » c'est un `JOIN` + un filtre
`WHERE` + une similarité vectorielle. Avec Postgres + pgvector : une requête. Avec
une base vectorielle séparée : deux systèmes à synchroniser, et une classe entière de
bugs. Postgres tient sans difficulté jusqu'à ~1 M de vecteurs, tu n'y arriveras
jamais avec des données personnelles.

## 7. Flux complet d'un message

```
Toi : « Où en est le projet Nova, et qu'est-ce que je disais sur le budget ? »
  │
  ├─1─ LibreChat transmet à l'agent Nova
  ├─2─ Prompt système = identité + faits (Type 2, injectés d'office)
  ├─3─ L'agent décide d'appeler des outils :
  │      nova-projects.project_status("Nova")     → statut, jalons
  │      nova-memory.recall("budget")             → 2 épisodes de mars
  │      nova-files.search_docs("budget Nova")    → 3 extraits de PDF
  ├─4─ Contexte assemblé : faits + statut + épisodes + extraits + question
  ├─5─ Ollama génère la réponse (en citant ses sources)
  ├─6─ Réponse affichée (+ lue à voix haute si mode vocal)
  └─7─ Échange stocké → consolidé cette nuit
```

Le point important de ce flux : **rien n'est sorti de ta machine.**

## 8. Arborescence cible du projet

```
nova/
├── docker-compose.yml           # tout le système
├── .env                         # secrets (jamais commité)
├── config/
│   ├── librechat.yaml           # endpoints, agents, MCP, voix
│   └── prompts/nova-system.md   # l'identité de Nova, versionnée
├── services/
│   ├── nova-memory/             # serveur MCP
│   ├── nova-projects/
│   ├── nova-files/
│   └── nova-consolidator/       # le travail nocturne
├── data/                        # ← TES DONNÉES, à sauvegarder
│   ├── postgres/
│   ├── mongo/
│   ├── ollama/                  # modèles (re-téléchargeables, non critique)
│   └── documents/               # sources originales
├── scripts/backup.sh
└── docs/
```

Règle de sauvegarde : **`data/postgres` et `data/documents` sont irremplaçables.**
Tout le reste se reconstruit avec un `docker compose up`. Une sauvegarde qui ne
couvre que ces deux dossiers suffit — et une sauvegarde simple est une sauvegarde
qui sera réellement faite.
