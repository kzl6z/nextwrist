# 05 — À faire aujourd'hui, dans l'ordre

Objectif de la journée : **discuter avec un modèle local**, même petit, même lent.
Compter 2 à 3 heures. Rien d'autre.

---

## Étape 0 — Connaître ta machine (10 min) ⚠️ à faire en premier

Tout le reste dépend de cette réponse. Note ces 4 chiffres quelque part :

| À relever | Où |
|---|---|
| RAM totale | Gestionnaire de tâches / Moniteur d'activité / `free -h` |
| Carte graphique et sa VRAM | Gestionnaire de tâches → Performance / `nvidia-smi` |
| Espace disque libre | Prévoir **100 Go** minimum |
| Système d'exploitation | Windows / macOS / Linux + version |

Puis va chercher **ta ligne** dans le tableau matériel de
[`02-technologies-choix.md`](02-technologies-choix.md#3-le-modèle--la-décision-la-plus-dépendante-de-ton-matériel).
Tu tiens ton modèle. Ne prends pas au-dessus « pour voir » : le mode d'échec le plus
courant est un modèle trop lourd qui rend l'usage quotidien pénible.

---

## Étape 1 — Ollama (30 min)

1. Installer Ollama depuis le site officiel (`ollama.com`).
2. Vérifier l'installation en ligne de commande (`ollama --version`).
3. Télécharger **un petit modèle d'abord**, quelle que soit ta machine : `qwen3:4b`.
   Objectif : valider que la chaîne fonctionne, pas obtenir la meilleure qualité.
4. Le lancer et lui poser 3 questions **en français**.
5. Observer la vitesse. Si c'est fluide, télécharger ensuite le modèle de ta ligne.

**Ce que tu valides ici :** l'inférence locale fonctionne sur ta machine. Si ça
coince, tout le reste est bloqué — ne passe pas à l'étape suivante.

---

## Étape 2 — Docker (30 min)

1. Installer Docker Desktop (Windows/Mac) ou Docker Engine + Compose (Linux).
2. Vérifier avec `docker run hello-world`.
3. **Sous Windows :** installer WSL2 si ce n'est pas déjà fait, et travailler
   **dans** le système de fichiers Linux (`~/nova`), pas dans `C:\Users\...` — les
   volumes Docker montés depuis Windows sont beaucoup plus lents et provoquent des
   problèmes de permissions difficiles à diagnostiquer.

---

## Étape 3 — Le dépôt du projet (20 min)

Crée cette structure et initialise git dès maintenant, avant d'avoir quoi que ce soit
à versionner :

```
nova/
├── config/
│   └── prompts/
├── data/          ← à ignorer par git
├── docs/
├── scripts/
└── .gitignore
```

Dans `.gitignore`, dès la première minute : `data/`, `.env`, `*.log`.

Pourquoi maintenant : le jour où tu casseras ta configuration — et tu la casseras —
git est la différence entre « je reviens en arrière en 10 secondes » et « je
recommence tout ». C'est aussi ce qui te permettra d'expérimenter sans peur.

---

## Étape 4 — LibreChat (45 min)

1. Récupérer le dépôt officiel LibreChat.
2. **Épingler une version précise** dans le fichier compose (ne pas laisser
   `:latest`). Note le numéro dans ton `RUNBOOK.md`.
3. Copier le `.env.example` en `.env`, générer les secrets demandés.
4. Démarrer avec `docker compose up -d`, puis **lire les logs** (`docker compose
   logs -f`) : c'est là que se trouvent les erreurs, pas dans le navigateur.
5. Ouvrir l'interface, créer ton compte administrateur.

À ce stade LibreChat tourne mais n'est connecté à aucun modèle — c'est normal.

---

## Étape 5 — Brancher LibreChat sur Ollama (30 min)

C'est l'étape qui échoue le plus souvent, et presque toujours pour la même raison.

Il faut créer un `librechat.yaml` déclarant Ollama comme *endpoint personnalisé*
(API OpenAI-compatible, sur `/v1`), puis le monter dans le conteneur et redémarrer.

**Le point critique — lis-le avant de déboguer :** depuis l'intérieur d'un conteneur,
`localhost` désigne le conteneur, pas ta machine. L'adresse d'Ollama vue depuis
LibreChat est donc :

| Système | Adresse à utiliser |
|---|---|
| Mac / Windows | `http://host.docker.internal:11434/v1` |
| Linux | `http://172.17.0.1:11434/v1` (passerelle Docker) |

Sous Linux, il faut en plus qu'Ollama écoute au-delà de `localhost`
(`OLLAMA_HOST=0.0.0.0`), sinon il refusera la connexion venant du conteneur.

**Fin de journée :** ton modèle apparaît dans la liste déroulante de LibreChat et te
répond. C'est tout, et c'est suffisant. La suite est dans
[`04-v01-30-jours.md`](04-v01-30-jours.md).

---

## Si tu bloques

Dans cet ordre, sans sauter d'étape :

1. **Lire les logs** : `docker compose logs -f <service>`. La réponse y est
   quasiment toujours.
2. **Isoler la couche** : Ollama répond-il *seul*, hors Docker ? Si oui, le problème
   est réseau, pas modèle.
3. **Chercher le message d'erreur exact** dans les *issues* GitHub du projet
   concerné — quelqu'un l'a déjà eu.
4. Discord LibreChat / r/LocalLLaMA : communautés actives et accueillantes.

**Règle de discipline :** ne change **qu'une chose à la fois**, et note ce que tu as
changé. Trois modifications simultanées, et tu ne sauras jamais laquelle a résolu (ou
cassé) le problème. C'est vrai pour la configuration, les modèles et le RAG.

---

## Ce qu'il ne faut pas faire aujourd'hui

- ❌ Installer la voix, la caméra, ou un serveur MCP
- ❌ Télécharger 6 modèles pour les comparer
- ❌ Concevoir la base de données de la mémoire
- ❌ Lire 4 heures de tutoriels avant de lancer la première commande

Aujourd'hui : **une seule chose fonctionne, et elle fonctionne vraiment.**
