# 09 — Ce qui est réalisable aujourd'hui, et ce qui ne l'est pas

Évaluation franche de tes 14 capacités, à matériel personnel et en local.

**Légende :** ✅ faisable et bon · ⚠️ faisable mais dégradé en local · ⛔ pas
aujourd'hui.

| # | Capacité | Verdict | Commentaire |
|---|---|---|---|
| 0 | *Capturer* (ajouté) | ✅ | Absent de ta liste, et c'est la capacité la plus critique. Voir critique n°3. |
| 1 | Mémoriser les projets | ✅ | **Ce n'est pas un problème d'IA, c'est une base de données.** Facile, fiable, sous-estimé. |
| 2 | Mémoriser les objectifs | ✅ | Idem. Quelques dizaines de lignes injectées dans le prompt. |
| 3 | Historique intelligent | ✅ | Consolidation nocturne. Technique maîtrisée, résultat très bon. |
| 4 | **Faire des liens** | ⚠️ | **Le plus dur de la liste.** Faisable, mais résultat modeste : ~1 lien utile/semaine. Voir doc 07. |
| 5 | Aider à apprendre | ✅ | **Sous-estimé, meilleur rapport valeur/effort du projet.** Questions générées depuis tes documents, répétition espacée, suivi des lacunes. |
| 6 | Aider à innover | ⚠️ | Les LLM sont bons pour *combiner*, mauvais pour *évaluer*. Nova produira 20 pistes dont 2 valables — c'est à toi de trier. Utile à condition de ne pas attendre du jugement. |
| 7 | Critiquer tes idées | ⚠️ | Sycophantie. Améliorable par la conception, jamais résolu en local. Voir critique n°2. |
| 8 | Rechercher | ✅ | SearXNG + extraction. Qualité correcte, inférieure aux API payantes. |
| 9 | Lire des documents | ✅ | Très bon aujourd'hui. Docling + RAG + citations. |
| 10 | Comprendre des images | ✅ | Bon : description, lecture de texte, schémas simples. Faible sur les plans techniques denses. |
| 11 | Utiliser une caméra | ✅ / ⚠️ | Techniquement trivial. **Faible valeur réelle**, questions de vie privée. Voir critique n°4. |
| 12 | Interface vocale | ✅ | Latence réaliste 1-3 s. Ce n'est pas la fluidité du film, mais c'est confortable. |
| 13 | Concevoir des projets techniques | ⚠️ | **C'est là que le local coûte le plus cher.** Un 30B local est nettement en dessous d'un grand modèle sur l'architecture et le débogage. |
| 14 | Assistant de recherche | ✅ | Le vrai cœur de valeur : chercher, lire, résumer, croiser, citer, garder. Très bon dès la V0.4. |

**Trois capacités sont excellentes et tu les sous-estimes** : n°1/2 (mémoire de
projets — c'est de la base de données, pas de l'IA), n°5 (apprentissage) et n°14
(assistant de recherche). Elles feront 80 % de la valeur que tu retireras de Nova.

**Trois capacités sont surestimées** : n°4 (les liens, spectaculaire mais au
rendement modeste), n°11 (la caméra) et n°6 (l'innovation, qui reste ton travail —
Nova fournit la matière, pas le jugement).

---

## Ce qui n'est pas réalisable aujourd'hui — à savoir avant de commencer

### ⛔ Un modèle qui apprend en continu de tes retours
Le rêve : Nova s'améliore à force de te fréquenter, en modifiant ses propres poids.
La réalité : le réentraînement continu sur des données personnelles est instable
(oubli catastrophique), coûteux, et non résolu en 2026. **Ce qu'on fait à la place :**
la mémoire externe et le prompt. C'est moins élégant, ça marche mieux, et c'est
inspectable — tu peux lire ce que Nova croit savoir de toi, ce qui serait impossible
avec des poids modifiés.

### ⛔ La véritable initiative
Jarvis interrompt Tony parce qu'il a *jugé* que c'était le moment. Aucun système
actuel n'a ce jugement. Ce qu'on construit est une simulation convaincante : des
tâches planifiées, des règles, des seuils. Utile, mais ne confonds pas — Nova ne
décidera jamais spontanément que quelque chose mérite ton attention. Elle appliquera
des règles que tu auras écrites.

### ⛔ La conversation vocale à interruption naturelle
Se couper la parole, hésiter, reprendre — cela demande une architecture audio en flux
avec détection de tour de parole. Des systèmes le font, mais l'intégrer en local à ta
pile est un projet en soi. **Attends-toi à du tour par tour**, avec 1 à 3 secondes de
latence. C'est déjà agréable ; ce n'est pas le film.

### ⛔ Un agent autonome fiable sur des tâches longues
« Nova, fais-moi une revue de littérature complète sur X » en autonomie totale : les
agents dérivent, s'enferment dans des boucles, inventent. C'est vrai même pour les
meilleurs modèles commerciaux, et pire en local. **Ce qui marche :** des tâches
courtes, un point de contrôle humain, des outils bien délimités.

### ⛔ Comprendre tes intentions non exprimées
Nova ne saura que ce que tu écris ou dis. Pas de captation ambiante de ton contexte
mental. C'est le rappel qui compte : **la qualité de Nova sera le reflet direct de ce
que tu y déposes.**

---

## Ce qui a réellement changé et rend le projet possible maintenant

Pour être équitable, l'inverse mérite d'être dit. Ce projet aurait été irréaliste il
y a deux ans, et l'est devenu pour quatre raisons :

1. **Les modèles ouverts sont devenus suffisants.** Un modèle de 30 Md à architecture
   MoE tourne sur une machine personnelle avec une qualité qui, en 2023, demandait
   une grappe de serveurs.
2. **L'appel d'outils fonctionne vraiment.** C'est le déblocage central : sans lui,
   pas de mémoire, pas de MCP, pas de Nova — juste un chatbot.
3. **MCP a standardisé la connexion agent ↔ outils.** Tes capacités deviennent
   portables et survivent à tes changements d'interface.
4. **Les briques locales sont matures** : Ollama, Whisper, pgvector, Docling — toutes
   libres, toutes fonctionnelles, aucune à écrire.

Le projet est ambitieux, mais aucune de ses pièces n'exige de recherche. La seule
partie réellement exploratoire est le moteur de liens — et il est isolé du reste, ce
qui veut dire que même s'il déçoit, Nova reste un excellent système.

---

## Le résumé en une phrase

**Une Nova qui te connaît, lit tes documents, cherche, se souvient, t'aide à
apprendre et te parle est parfaitement réalisable en 12 mois. Une Nova qui a de
l'initiative, du jugement et de l'intuition ne l'est pas — et ne le sera pas par un
choix d'architecture.** Le projet vaut d'être fait pour la première, pas pour la
seconde.
