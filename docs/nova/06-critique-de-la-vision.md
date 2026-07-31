# 06 — Critique de la vision

> Mon rôle ici n'est pas de valider ton projet. C'est de te dire ce qui, dans ta
> vision, ne se passera pas comme tu l'imagines — pendant qu'il est encore gratuit
> de changer d'avis.

Ta vision est solide sur un point rare : tu as compris que le sujet n'est pas la
conversation mais l'**accumulation**. La plupart des gens qui se lancent là-dedans
construisent une interface de chat de plus. Toi tu décris un système qui te connaît.
C'est le bon problème.

Ce qui suit, ce sont les sept endroits où je pense que tu te trompes.

---

## Critique 1 — « Faire des liens entre les idées » n'est pas une fonction du modèle

C'est ta demande la plus intéressante et **la seule qui n'est pas résolue par les
technologies existantes**. Elle mérite d'être comprise précisément, parce que
l'attente naïve mène directement à la déception.

Ton exemple : hologrammes aujourd'hui, électronique dans 6 mois, et Nova relie.

Ce que beaucoup imaginent : le modèle, étant intelligent, « remarquera » le lien.

**Il ne le remarquera jamais.** Un LLM n'a aucune vie entre deux messages. Il n'a
pas d'arrière-plan mental, pas de rumination, pas d'accès spontané à ton passé. Au
moment où tu parles d'électronique, ta conversation d'il y a 6 mois n'existe tout
simplement pas pour lui — sauf si un autre mécanisme, extérieur au modèle, est allé
la chercher et la lui a mise sous les yeux.

Et le RAG classique ne suffit pas non plus, pour une raison structurelle : le RAG
récupère ce qui **ressemble à ta question**. « Hologramme » et « électronique » ne
se ressemblent pas. Le lien entre eux est *indirect* — il passe par un troisième
concept (modulateur optique → pilotage → électronique de commande). Une recherche
par similarité ne traverse pas ce genre de pont.

Surtout : **personne n'a posé la question.** Le lien doit être *poussé* vers toi, pas
tiré par une requête. Or tout ce que tu connais de l'IA conversationnelle fonctionne
en mode tiré.

Conclusion : cette capacité demande un moteur dédié, qui tourne **hors conversation**,
la nuit, et qui fait de l'ingénierie de données avant de faire de l'IA. Sa conception
est dans [`07-moteur-de-liens.md`](07-moteur-de-liens.md). C'est la partie la plus
ambitieuse du projet et je la traite comme telle.

**Attente à calibrer maintenant :** un bon moteur de liens produira **1 rapprochement
réellement utile par semaine**, noyé dans 20 rapprochements triviaux qu'il faudra
filtrer. Si tu en attends 10 par jour, tu seras déçu et tu abandonneras. Un par
semaine pendant trois ans, c'est 150 idées que tu n'aurais pas eues. C'est énorme.
C'est aussi ce qu'on peut honnêtement viser.

---

## Critique 2 — « Critiquer mes idées » : les modèles locaux sont complaisants

Tu demandes à Nova de te contredire. C'est la demande la plus saine de ta liste, et
c'est aussi celle où la technologie te trahira le plus discrètement.

Les modèles de langage sont post-entraînés pour être agréables. Ce biais — la
sycophantie — est **massif** et il est pire sur les modèles petits et ouverts que sur
les grands modèles commerciaux. Concrètement : tu présentes une mauvaise idée à un
modèle 14B, il te dit que c'est une excellente piste et te propose trois façons de
l'améliorer. Il ne te dira presque jamais « ce projet ne tient pas debout, voici
pourquoi ».

Le danger n'est pas qu'il soit inutile. C'est qu'il soit **activement nuisible** : un
second cerveau qui te confirme dans tes erreurs est pire que pas de second cerveau.
Tu y gagnes une fausse confiance.

Ce qu'on peut faire, dans l'ordre d'efficacité :

1. **Un mode « critique » séparé**, avec son propre prompt système, où la consigne
   n'est pas « aide-moi » mais « trouve les trois raisons pour lesquelles ceci
   échouera ». Changer le rôle change le comportement bien plus que changer le modèle.
2. **Ne jamais présenter l'idée comme la tienne** dans ce mode. « Un collègue propose
   X » produit une critique nettement plus franche que « je propose X ».
3. **Un modèle raisonneur** pour ce mode uniquement (variante *thinking* de Qwen 3) :
   plus lent, mais il déroule les objections au lieu de conclure tout de suite.
4. **Demander une position, pas une évaluation** : « argumente contre » plutôt que
   « qu'en penses-tu ».

Même avec tout ça, sois lucide : **la qualité de critique d'un modèle local de 30 Md
reste en dessous de celle d'un grand modèle commercial.** C'est le domaine où ta
contrainte du local coûte le plus cher. C'est un choix défendable — mais choisis-le
en le sachant, pas par défaut. Voir la question ouverte n°3 en fin de document.

---

## Critique 3 — Ton vrai goulot d'étranglement n'est pas technique, c'est l'alimentation

Un second cerveau vide ne sert à rien. Toute ton attention se porte naturellement sur
la sortie (que Nova répond, comment elle relie, comment elle parle). Or **le projet
échoue presque toujours à l'entrée** : au bout de six semaines, tu as un système
magnifique qui contient trois PDF et douze conversations.

Jarvis observe Tony en permanence. Nova ne saura que ce que tu lui donnes. Et tu ne
lui donneras rien si donner coûte plus de dix secondes.

Ta liste de 14 capacités ne contient pas la capture. C'est l'oubli le plus important
de ta vision, et je l'ajoute comme **capacité n°0**, prioritaire sur les treize
autres :

- une note en une ligne, depuis le téléphone, en moins de 5 secondes ;
- un dossier surveillé : tout fichier déposé est ingéré, sans rien faire d'autre ;
- le partage depuis le navigateur (« envoyer cette page à Nova ») ;
- l'ingestion automatique de tes propres conversations avec Nova.

**Règle d'ingénierie associée :** optimise la friction d'entrée avant d'optimiser la
qualité de sortie. Un système médiocre bien nourri bat un système brillant à jeun.

---

## Critique 4 — La caméra est ta capacité la moins rentable

Elle est dans ta liste parce qu'elle est dans le film. Regardons-la froidement.

**Coût :** un modèle de vision résident en mémoire (concurrence avec ton modèle
principal), une gestion de flux, une capture, un stockage d'images, et — surtout —
une décision sur la vie privée qui engage d'autres personnes que toi.

**Valeur réelle :** que ferais-tu concrètement, cette semaine, avec une caméra ? Dans
la quasi-totalité des cas, la réponse honnête est « lui montrer un objet ou un
document » — ce qu'une photo envoyée depuis ton téléphone fait déjà, sans caméra
permanente, sans flux, sans risque.

**Mon avis de CTO :** la vision d'images, oui, c'est utile et pas cher. La **caméra
permanente**, c'est la seule brique du projet qui change la nature du système : elle
enregistre un espace physique et potentiellement des tiers. Elle mérite d'être
décidée consciemment (qui peut être filmé, qui est informé, quelle rétention, quel
témoin lumineux) et pas installée « parce que c'était dans la liste ».

Recommandation : capture à la demande, jamais de flux continu, et très tard dans la
feuille de route. Si dans un an tu n'as toujours pas ressenti le manque, c'est la
réponse.

---

## Critique 5 — La voix multiplie le plaisir, pas la valeur

Le fantasme Jarvis est vocal. C'est même probablement l'image qui t'a fait démarrer
ce projet. Je ne vais pas te dire de l'abandonner — mais de la situer.

90 % de la valeur d'un second cerveau est **textuelle** : chercher, relier,
mémoriser, citer, comparer. La voix n'ajoute rien à ces fonctions ; elle change
l'expérience, ce qui n'est pas rien, mais elle est aussi la brique qui casse le plus
souvent (latence, coupures, transcriptions fausses, modèles qui se disputent la
mémoire vive).

Le piège classique — et je l'ai vu tuer beaucoup de projets de ce type : mettre la
voix au mois 1, passer trois semaines à déboguer de l'audio, ne jamais construire la
mémoire, et abandonner en croyant que le projet était trop dur. Le projet n'était pas
trop dur. L'ordre était mauvais.

La voix arrive en V0.5, après la mémoire. Ce n'est pas une punition, c'est un
séquencement.

---

## Critique 6 — « Débutant » et « architecture sur plusieurs années » sont en tension

Tu demandes une architecture tenable sur des années, tout en débutant. Ces deux
choses tirent dans des directions opposées : une architecture prévue pour durer est
généralement trop abstraite pour être comprise par celui qui la construit, et un
système compris par un débutant est généralement trop naïf pour durer.

Ma résolution, et c'est un vrai choix d'ingénierie :

- **Le système est modulaire, mais chaque module est minuscule.** Un serveur MCP fait
  80 lignes de Python. Tu peux le lire en entier, le comprendre en entier, le
  réécrire en une soirée. La complexité est dans le *nombre* de modules, jamais dans
  un module.
- **Aucune abstraction avant trois cas concrets.** On n'écrit pas de framework, on
  écrit trois fois la même chose, et *ensuite* on factorise si ça en vaut la peine.
- **On emprunte la complexité au lieu de l'écrire** : LibreChat, Postgres, Ollama
  sont des systèmes complexes maintenus par d'autres. Ton code à toi reste petit.

Corollaire : **méfie-toi de l'IA comme accélérateur.** Elle peut t'écrire 2000 lignes
en dix minutes — dont tu ne comprendras aucune, que tu ne pourras pas déboguer, et
qui deviendront une dette impossible à porter sur trois ans. Ta règle : *tu ne
fusionnes pas du code que tu ne peux pas expliquer à voix haute.* Demande à l'IA de
t'expliquer avant de te générer. Sur un projet de plusieurs années, ta compréhension
est un actif plus précieux que ta vitesse.

---

## Critique 7 — Le vrai risque du projet, c'est toi

Sois lucide sur la statistique : la grande majorité des projets « Jarvis personnel »
meurent au mois 3. Pas pour des raisons techniques. Pour deux raisons, toujours les
mêmes :

1. **Le système n'apporte de la valeur qu'après avoir accumulé** — mais l'énergie de
   celui qui le construit est maximale au début, quand il est encore vide. La courbe
   de motivation et la courbe de valeur sont décalées de plusieurs mois. C'est le
   cœur du problème.
2. **On construit au lieu d'utiliser.** Construire est gratifiant immédiatement,
   utiliser demande de la discipline. On finit avec un système impeccable dont on ne
   se sert pas.

C'est pour ça que la feuille de route impose un critère par version : *tu l'as
utilisée 5 jours d'affilée par préférence*. Ce n'est pas de la méthode pour faire
joli. C'est le seul garde-fou contre le mode d'échec dominant.

---

## Ce qui est juste dans ta vision, et qu'il faut protéger

Trois choses, à ne pas perdre en route :

1. **« Pas un chatbot ».** Cette phrase, tenue avec rigueur, produit les bonnes
   décisions à chaque carrefour. Garde-la comme test : *est-ce que ce que je
   construis là accumule quelque chose, ou est-ce que ça se contente de répondre ?*
2. **« Changer de modèle sans reconstruire ».** C'est une exigence d'architecte, pas
   de débutant. C'est elle qui impose les deux frontières stables (API
   OpenAI-compatible, MCP) et qui garantit que ton travail de 2026 servira encore en
   2029.
3. **« Comprendre progressivement ce qui est construit ».** C'est ce qui te permettra
   de réparer, et donc de durer. Le jour où tu ne comprends plus ton système, il est
   mort — tu ne le sais juste pas encore.

---

## Les trois questions que je te renvoie avant de valider

Ces trois réponses changent réellement l'architecture. Je ne peux pas les trancher à
ta place.

**Q1 — Ton matériel.** RAM, carte graphique et VRAM, système d'exploitation. Tout le
dimensionnement en dépend, et un mauvais choix ici est la cause n°2 d'abandon.

**Q2 — L'interface : LibreChat ou Open WebUI ?** Comparaison détaillée dans
[`02-technologies-choix.md`](02-technologies-choix.md#1-interface--librechat-ou-open-webui).
Ma recommandation est LibreChat, mais je veux insister sur un point : **c'est la
décision la moins importante du projet.** Elle est réversible en une journée, parce
que la valeur vit dans Nova Core, pas dans l'interface. Ne passe pas deux semaines
à hésiter.

**Q3 — Doctrine du local : stricte ou pragmatique ?** Deux positions défendables :

- *Stricte* — 100 % local, sans exception. Tu acceptes une qualité de critique et de
  conception technique inférieure sur les tâches les plus difficiles. Confidentialité
  absolue, coût nul, indépendance totale.
- *Pragmatique* — tout est local par défaut, et **toi** tu peux router
  explicitement une tâche difficile vers un modèle plus puissant, sans mémoire, sans
  contexte personnel, en le décidant à chaque fois. L'architecture le permet sans
  rien changer (les deux parlent la même API).

Je recommande d'**architecturer pour la position pragmatique et de vivre en position
stricte**. Tu ne fermes aucune porte et tu ne dépends de personne. Mais c'est ta
décision, et elle a une dimension qui n'est pas technique.
