# Modules NOVA embarqués dans l'application de bureau

Ces fichiers s'exécutent dans l'application Electron mais appartiennent à
Nova : c'est du code métier, pas de l'habillage. Ils sont versionnés ici pour
qu'un `git pull` suffise à les récupérer, et pour qu'ils aient des bancs
d'essai — ce qui serait impossible s'ils ne vivaient que dans l'application.

## Installation

```bash
make ui                              # ~/Desktop/nova-project
make ui CIBLE=/autre/chemin
```

**Ne les copie pas à la main.** Ce tableau a existé seul pendant des semaines,
et il ne suffisait pas : `brain.js` était rappelé à chaque `git pull`, les
trois autres non. `rendu-econome.js` — le correctif de la contention GPU,
mesuré et testé — est resté sur l'étagère pendant que la machine se figeait à
chaque réponse. Une instruction qu'il faut *penser* à appliquer n'est pas une
instruction.

`make ui` est idempotent (bloc délimité, réécrit à chaque fois), sauvegarde
`script.js` avant d'écrire, et **relit** le résultat : il se termine en erreur
si un module manque.

Pour vérifier côté application, dans la console :

```
[NOVA/rendu] cadence adaptative — 4 images/s pendant qu’elle réfléchit
```

Si cette ligne est absente, le rendu économe ne tourne pas.

| Fichier | Où il va | Banc d'essai |
|---|---|---|
| `brain.js` | `nova-project/electron/` | `test-flux.cjs`, `test-recuperation.cjs` |
| `reveil-vocal.js` | fin de `nova-project/script.js` | `test-reveil.cjs` |
| `parole-en-flux.js` | fin de `nova-project/script.js` | `test-flux.cjs` |
| `rendu-econome.js` | fin de `nova-project/script.js` | `test-rendu.cjs` |

```bash
node test-reveil.cjs
node test-flux.cjs
node test-recuperation.cjs
node test-rendu.cjs
```

Aucun n'a besoin de micro, d'Electron, d'Ollama ni de Nova Core.

`memory.js` n'est pas ici : il appartient à l'application. Les bancs d'essai
en interceptent le chargement et rendent un double.

---

# Réveil vocal

`reveil-vocal.js` est la brique d'écoute permanente. Elle est versionnée ici
parce qu'elle appartient à Nova, même si elle s'exécute dans l'application
Electron : c'est du code métier, pas de l'habillage.

## Ce qu'elle fait

Découpe le flux du micro **par la parole**, jamais par le chronomètre.

```
silence ──▶ [seuil franchi] ──▶ enregistrement ──▶ [700 ms de silence] ──▶ envoi
              ▲                                                              │
              └──────────── 400 ms de pré-roll conservés en amont ───────────┘
```

Trois propriétés qui découlent de cette forme :

1. **La phrase n'est jamais coupée.** Sa longueur est décidée par toi, pas par
   une constante. C'est ce qui distingue « Nova » de « Nova, ouvre le dossier
   du projet dont je t'ai parlé hier ».
2. **Le début du mot n'est jamais perdu.** Au moment où le niveau sonore
   franchit le seuil, la première consonne est déjà prononcée. Le pré-roll la
   rattrape.
3. **Le silence est gratuit.** Aucune requête n'est émise tant que personne ne
   parle — condition nécessaire pour une écoute permanente sur 8 Go.

## Pourquoi du WAV et pas du WebM

Un flux WebM ne se découpe pas : seul le premier morceau porte l'en-tête. Tout
pré-roll y est donc impossible. Le WAV se construit octet par octet, ce qui
rend le tampon circulaire trivial.

## Ce que ça a remplacé

Un extrait de 2,6 s envoyé toutes les 3 s, en aveugle. Deux effets mesurés :

- la phrase tombait à cheval sur deux extraits, et Whisper recevait deux
  moitiés dont aucune n'était intelligible — d'où une réussite sur dix, sans
  qu'aucune erreur n'apparaisse nulle part ;
- la machine transcrivait du silence en boucle, au point qu'une détection
  finissait par prendre 12 s : le processeur était occupé à écouter le vide.

## Essai

```bash
node test-reveil.cjs
```

Simule des trames audio et vérifie la segmentation sans micro, sans Electron
et sans Nova Core : un extrait pour une phrase, aucun pour un bruit bref,
aucun pour du silence, et un en-tête WAV cohérent avec sa charge utile.

## Installation

Le module est intégré à la fin du `script.js` de l'application, en ajout pur —
aucune ligne existante n'est modifiée. Si quoi que ce soit y échoue, ça échoue
**après** le chargement complet : l'interface s'affiche toujours.

---

# Parole en flux

`parole-en-flux.js` fait commencer Nova à parler **avant** qu'elle ait fini
d'écrire.

## Le problème

Trois attentes bout à bout, et un silence complet pendant tout ce temps :

```
écrire toute la réponse  →  la faire synthétiser  →  la prononcer
```

Un humain ne fait pas ça : il commence sa phrase et construit la suite en
parlant. C'est ce qui donne à Siri et à ChatGPT vocal leur air instantané —
ils ne calculent pas plus vite, ils **commencent plus tôt**.

## Comment

Deux obstacles, deux petites machines à états dans `brain.js` :

| Obstacle | Réponse |
|---|---|
| La réponse arrive enveloppée dans `{"response":"…"}` | `ExtraitReponse` lit ce champ caractère par caractère pendant que le reste s'écrit, en gérant les échappements — un `\"` au milieu d'une phrase ne doit pas être pris pour la fin du champ |
| Une syllabe isolée ne se synthétise pas | `DecoupePhrases` coupe sur une ponctuation **suivie d'un espace**, avec une longueur minimale : « 3.5 » et « M. Dupont » restent entiers |

Côté fenêtre, une file d'attente prononce les phrases dans l'ordre. Sans elle,
deux voix se superposeraient dès la deuxième phrase.

## ⚠️ Ce que ça ne fait pas

Le flux ne raccourcit que **l'écriture**. Si le modèle met trente secondes à
*lire* la question avant son premier mot, il n'y a rien à diffuser pendant ces
trente secondes.

La parole en flux et la taille du prompt ne s'opposent pas : **elles se
multiplient**. Voir R13 dans `docs/nova/08-risques.md`.

## Essai

```bash
node test-flux.cjs
```

Lance un faux Nova Core qui émet l'objet JSON caractère par caractère, à la
vitesse d'un modèle local, et vérifie ce qui compte vraiment :

```
 1409 ms | Un trou noir est une région de l'espace où la gravité est si intense…
 3435 ms | Même la lumière y reste piégée pour toujours.
 3436 ms | (fin de la génération)

elle commence à parler 2027 ms avant la fin — 59 % de silence en moins
```

Le test vérifie aussi que le texte est reconstitué **exactement** et que la
mémoire structurée traverse le flux sans perte.

---

# Récupération de la réponse

Un petit modèle invente des formes. Cas **réel**, relevé dans les logs : le
contrat disait

```json
{"response":"tes deux phrases"}
```

et `llama3.2:3b` a pris le texte d'exemple pour le **nom du champ** :

```json
{ "tes deux phrases": { "Un trou noir est une région…": "C'est une…" } }
```

La réponse était là, complète et juste, rangée là où personne ne la cherchait.
Nova a dit « Entendu. » — le garde-fou `res.response || 'Entendu.'`, sans que
rien ne le signale.

Deux corrections, et il fallait les deux :

1. **La consigne** nomme la clé explicitement et donne deux exemples complets
   avec de vraies questions. Un texte d'exemple à l'intérieur du JSON est pris
   au pied de la lettre.
2. **Le filet** parcourt tout l'objet et récupère les phrases où qu'elles
   soient — dans les valeurs comme dans les clés, puisque le modèle avait mis
   la moitié de sa réponse dans une clé.

Le seuil de 30 caractères sépare une phrase d'un nom de champ. Sans lui, Nova
prononcerait « query goal Research ».

```bash
node test-recuperation.cjs
```

Le cas réel est dans le test, avec les formes plausibles autour (clé anglaise,
clé française, tableau, imbrication) et ce qu'il ne faut surtout pas récupérer.

---

# Rendu économe

`rendu-econome.js` rend le processeur graphique au modèle pendant qu'il
réfléchit.

## Le constat

Mêmes appels, même modèle, mesurés au banc :

| | Application fermée | Application ouverte |
|---|---|---|
| Lecture de la question | 0,2 s | **14,6 s** |
| Écriture | 28,8 jetons/s | **7,6 jetons/s** |

Soixante-treize fois plus lent à lire, presque quatre fois plus lent à écrire.
Le modèle n'y était pour rien, le prompt non plus : **c'est l'interface qui
étranglait le moteur.**

## Pourquoi l'écart est si différent sur les deux phases

C'est ce rapport — 73 contre 3,8 — qui a permis de désigner la sphère plutôt
que la mémoire ou le disque. Sur Apple Silicon, l'animation et le modèle
partagent le **même** processeur graphique, mais les deux phases n'en
dépendent pas de la même façon :

- la **lecture** traite tous les jetons du prompt en parallèle — la phase la
  plus massivement parallèle, donc la plus sensible à un GPU déjà occupé ;
- l'**écriture** produit un jeton après l'autre et bute surtout sur la bande
  passante mémoire.

Une contention mémoire aurait dégradé les deux dans les mêmes proportions.

## Ce que fait le module

Il n'arrête pas l'animation — une sphère figée dirait « c'est planté »
exactement au moment où il ne faut pas. Il abaisse sa cadence, et l'abaisse
le plus fort quand le modèle travaille :

| État | Images/s | Pourquoi |
|---|---|---|
| INTRO, PRESENTING | 30 | mise en scène, aucun modèle ne tourne |
| LISTENING | 20 | elle réagit à la voix, ça doit rester vivant |
| IDLE | 12 | une respiration de 7,5 s n'a pas besoin de plus |
| SPEAKING | 12 | il écrit peut-être encore la phrase suivante |
| **THINKING** | **4** | ⚡ le GPU appartient au modèle |

Soixante images par seconde pour une respiration de 7,5 secondes est de toute
façon du gaspillage : l'œil ne voit rien en dessous de 15, la machine si.

```bash
node test-rendu.cjs
```

Le banc simule `requestAnimationFrame` hors navigateur et vérifie chaque
cadence, la réduction pendant la réflexion (**93 % d'images en moins**), et
que l'annulation d'image reste fonctionnelle — une erreur ici figerait
l'interface ou laisserait une animation tourner en fond.

> La première version du banc annonçait 146 img/s pour une cadence visée à
> 30 : chaque mesure laissait tourner la boucle de la précédente. Un banc
> d'essai se vérifie comme le reste.
