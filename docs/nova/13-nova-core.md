# 13 — Nova Core : la plateforme

> Ce document explique ce qui a été construit, pourquoi, et surtout **ce qui
> ne l'a pas été**. La seconde partie est la plus importante.

---

## 1. Le principe qui gouverne tout le reste

> **Le noyau ne connaît ni la base de données, ni le moteur d'inférence, ni
> l'interface. Il ne manipule que des descriptions et des décisions.**

```
api  ──▶  orchestrator  ──▶  core  ──▶  contrats
                        ──▶  memory · documents · llm · voice  ──▶  db
```

Conséquence directe et vérifiable : **le routeur et le planificateur se
testent sans machine, sans modèle et sans réseau.** 36 tests s'exécutent en
0,2 seconde. C'est ce qui les rendra encore vrais quand Ollama, Postgres et
Electron auront tous les trois été remplacés.

C'est aussi le critère qui a décidé de l'emplacement de chaque fichier. Quand
j'ai hésité — l'amorce de dictée doit-elle aller dans `voice/` ? — la règle a
tranché : `voice/vocabulaire.py` transforme des phrases en termes et ne
connaît rien du projet ; aller chercher ces phrases dans la mémoire est le
travail de l'orchestrateur.

---

## 2. Les modules, et ce qu'ils font réellement

| Module | État | Où |
|---|---|---|
| **Memory Engine** | ✅ existait, inchangé | `memory/` — faits, conversations, budget (R13) |
| **Brain Engine** | ✅ existait, inchangé | `orchestrator.py` + `llm/client.py` |
| **Voice Engine** | ✅ existait, enrichi | `voice/` — réveil, transcription, vocabulaire, homophones |
| **Planner Engine** | 🆕 **réel, testé** | `core/planificateur.py` |
| **Model Router** | 🆕 **réel, testé** | `core/routeur.py` |
| **Tool Manager** | 🆕 **réel, 4 outils** | `outils/` |
| **Workspace Manager** | 🆕 **réel, 7 espaces** | `espaces/` |
| **Agent Manager** | 🆕 registre + 2 agents | `agents/` |
| **Platform Engine** | 🆕 réel | `core/plateforme.py` |
| **Vision Engine** | ⚠️ **contrat seul** | `vision/` |

**Rien n'a été déplacé, rien n'a été réécrit.** Les 3 282 lignes existantes
sont intactes ; le noyau se pose au-dessus. C'était la condition de « aucune
régression », et elle se vérifie : les 139 tests d'avant passent toujours.

---

## 3. Le registre : un mécanisme, quatre usages

Outils, agents, espaces et modèles ont le même besoin — être déclarés,
retrouvés par nom, listés par capacité. Écrire quatre gestionnaires aurait
produit quatre fois le même code avec trois divergences.

```python
registre_outils  = Registre("outil")
registre_agents  = Registre("agent")
registre_espaces = Registre("espace")
```

**Ajouter un outil en 2027 ne demandera de toucher aucun fichier existant :**

```python
@registre_outils.enregistrer
class Imprimante:
    nom = "imprimante"
    description = "Envoie un document à l'imprimante"
    capacite = "action"
    def executer(self, chemin): ...
```

C'est la définition opératoire de « extensible » : une capacité nouvelle
n'est pas une modification, c'est un ajout.

**La validation est stricte à l'entrée.** Une brique sans description, avec
une capacité inventée, ou dont le nom est déjà pris fait échouer le démarrage
avec un message qui dit quoi corriger. L'alternative — découvrir six mois
plus tard qu'un outil n'a jamais eu de description — est exactement la dette
qui rend un projet impossible à reprendre.

### Pourquoi des `Protocol` et pas des classes de base

Un outil n'a **rien à importer de Nova** pour en devenir un ; il lui suffit
d'avoir les bons attributs. Un module écrit dans trois ans, sans connaître le
noyau, se branche sans modification. Un héritage aurait imposé une dépendance
vers le noyau — un couplage dans le mauvais sens.

---

## 4. Le planificateur

```
« Prépare-moi un exposé sur Donald Trump »

  1. Comprendre le sujet et l'angle attendu   raisonnement
  2. Rechercher la matière                    recherche
  3. Construire le plan                       raisonnement
  4. Rédiger les diapositives                 rédaction
  5. Illustrer                                vision
  6. Vérifier la cohérence                    raisonnement
  7. Présenter l'espace de travail            action
```

**Un plan est une donnée, pas une exécution.** On peut donc l'afficher, le
journaliser, le faire valider avant exécution, le rejouer à l'identique. Une
chaîne d'appels enfouie dans du code ne permet aucune de ces quatre choses.

### Le piège évité

Faire planifier un modèle à chaque phrase serait ruineux et absurde : « quelle
heure est-il » n'a pas besoin d'un plan en sept étapes. La règle est donc :

> **on planifie quand la demande le mérite, jamais par principe.**

`Plan.direct` distingue les deux cas. Huit familles sont reconnues sans
aucun appel — présentation, développement, voyage, document, recherche,
analyse média, impression 3D, automatisation — **en zéro milliseconde**.

### Il ne peut pas échouer

Trois origines possibles, toujours un plan :

| Origine | Quand |
|---|---|
| `deterministe` | motif reconnu, aucun appel |
| `modele` | le modèle a proposé un découpage exploitable |
| `repli` | le modèle a échoué, ou répondu n'importe quoi |

Un modèle absent, lent ou incohérent dégrade la **finesse** du plan, jamais
la capacité de Nova à répondre.

> Cette propriété a d'ailleurs masqué un vrai bug : ma consigne au modèle
> utilisait `str.format` sur un texte plein d'accolades JSON. Elle levait à
> **chaque** appel, et le repli produisait un plan correct. C'est le test du
> chemin nominal qui l'a trouvée. **Un système qui ne peut pas échouer peut
> aussi cacher ses pannes.**

---

## 5. Le routeur de modèles

> **L'utilisateur ne choisit pas l'IA. Nova choisit.**

Sur des **mesures**, jamais sur des réputations — `scripts/bench_models.py`
les relève sur la machine réelle.

```
1. Écarter ceux qui n'ont pas la capacité demandée.
2. Écarter ceux qui monologuent, si la réponse doit être prononcée.
3. Écarter ceux qui n'atteignent pas la vitesse minimale de l'usage.
4. Parmi les restants : le PLUS CAPABLE, pas le plus rapide.
```

Le point 4 mérite d'être défendu, parce qu'il va contre l'intuition. Mesures
réelles sur l'iMac :

| Modèle | Poids | Vitesse |
|---|---|---|
| `qwen2.5:1.5b` | 1,0 Go | 55 j/s |
| `llama3.2:3b` | 2,0 Go | **28,8 j/s** ← retenu |

Les deux sont largement sous le seuil de confort. À ce niveau, la vitesse
supplémentaire **ne s'entend pas** — d'autant que la parole en flux commence
dès la première phrase. Le milliard de paramètres en moins, lui, s'entend à
chaque réponse.

On ne troque de la capacité contre de la vitesse que **sous** le seuil. C'est
la règle du premier jour : *une IA extraordinairement intelligente avec une
interface simple bat une interface spectaculaire avec une IA médiocre.*

### Les usages, pas les modèles

```python
USAGES["vocal"]  # conversation, ≥12 j/s, ne monologue pas, local exigé
```

`USAGES["vocal"]` reste vrai en 2035. `"llama3.2:3b"` non. **Aucun appelant
ne nomme jamais un modèle.**

---

## 6. La réactivité, dans l'architecture

Comprendre et répondre n'ont pas le même coût. Les séparer en deux points
d'entrée permet à l'interface d'afficher le plan **tout de suite** :

```
POST /v1/plan        ce qu'elle compte faire      10 ms      (aucun modèle)
GET  /v1/capacites   ce dont elle dispose         immédiat
POST /v1/messages    la réponse                   le temps qu'il faut
```

C'est la différence entre « elle rame » et « elle travaille » — **pour un
temps total identique**.

Trois autres décisions servent le même objectif :

- **Le démarrage n'attend jamais un modèle.** Entretien du modèle de langue
  et préchauffage de la transcription partent tous deux en tâche de fond.
  Le travail prévisible se fait pendant que personne ne regarde.
- **Le planificateur déterministe ne coûte rien**, ce qui permet de l'appeler
  à chaque demande.
- **Le rendu s'efface devant le calcul** (`rendu-econome.js`) : sur Apple
  Silicon, l'animation et le modèle partagent le même processeur graphique.

---

## 7. ⚠️ Ce qui n'a PAS été construit, et pourquoi

C'est la partie que je te dois le plus.

### La vision ne voit rien

Chaque méthode lève `PasEncoreImplemente` avec ce qui manque exactement. **Un
module qui prétend faire quelque chose et ne le fait pas est pire que son
absence** : on l'appelle, il rend une valeur vide, et on cherche le bug
ailleurs.

Ce qu'elle demandera, honnêtement :

| Capacité | Ce qu'il faut |
|---|---|
| Décrire une image | un modèle multimodal résident, ~4 Go |
| Analyser une vidéo | le même, plus un découpage en images-clés |
| Identifier des composants | un modèle spécialisé, ou une base de références |
| Trouver la documentation | un accès réseau **et une politique de sortie** |
| Reconstruire en 3D | de la photogrammétrie : un projet, pas une fonction |

Sur 8 Go, un modèle multimodal résident **à côté** du modèle de langue n'est
pas réaliste — la mesure de cette session le dit sans ambiguïté : chaque
mégaoctet résident se paie deux fois.

### Deux agents, pas six

Enregistrer six agents vides donnerait l'illusion d'un système complet et
rendrait chaque débogage plus difficile. Le contrat est prêt, le registre est
prêt ; les agents arriveront quand ils auront quelque chose à faire — et
surtout quand un modèle les rendra utiles. Un modèle de 3 milliards de
paramètres ne rédigera pas un exposé de vingt diapositives.

### Ni terminal, ni navigateur, ni impression

Ces outils **agissent** sur la machine ou sortent de la maison. Ils demandent
une politique d'autorisation qui n'existe pas encore. Livrer « exécuter une
commande shell » sans ce garde-fou serait irresponsable — d'autant qu'un
document ingéré peut contenir des instructions.

Le seul outil qui touche au disque, `lire_fichier`, est borné au dossier de
travail, chemin **résolu** avant comparaison : `data/../../.ssh` commence
bien par `data/`.

### Le plan est calculé, pas encore exécuté

L'intégration est **observable avant d'être agissante**. Le plan est produit,
journalisé, exposé par l'API ; la réponse continue de passer par le chemin
éprouvé. Brancher l'exécution des agents le même jour aurait mis en jeu tout
ce qui fonctionne pour une capacité que rien n'attend encore.

C'est la règle du projet, appliquée à l'architecture elle-même : **une
capacité à la fois, chacune vérifiée avant la suivante.**

---

## 8. Pourquoi ça tient dix ans

| Ce qui changera | Ce qu'il faudra toucher |
|---|---|
| Le modèle de langue | une ligne de `.env` |
| Le moteur d'inférence | `llm/client.py`, seul module qui sait qu'Ollama existe |
| L'interface | rien — Nova tourne sans |
| La base de données | `db.py` |
| Un nouvel outil | **un fichier nouveau, zéro fichier existant** |
| Un nouvel espace | idem |
| Un nouvel agent | idem |
| Une nouvelle capacité | une ligne dans `CAPACITES_CONNUES` |

Le seul fichier qu'on ne peut pas changer sans casser le reste est
`core/contrats.py`. C'est précisément pour ça qu'il est court, qu'il ne
dépend de rien, et qu'il ne contient aucune logique.
