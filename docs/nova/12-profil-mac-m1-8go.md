# 12 — Profil matériel : iMac M1, 8 Go, macOS 14.6

> Configuration réelle du projet. Ce document remplace les recommandations
> génériques du doc 02 pour tout ce qui concerne cette machine.

```
Puce   : Apple M1
RAM    : 8 Go (mémoire unifiée — pas de VRAM séparée)
macOS  : 14.6.1
Disque : 13 Go libres   ← le point bloquant
```

---

## 1. Le diagnostic

**La RAM n'est pas le problème.** 8 Go de mémoire unifiée sur M1, c'est modeste
mais suffisant pour un modèle de 4 milliards de paramètres quantifié. macOS laisse
Ollama utiliser environ 70 % de la RAM pour le GPU, soit **~5,5 Go de budget**.

**Le disque, si.** 13 Go libres, c'est *déjà* sous le seuil de confort de macOS
(qui commence à mal se comporter en dessous de ~15 % de libre). Avant même
d'installer quoi que ce soit, cette machine est à l'étroit.

Budget d'installation réaliste :

| Élément | Taille |
|---|---|
| `qwen3:4b` (quantifié) | ~2,5 Go |
| `bge-m3` (embeddings) | ~1,2 Go |
| PostgreSQL 16 + pgvector (Homebrew) | ~0,3 Go |
| Environnement Python | ~0,3 Go |
| Outils de ligne de commande Xcode *(si absents)* | ~1,5 Go |
| **Total** | **~4,3 à 5,8 Go** |

Il resterait 7 à 9 Go. Ça tient — mais sans marge, et macOS a besoin de marge pour
la mémoire virtuelle, ce qui est *justement* critique sur 8 Go de RAM.

**Recommandation : libérer du disque avant de commencer. Objectif 30 Go.**
C'est la tâche n°1, avant Ollama, avant tout le reste.

---

## 2. Décision : pas de Docker sur cette machine

C'est l'écart le plus important par rapport au doc 11.

Le `docker-compose.yml` du projet lance trois conteneurs (Postgres, Nova, Open
WebUI). Sur ce Mac, ce n'est pas raisonnable :

- Docker Desktop fait tourner une **machine virtuelle Linux** qui réserve ~2 Go de
  RAM avant même le premier conteneur. Sur 8 Go, c'est un quart de la machine
  perdu — au détriment direct du modèle.
- Son installation coûte plusieurs Go de disque qu'on n'a pas.
- Open WebUI ajoute ~1 Go d'image pour une fonction que la ligne de commande
  couvre déjà en V1.

**Installation native à la place.** Postgres et Nova tournent directement sur
macOS, Ollama aussi. Aucune VM, aucune couche intermédiaire.

Le `docker-compose.yml` reste dans le dépôt : il redeviendra le bon chemin le jour
d'un changement de machine. Ce n'est pas du travail perdu, c'est du travail en
avance.

---

## 3. Choix des modèles

| Rôle | Modèle | Taille | Justification |
|---|---|---|---|
| Cerveau | **à choisir par la mesure** | — | `uv run python scripts/bench_models.py` |
| Embeddings | **`bge-m3`** | ~1,2 Go | **Ne pas économiser ici** |

### ⚠️ `qwen3:4b` a été écarté — mesuré, pas supposé

Recommandé initialement sur ses caractéristiques générales (excellent français,
excellent appel d'outils), il s'est révélé **inutilisable ici**. Mesures réelles
sur cette machine, pour la question « Dis bonjour en une phrase » :

| | Résultat |
|---|---|
| `ollama run` direct | **51,8 s** |
| Via l'API, tel quel | 34,5 s — dont **2619 caractères** de raisonnement invisible |
| Via l'API, `think: false` | 56,4 s — le raisonnement passe simplement dans la réponse |

La cause n'est pas la puissance de la machine : le modèle était résident,
`100% GPU`, et la génération de la réponse elle-même prenait 3 secondes. Tout le
temps partait dans une phase de raisonnement d'environ mille tokens **avant** le
premier mot visible.

**La leçon, et elle vaut pour tout le projet :** aucune fiche technique ne
mentionne ce comportement. Les classements publics ne le mesurent pas. Seule
l'exécution sur la machine réelle le révèle — d'où `scripts/bench_models.py`,
qui mesure ce qui compte vraiment : le **temps avant le premier mot**.

Un modèle « raisonneur » reste utile pour l'analyse lourde. Il est disqualifié
pour l'assistant du quotidien, où la latence perçue prime sur la finesse.

### Pourquoi pas `qwen3:8b`

Il pèse ~5,2 Go, pour un budget GPU de ~5,5 Go. Il « rentre » au sens strict, et
c'est exactement le piège : il ne resterait rien pour les embeddings, macOS
basculerait en mémoire virtuelle, et l'ensemble deviendrait pénible. **Un modèle
rapide et moyen bat un modèle excellent et inutilisable** — c'est le mode d'échec
n°2 du registre des risques.

### Pourquoi garder `bge-m3` malgré son poids

C'est le seul choix du projet qu'on ne peut pas revoir sans tout re-vectoriser.
`nomic-embed-text` ne pèse que 274 Mo, mais il est nettement plus faible en
français — et une recherche dégradée ne lève jamais d'erreur : Nova « ne trouve
pas », sans dire pourquoi. On paie 1,2 Go pour ne pas s'enfermer.

### Le réglage qui change tout — et le piège qui va avec ⚡

Sans entretien, Ollama décharge un modèle après 5 minutes d'inactivité, et
plus tôt encore quand la machine manque de mémoire. Le rechargement se paie
alors **avant chaque réponse**.

Mesure sur cette machine, qui a coûté trois jours à identifier :

```
prompt 6573 caractères  →  21,4 s avant le premier mot
prompt  880 caractères  →  21,1 s avant le premier mot
```

Sept fois moins de contexte, **le même temps**. Un coût qui ne varie pas avec
l'entrée n'est pas du travail proportionnel à l'entrée : c'est un chargement.
Deux tours ont été perdus à raccourcir le prompt.

**Le piège :** `keep_alive` est une option de l'API **native** d'Ollama. Nova
parle à son point d'entrée **compatible OpenAI**, qui ignore en silence les
champs qu'il ne connaît pas. Le réglage était envoyé et n'avait aucun effet.

Deux remèdes, et le second est celui qu'on garde :

```bash
launchctl setenv OLLAMA_KEEP_ALIVE -1    # côté serveur : marche, mais s'oublie
```

Nova Core entretient elle-même le modèle : un fil de fond envoie une requête
d'**un seul jeton toutes les quatre minutes**. Aucune manipulation à retenir,
aucune réinstallation à refaire. **Une correction qui dépend de la mémoire de
quelqu'un n'est pas une correction.**

### Choisir un modèle par la mesure, pas par sa fiche

```bash
uv run python scripts/bench_models.py
```

Le banc décharge chaque modèle, mesure à froid, puis à chaud. La différence
**est** le temps de chargement. Il sépare les trois coûts qu'on confond
constamment :

| Colonne | Ce qu'elle dit | Ce qu'il faut faire si elle est haute |
|---|---|---|
| **Chargement** | le modèle est relu du disque | libérer de la mémoire, ou prendre plus petit |
| **Lecture** | comprendre la question | raccourcir le prompt |
| **Écriture** | produire la réponse | modèle trop gros pour la machine |

Un chargement de 21 s pour 2 Go, alors qu'un SSD lit à plusieurs Go/s, ne dit
pas « le modèle est gros ». Il dit **« la machine manque de mémoire »**.

---

## 4. Attentes honnêtes

**Ce qui marchera bien :** la mémoire des faits, l'ingestion et la recherche
documentaire, les résumés, la conversation courante. C'est-à-dire l'essentiel de
la valeur d'un second cerveau.

**Ce qui sera faible :** le raisonnement long et le **mode critique**. Un modèle
de 4 milliards de paramètres est complaisant — c'est précisément la critique n°2
du dossier, amplifiée par la taille. Ne fonde aucune décision importante sur son
avis, et considère ce mode comme une démonstration tant qu'on est sur cette
machine.

**Ce qu'il faut éviter :** faire tourner Nova pendant que d'autres applications
lourdes sont ouvertes. Sur 8 Go, le navigateur avec vingt onglets et un modèle de
langage se disputent la même mémoire.

---

## 5. Trajectoire matérielle

Cette machine suffit pour aller jusqu'à la **V0.3** (la mémoire automatique),
c'est-à-dire l'étape décisive du projet. Elle ne suffira pas pour la vision ni
pour la voix, qui demandent des modèles supplémentaires résidents.

Si le projet tient six mois et que tu veux investir : **la RAM est le seul chiffre
qui compte** sur Apple Silicon. 32 Go permettent `qwen3:30b-a3b`, qui change
réellement la qualité des réponses. 16 Go est un demi-pas qui ne débloque que
`qwen3:8b` — pas assez pour justifier la dépense.

En attendant, aucune décision d'architecture ne dépend du matériel : changer de
modèle, c'est une ligne dans `.env`.
