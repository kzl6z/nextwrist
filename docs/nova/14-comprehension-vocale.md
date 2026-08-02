# 14 — La compréhension vocale

> Nova ne doit pas *transcrire* ce que tu dis. Elle doit **comprendre ce que
> tu veux**. Ce sont deux problèmes différents, et le second n'est pas
> l'affaire du modèle de transcription.

---

## 1. Le problème, en une ligne

Whisper rend une chaîne de caractères. Une chaîne de caractères n'est pas une
demande.

Trois cas relevés en conditions réelles sur cette machine :

| Tu as dit | Whisper a entendu | Ce qu'il fallait faire |
|---|---|---|
| « installe Ollama » | « installe aux lamas » | corriger, sans demander |
| « qui était Aznavour » | « qui était as na vour » | demander confirmation |
| « sur quelle planète pourrions-nous vivre » | « sur quelle planète pour lui en ouvrir » | faire répéter |

Les trois sortent du **même** modèle avec le **même** réglage. Ce qui les
distingue n'est pas la qualité de la transcription : c'est ce qu'on en fait
ensuite.

---

## 2. La règle qui gouverne tout

> **Ne jamais deviner.** Corriger quand on est sûr, demander quand on ne l'est
> pas, et **ne rien toucher** quand la phrase est déjà correcte.

Elle a une conséquence qu'il faut assumer : **Nova demandera parfois de
répéter.** C'est voulu. Un assistant qui répond à côté sans le savoir est bien
pire qu'un assistant qui demande — le premier fait perdre confiance, le second
en inspire.

La troisième partie de la règle est la plus facile à oublier et la plus
coûteuse à violer : une phrase déjà correcte que l'on « améliore » est une
régression pure. C'est pourquoi chaque étage du pipeline est conçu pour
**n'agir que sur ce qu'il sait reconnaître**, et laisser passer tout le reste
intact.

---

## 3. La chaîne

```
micro → STT → nettoyage → correction → intention → validation → LLM
         │        │            │           │            │
    transcribe  nettoyage   lexique   intentions   comprehension
      .py         .py        .py         .py          .py
```

Chaque étage vit dans son fichier et se teste seul. `comprehension.py` est
l'**assemblage** : le seul endroit du pipeline vocal qui ait le droit de
décider.

### 3.1 STT — `voice/transcribe.py`

Nouveauté : la transcription ne rend plus une chaîne mais un objet.

```python
@dataclass(frozen=True)
class Transcription:
    texte: str
    logprob: float | None = None   # ce que Whisper pense de son propre travail
    duree: float = 0.0
```

`avg_logprob` est disponible depuis toujours dans `faster-whisper` et était
**jeté**. C'est pourtant le signal le plus honnête du pipeline : c'est le
modèle lui-même qui dit qu'il a douté. On en garde la moyenne **pondérée par
la durée** — un segment d'une demi-seconde ne doit pas peser autant qu'un
segment de trois.

`str(transcription)` rend le texte : aucun appelant existant n'a changé.

### 3.2 Nettoyage — `voice/nettoyage.py`

Sûr, jamais un pari. Ce qui est retiré ici est retiré parce qu'il ne porte
**aucune** information :

- hésitations (`euh`, `hum`, `bah`, `ben`…), y compris `alors`/`donc` mais
  **uniquement en tête** — « donc » au milieu d'une phrase est un connecteur
  logique, pas une hésitation ;
- répétitions immédiates (« ouvre ouvre Discord »), sauf les répétitions
  légitimes du français (« très très », « non non ») ;
- faux départs (« ouvre Chrome, non, plutôt Firefox » → on garde ce qui suit
  la correction) ;
- mots collés, ponctuation française (l'espace **avant** `? ! ; :`).

Le retrait des hésitations est **itératif** en tête : « alors donc euh lance
Spotify » demande trois passes.

### 3.3 Correction — `voice/lexique.py` + `voice/phonetique.py`

Whisper se trompe sur ce qui est **rare dans la langue**. « Ollama »,
« Rafale », « Electron » ne sont pas rares pour toi — ils le sont pour lui. Un
lexique personnel comble exactement cet écart, et rien d'autre.

Chercher « aux lamas » dans une liste de mots ne donne rien : aucune lettre ne
coïncide. Chercher son **code phonétique** dans un index de codes le trouve
immédiatement :

```
« aux lamas »  →  OLA   →  « Ollama »   (0,96)
« la rafale »  →  RAFAL →  « Rafale »   (0,90)
« bonsoir »    →  BOSWAR → aucun voisin  (on ne touche à rien)
```

L'encodage compare des **sons, pas des lettres**, et ne met **aucun
séparateur** entre les mots — c'est précisément ce qui fait que « aux lamas »
(deux mots) et « Ollama » (un mot) donnent le même code.

Les fragments sont essayés **du plus long au plus court** : « aux lamas » ne se
trouve qu'en regardant deux mots ensemble, et c'est le cas le plus fréquent
des erreurs sur les noms propres.

**Deux seuils, et ils ne servent pas à la même chose :**

| Seuil | Valeur | Effet |
|---|---|---|
| `SEUIL_CERTITUDE` | 0,94 | on corrige **sans demander** |
| `SEUIL_PROPOSITION` | 0,82 | on **propose**, on ne corrige pas |
| en dessous | — | on ne dit rien |

Le coût d'une correction fausse (Nova répond à côté) dépasse celui d'une
correction manquée (Nova demande à répéter). D'où des seuils volontairement
hauts.

#### L'apprentissage, et sa limite

Un terme entre dans le lexique quand il est **confirmé** — pas quand il est
entendu. Trois sources, par ordre de confiance :

| Source | Origine | Poids |
|---|---|---|
| `declare` | `NOVA_WHISPER_VOCABULAIRE`, écrit à la main | 1,00 |
| `memoire` | noms propres des faits confirmés | 0,90 |
| `appris` | corrections que tu as confirmées | 0,75 → 0,95 |

La distinction n'est pas théorique. Apprendre depuis les transcriptions
**brutes** ferait entrer « aux lamas » dans le lexique, et Nova apprendrait sa
propre erreur. C'est le mode d'échec classique de ce genre de système, et il
est **silencieux** : personne ne le voit venir, et au bout de six mois
l'assistant est confiant et faux.

### 3.4 Intention — `voice/intentions.py`

Quatre phrases, une seule intention :

```
« Ouvre Discord »
« Lance Discord »
« Tu pourrais ouvrir Discord ? »
« Est-ce que tu peux ouvrir Discord ? »
« ouvre l'application Discord s'il te plaît »

    → ouvrir_application(cible="Discord")
```

Deux temps, et c'est ce qui rend la méthode robuste sans être fragile :

1. **Dépolitesser** — « est-ce que tu peux », « tu pourrais », « s'il te
   plaît » ne portent aucune information sur l'intention.
2. **Reconnaître** — un verbe déclencheur, puis ce qui suit est la cible.

Énumérer les formulations complètes aurait demandé des centaines d'entrées et
en aurait raté autant. Énumérer les **verbes** et les tournures de politesse
demande vingt lignes et couvre tout le reste.

Douze intentions aujourd'hui (`ouvrir_application`, `fermer_application`,
`arret_pc`, `redemarrer_pc`, `meteo`, `heure`, `date`, `volume_haut`,
`volume_bas`, `silence`, `recherche_web`, `memoire`). **Ajouter une intention
= ajouter une ligne.**

> **Le piège de l'alignement.** « s'il » est UN mot pour toi et DEUX après
> normalisation (« s il ») ; « l'application » de même. Compter les mots du
> côté normalisé pour en retirer du côté original coupe au mauvais endroit —
> dans un sens on laissait « Discord s'il te », dans l'autre la cible gardait
> son déterminant. La correspondance jeton → mot d'origine (`_aligner`) est la
> réponse aux deux cas, et la coupure n'est acceptée qu'à une **frontière de
> mot original** : sans cette garde, le bruit « l » couperait « l'appli » et
> laisserait « appli ».

**Une intention reconnue n'est PAS une action exécutée.** `ouvrir_application`
dit ce qui est voulu ; c'est au Tool Manager de décider s'il sait le faire, et
à la politique d'autorisation de décider s'il en a le droit. Séparer les deux
est ce qui permettra d'ajouter des actions sans jamais toucher ce fichier.

### 3.5 Validation — `voice/comprehension.py`

Trois confiances, **multipliées, jamais moyennées** :

| Source | Ce qu'elle mesure |
|---|---|
| acoustique | `avg_logprob` de Whisper |
| lexicale | les corrections ont-elles été sûres ou approximatives |
| structurelle | la phrase a-t-elle une forme compréhensible |

Une moyenne laisserait un signal fort masquer un signal faible ; or **un seul
doute sérieux suffit** à rendre la demande incertaine. Le produit a exactement
ce comportement.

Trois issues :

| Confiance | État | Ce que Nova fait |
|---|---|---|
| ≥ 0,80 | sûre | transmet au modèle, sans rien demander |
| 0,55 – 0,80 | à confirmer | « As-tu dit : … ? » |
| < 0,55 | incomprise | « Je n'ai pas bien saisi. Tu peux répéter ? » |

Une intention nette relève la confiance de 0,15 : « ouvre Discord » ne veut
rien dire d'autre, même mal transcrit.

> **Le contresens qu'il a fallu corriger.** La confiance d'une *suggestion*
> mesure la qualité de la **correction**, pas celle de la phrase. Une
> suggestion à 0,86 signifie « je crois assez fort qu'il faut corriger » —
> donc que la phrase actuelle est probablement **fausse**. La reprendre telle
> quelle rendait la demande « sûre » justement quand il fallait demander. Un
> doute non levé plafonne donc explicitement la confiance **sous** le seuil.

Chaque décision porte ses **raisons**. Sans elles, un doute est indébogable.

---

## 4. Ce que ce pipeline ne fait pas, et ne fera pas

> « sur quelle planète pour lui en ouvrir » → « sur quelle planète
> pourrions-nous vivre »

Cette reconstruction demande un **modèle de langue**, pas un lexique :
« pourrions-nous vivre » n'est pas un terme rare, c'est du français ordinaire.
Aucun dictionnaire personnel ne la produira jamais.

Ce que le pipeline fait dans ce cas, et qui vaut mieux que d'y répondre à
l'aveugle : il **détecte que la phrase est douteuse** (logprob −0,75,
beaucoup de mots très courts → confiance 0,49) et **demande**.

---

## 5. Où ça se branche

```
api/audio_compat.py          POST /v1/audio/transcriptions
        │
        ├─ transcribe.transcrire(...)        → Transcription(texte, logprob)
        │
        └─ orchestrator.comprendre_la_parole(...)  → Comprehension
```

Le pipeline est appelé depuis l'**orchestrateur**, jamais depuis `voice/`.
Raison : comprendre demande le **lexique**, donc la **mémoire**, et la couche
voix n'a pas le droit de la consulter. La flèche ne remonte jamais.

    api → orchestrator → core → contrats
                      → memory · documents · llm · voice → db

La réponse HTTP conserve `text` — **aucun client existant ne casse** — et
ajoute :

```json
{
  "text": "installe Ollama",
  "brut": "installe aux lamas",
  "confiance": 1.0,
  "sure": true,
  "a_confirmer": false,
  "question": null,
  "intention": null,
  "corrections": [{"entendu": "aux lamas", "propose": "Ollama", "confiance": 1.0}],
  "raisons": ["corrigé : « aux lamas » → « Ollama »"]
}
```

Un client qui ignore ces champs obtient exactement le comportement d'avant.

---

## 6. Le coût, et comment il a été payé

Le vocabulaire personnel vient de la mémoire. Naïvement, cela ajoutait **deux
lectures de la base par phrase dictée** — une pour l'amorce de transcription,
une pour le lexique de correction — **avant même que Whisper ne commence**.
C'est du temps d'attente pur, payé à chaque mot prononcé, et parfaitement
invisible dans le profil : aucune ligne ne paraît coupable.

Deux corrections, toutes deux mesurées :

| Défaut | Correction | Effet |
|---|---|---|
| 2 lectures mémoire par phrase | cache commun, 60 s, invalidé quand un fait est confirmé | 4 appels → **1 lecture** |
| index phonétique reconstruit à **chaque** ajout | indexation paresseuse, une fois par lot | 300 termes : **0,5 ms** au lieu d'un coût quadratique |

Le cache est court **à dessein** : les faits confirmés changent quelques fois
par jour, et une minute de retard sur un nom nouveau ne se remarque pas.
`orchestrator.oublier_le_vocabulaire()` supprime même ce retard, et il est
appelé dès qu'un fait est ajouté ou confirmé — pour que le nom que Nova vient
d'apprendre soit **entendu dès la phrase suivante**.

L'invalidation est déclenchée depuis `api/admin.py`, pas depuis
`memory/facts.py` : la mémoire ne connaît pas l'orchestrateur.

---

## 7. Ce qui reste à faire

| Manque | Pourquoi ça compte |
|---|---|
| La source `appris` n'est jamais alimentée | Confirmer une question « As-tu dit… ? » devrait enrichir le lexique. Le champ existe, la boucle non. |
| Les applications installées ne sont pas lues | `ouvrir_application` a une cible textuelle ; personne ne vérifie qu'elle existe. |
| Aucune intention n'est exécutée | Reconnues, journalisées, transmises au modèle. Le Tool Manager reste à écrire. |
| La confirmation n'est pas parlée | `question()` est rendue par l'API ; l'interface ne la prononce pas encore. |

Ces manques sont **assumés et documentés** plutôt que comblés à moitié : une
boucle d'apprentissage bâclée empoisonne le lexique en silence, et c'est
irréversible.

---

## 8. Tests

`tests/test_voix_comprehension.py` — 62 tests, dont :

- les cinq formulations de « ouvre Discord » donnent **exactement** la même
  intention ;
- une phrase correcte et bien transcrite **ne bouge pas** ;
- une correction incertaine **ne s'applique pas** ;
- le pipeline **ne lève jamais**, y compris sur `""`, `"?"`, `"euh"` ;
- sans lexique, le pipeline fonctionne quand même (chaque capacité est
  facultative).

`tests/test_cache_vocabulaire.py` — 6 tests, dont : une mémoire en panne ne
rend pas Nova muette, et un fait nouveau est entendu dès la phrase suivante.
