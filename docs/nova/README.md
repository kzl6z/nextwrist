# Nova — Assistant personnel local et évolutif

> Document de conception. Rédigé en tant que CTO / ingénieur principal du projet.
> Aucune ligne de code ici : d'abord l'architecture, les choix, la trajectoire.

## 1. Ce que Nova est (et n'est pas)

**Nova n'est pas un chatbot.** Un chatbot est une fonction sans état : une question
entre, une réponse sort, tout est oublié. Nova est l'inverse : un **système qui
accumule** — de la mémoire, des documents, des projets, des habitudes — et dont la
conversation n'est qu'une des interfaces.

La bonne façon de se le représenter :

```
Un chatbot  = un modèle + une interface
Nova        = une base de connaissances personnelle + des outils + une boucle
              de raisonnement, dont un modèle est le moteur interchangeable
```

Conséquence directe sur l'architecture, et c'est **la décision structurante du
projet** :

> LibreChat n'est pas Nova. Ollama n'est pas Nova. Le modèle n'est pas Nova.
> Nova, c'est **tes données + tes outils**. Tout le reste est remplaçable.

Dans 18 mois tu auras probablement changé de modèle (3 fois), peut-être d'interface,
peut-être de moteur d'inférence. Si ta mémoire, tes projets et tes documents vivent
**dans LibreChat**, tu perds tout à chaque migration. S'ils vivent dans un service
autonome (« Nova Core ») que les interfaces interrogent, tu ne perds jamais rien.

Toute l'architecture qui suit découle de ce principe.

## 2. Principes directeurs

| Principe | Traduction concrète |
|---|---|
| **Local d'abord** | Aucune donnée personnelle ne sort de la machine. Le seul trafic sortant est le téléchargement des modèles et, plus tard, la recherche web. |
| **Données chez toi** | Postgres + système de fichiers, sur ton disque, sauvegardés par toi. Format ouvert, exportable, lisible sans Nova. |
| **Open source** | Licences OSI (Apache 2.0, MIT, AGPL) privilégiées. Les exceptions sont signalées explicitement dans `02-technologies-choix.md`. |
| **Simplicité** | Un seul `docker compose up`. Pas de Kubernetes, pas de microservices avant d'en avoir besoin. Chaque brique ajoutée doit être justifiée par un usage réel, pas par une anticipation. |
| **Évolutivité** | Interfaces stables entre les couches (API OpenAI-compatible, protocole MCP). Chaque brique doit pouvoir être remplacée sans toucher aux autres. |
| **Réversibilité** | Aucune décision de la V0.1 ne doit t'empêcher de faire quelque chose en V1.0. |

## 3. Le piège n°1 à éviter

Tu es débutant, et le réflexe naturel est de vouloir tout brancher en même temps :
voix, caméra, mémoire, agents, recherche web. **C'est le mode d'échec le plus
courant de ce type de projet.** Chaque brique ajoute une source de panne, et à cinq
briques simultanées tu passes ton temps à déboguer au lieu de construire.

La règle : **une capacité à la fois, chacune vérifiée avant la suivante.** La feuille
de route est construite exactement comme ça.

## 4. Plan de lecture

| Document | Contenu |
|---|---|
| [`01-architecture.md`](01-architecture.md) | Les 6 couches, le schéma global, la conception de la mémoire |
| [`02-technologies-choix.md`](02-technologies-choix.md) | Chaque techno : rôle, avantages, inconvénients, alternatives, verdict |
| [`03-feuille-de-route.md`](03-feuille-de-route.md) | V0.1 → V1.0 → V2.0, sur trois ans, avec critères de sortie |
| [`04-v01-30-jours.md`](04-v01-30-jours.md) | Le plan semaine par semaine des 30 premiers jours |
| [`05-demarrage-aujourdhui.md`](05-demarrage-aujourdhui.md) | Les étapes exactes, aujourd'hui, dans l'ordre |
| [`06-critique-de-la-vision.md`](06-critique-de-la-vision.md) | ⚡ Les 7 endroits où je pense que tu te trompes + les 3 questions à trancher |
| [`07-moteur-de-liens.md`](07-moteur-de-liens.md) | Le « deuxième cerveau » : graphe, sérendipité, filtrage |
| [`08-risques.md`](08-risques.md) | Registre des risques classé par probabilité réelle |
| [`09-faisabilite-honnete.md`](09-faisabilite-honnete.md) | Tes 14 capacités notées une par une, et ce qui n'est pas faisable |

**Ordre de lecture conseillé :** 06 (la critique) → 01 (l'architecture) → 09 (la
faisabilité) → 03 (la trajectoire) → 05 (aujourd'hui). Le document 06 est le plus
important : il est le seul qui puisse te faire changer d'avis avant de dépenser des
mois.
