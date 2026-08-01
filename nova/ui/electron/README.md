# Réveil vocal — module pour l'application de bureau

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
