# 07 — Le moteur de liens (le « deuxième cerveau »)

> C'est la pièce qui distingue Nova de tout ce qui existe déjà. C'est aussi la plus
> difficile, et celle qui demande le plus de discipline pour ne pas produire du bruit.

## 1. Le problème posé

> « Si je lui parle d'hologrammes aujourd'hui puis d'électronique dans 6 mois, je veux
> qu'elle puisse relier les deux sujets et me proposer des pistes nouvelles. »

Trois difficultés distinctes sont cachées dans cette phrase, et elles n'ont pas la
même solution.

| Difficulté | Nature | Pourquoi le chat ne la résout pas |
|---|---|---|
| **Distance sémantique** | « hologramme » et « électronique » ne se ressemblent pas | La recherche vectorielle rapproche ce qui est similaire, pas ce qui est complémentaire |
| **Distance temporelle** | 6 mois séparent les deux | Rien ne relit spontanément le passé |
| **Absence de requête** | Tu n'as pas posé la question | Toute l'IA conversationnelle fonctionne sur requête |

La troisième est la plus profonde. Un système qui répond ne peut pas, par
construction, produire une idée que tu n'as pas cherchée. **Il faut un processus qui
tourne sans toi.**

## 2. Le principe : trois temps séparés

```
   PENDANT           │      LA NUIT             │     LE MATIN
   la conversation   │   (hors conversation)    │
─────────────────────┼──────────────────────────┼─────────────────────
   On capture et     │  On extrait, on relie,   │  On présente 1 à 3
   on répond.        │  on note, on filtre.     │  liens. Tu votes.
   Rapide, réactif.  │  Lent, exhaustif, gratuit│  Court, exigeant.
```

Ce découpage est la clé. La nuit, le temps de calcul ne coûte rien et la latence est
sans importance : on peut faire tourner le modèle pendant deux heures sur l'ensemble
de ton corpus, ce qui serait impensable dans une conversation. **Le luxe du local,
c'est le calcul nocturne gratuit.** Aucun service commercial ne peut se le permettre
à ce prix.

## 3. Étape A — Extraction (à l'ingestion)

Chaque document, chaque note, chaque conversation passe par une extraction :

```
Texte  →  LLM  →  entités        : hologramme, SLM, interférence, laser…
                  type           : concept | technique | matériau | outil | personne
                  relations      : "SLM"  --utilisé-pour-->  "hologramme"
                  question ouverte: "comment piloter un SLM à haute fréquence ?"
```

Trois tables suffisent :

```
entities   id · nom · type · description · embedding · première_vue · dernière_vue
mentions   entity_id · source_id · extrait · date        (où et quand tu en as parlé)
relations  source_id · cible_id · type · confiance · origine
```

Deux détails qui font toute la différence :

- **`mentions` porte la date.** C'est ce qui rend le temps interrogeable : « ce que tu
  explorais en janvier », « un sujet abandonné depuis 8 mois ».
- **Les questions ouvertes sont extraites explicitement.** Ce sont les points
  d'accroche les plus féconds du système : une question sans réponse posée en mars
  qu'un document de septembre vient résoudre, c'est *exactement* le lien que tu
  cherches. Peu de systèmes font ça, et c'est peu coûteux.

## 4. Étape B — Le graphe

Un graphe, mais **dans Postgres**, pas dans une base graphe dédiée.

**Pourquoi :** à ton échelle (quelques dizaines de milliers d'entités), une requête
récursive SQL traverse 2 ou 3 sauts sans difficulté. Neo4j apporterait de la puissance
dont tu n'as pas besoin, au prix d'un système de plus à installer, sauvegarder et
apprendre. Et surtout : tes entités et tes vecteurs vivraient dans deux bases
différentes, ce qui interdit précisément le type de requête dont le moteur a besoin
(*parcours de graphe **et** similarité vectorielle **et** filtre temporel*, en une
fois).

Si un jour la profondeur manque : `Apache AGE`, une extension graphe pour Postgres —
tu gardes une seule base.

## 5. Étape C — Le moteur de sérendipité (le cœur)

Trois stratégies complémentaires, exécutées chaque nuit. Elles ne trouvent pas les
mêmes choses, et c'est le but.

### Stratégie 1 — Le pont structurel

On cherche deux sujets que tu as explorés **à des moments éloignés** et qui partagent
un voisin commun dans le graphe.

```
hologramme ──utilise──> modulateur spatial de lumière (SLM)
                                   │
                            nécessite
                                   ▼
                        pilotage haute fréquence  ←──concerne── électronique
             (mars)                                              (septembre)
```

Le résultat n'est pas « ces deux sujets sont liés » — c'est **le chemin lui-même**,
qui constitue l'explication. Nova ne dit pas « il y a un rapport », elle dit *par où*
passe le rapport. C'est ce qui rend la suggestion actionnable au lieu d'être vague.

C'est la stratégie qui répond littéralement à ton exemple.

### Stratégie 2 — L'analogie distante

On cherche des paires d'entités à la fois **sémantiquement proches** (vecteurs
similaires) et **contextuellement éloignées** (jamais mentionnées ensemble, domaines
différents, périodes différentes).

Le signal de sérendipité, c'est précisément la conjonction `similaire + jamais
rapproché`. Une entité similaire *et* déjà voisine, c'est trivial. Une entité
lointaine *et* dissemblable, c'est du bruit. La valeur est dans l'étroite bande entre
les deux.

C'est la stratégie qui produit les analogies inter-domaines — le mécanisme de la
plupart des innovations réelles.

### Stratégie 3 — La question réactivée

On confronte chaque **question ouverte** enregistrée à tout contenu ingéré depuis.

> « En mars tu te demandais comment dissiper la chaleur d'un laser compact. Le PDF
> que tu as ajouté mardi décrit une technique de caloduc plat qui pourrait
> s'appliquer. »

C'est la stratégie au meilleur rendement et la moins spectaculaire. C'est aussi celle
que je te conseille d'implémenter **en premier** : la plus simple, la plus fiable, et
celle qui donne immédiatement le sentiment que Nova travaille pour toi.

## 6. Étape D — Le filtre, et pourquoi il est vital

**Sans filtre, ce moteur est un générateur de bruit et tu l'ignoreras en trois
semaines.** Un graphe personnel produit des centaines de rapprochements possibles, et
l'écrasante majorité sont vrais mais sans intérêt (« l'électronique et les hologrammes
utilisent tous deux de l'électricité »).

Le filtre en trois passes :

1. **Élagage mécanique** — on écarte ce qui est déjà connu (les deux entités sont déjà
   apparues ensemble), trop générique (une entité reliée à des centaines d'autres :
   « énergie », « système »), ou trop faible.
2. **Notation par le LLM** — chaque candidat survivant est soumis au modèle avec une
   consigne dure : *« note de 0 à 10 la nouveauté et l'utilité de ce rapprochement
   pour quelqu'un qui travaille sur ces sujets. Sois sévère. Une note ≥ 7 doit être
   rare. »* On ne garde que le haut du panier.
3. **Ton vote** — les 3 meilleurs de la semaine te sont présentés. Tu votes 👍 / 👎.
   Le vote est stocké et sert à recalibrer : les types de liens que tu rejettes
   systématiquement sont progressivement écartés.

Cette troisième passe est **non négociable**. C'est la seule chose qui empêche le
système de dériver, et c'est aussi ce qui le fait s'améliorer au lieu de se dégrader.
Un moteur de liens sans retour humain est un flux RSS que personne ne lit.

## 7. Le rendu

Une seule règle : **peu, et daté.**

```
┌─ Nova · rapprochement de la semaine ─────────────────────────┐
│                                                              │
│  Hologrammes (mars) ←→ Électronique de puissance (septembre) │
│                                                              │
│  Le pont : les SLM que tu étudiais en mars demandent un       │
│  pilotage à haute fréquence — exactement la classe de         │
│  problème que tu explores depuis trois semaines.              │
│                                                              │
│  Piste : tes drivers actuels pourraient adresser un SLM       │
│  sans conception nouvelle.                                    │
│                                                              │
│  Sources : note du 12/03 · PDF « SLM driver design » p.7      │
│                                          [ 👍 ]  [ 👎 ]      │
└──────────────────────────────────────────────────────────────┘
```

Ce qui rend ce rendu crédible : le **chemin est montré**, les **dates sont montrées**,
les **sources sont citées**. Sans ça, tu ne peux pas juger si le lien est vrai, et une
suggestion que tu ne peux pas vérifier est une suggestion que tu ignoreras.

## 8. Attentes réalistes — à lire avant de commencer

| Attente | Réalité |
|---|---|
| Volume utile | **~1 lien vraiment intéressant par semaine.** C'est un succès, pas un échec. |
| Taux de déchet | 80-90 % des candidats sont triviaux avant filtrage |
| Montée en puissance | Inutile avant ~3-6 mois de corpus. Un graphe vide ne relie rien. |
| Qualité d'extraction | Le maillon faible : un modèle local extrait des entités approximatives, avec des doublons (« SLM » ≠ « modulateur spatial »). La déduplication d'entités est un vrai chantier, à traiter en V1.x. |
| Effort | La partie la plus coûteuse du projet. ~1 mois de travail pour une V1 correcte. |

**Le mode d'échec principal** n'est pas que le moteur ne trouve rien. C'est qu'il
trouve *trop*, que tu sois submergé de rapprochements médiocres, et que tu cesses de
les lire. Toute la conception ci-dessus est construite contre ce risque : peu de
liens, sévèrement filtrés, toujours explicables, toujours notés par toi.

## 9. Trajectoire de construction

| Étape | Contenu | Version |
|---|---|---|
| 1 | Extraction d'entités à l'ingestion, tables remplies, **rien d'autre** | V0.3 |
| 2 | Visualisation simple du graphe (voir, c'est comprendre ce qu'on a) | V0.4 |
| 3 | Stratégie 3 (questions réactivées) — la plus simple, la plus rentable | V0.6 |
| 4 | Stratégie 1 (ponts structurels) + notation LLM | V1.0 |
| 5 | Stratégie 2 (analogies distantes) + boucle de vote | V1.x |
| 6 | Déduplication d'entités, ontologie personnelle, calibration | V2.0 |

Point important : **l'étape 1 doit démarrer très tôt**, dès la V0.3, même si aucun
lien n'est produit avant des mois. Parce que le moteur ne peut relier que ce qui a
été extrait — et tu ne pourras pas réextraire facilement six mois de conversations
après coup. **Le graphe se remplit longtemps avant de servir.** C'est un
investissement à retardement, et c'est la raison pour laquelle il ne faut pas le
repousser.
