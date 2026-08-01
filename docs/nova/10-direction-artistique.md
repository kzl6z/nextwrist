# 10 — Direction artistique de Nova

> Aucun élément des références n'est repris. Ce document explique ce que j'en retiens,
> puis définit une identité propre à Nova.

---

## 1. Lecture des trois références

### Référence A — la sphère de particules sur fond sombre

Ce qui fonctionne, et pourquoi :

- **Le vide domine.** ~85 % de l'image est du fond. C'est ce vide qui donne l'échelle
  et le calme. Un objet unique dans du vide paraît important ; le même objet entouré
  de widgets paraît décoratif.
- **La forme est incomplète.** L'anneau n'est pas fermé, les particules s'échappent.
  Une forme parfaite paraît morte ; une forme légèrement instable paraît **vivante**.
  C'est le mécanisme central de l'effet « l'IA respire ».
- **Une seule source lumineuse.** Pas de dégradé multicolore : une teinte, des
  variations d'intensité. La sobriété chromatique est ce qui rend l'objet crédible.
- **Le fond n'est pas noir pur** mais un gris-bleu très sombre, légèrement dégradé.
  Le noir pur écrase les basses lumières et fait « fond de page web » ; un gris très
  sombre fait « matière ».

### Référence B — le concept type poste de commandement

Ce qui fonctionne : la hiérarchie est immédiate (un objet central, des états à
gauche, une invite en bas), le vocabulaire d'état est excellent (*veille · écoute ·
réflexion · parole* — quatre mots qui disent tout), et l'ensemble inspire confiance.

**Ce qui ne fonctionne pas, et c'est le point important :**

- **C'est un fond d'écran, pas une interface.** La sphère occupe ~40 % de la hauteur.
  Où s'affiche une réponse de 600 mots ? Où mettre trois citations de sources avec
  numéro de page ? Il n'y a **aucune place pour le contenu** — or un second cerveau
  produit essentiellement du texte.
- **Les anneaux concentriques, les graduations, les traits de scan** ne portent
  aucune information. C'est de l'ornement qui imite l'instrumentation. Au bout de
  trois jours d'usage réel, l'ornement devient du bruit.
- **Les capitales très espacées** (`J A R V I S`) sont la signature typographique du
  faux futur. Utilisable une fois, sur un logotype. Jamais dans une interface.

### Référence C — ton propre prototype, en conditions réelles ⚡

C'est la plus instructive des trois, et je te remercie de l'avoir envoyée : elle
montre le concept **confronté au réel**, et il casse.

Ce que je vois : ton surcouche Nova flotte au-dessus d'un bureau Windows clair,
un explorateur de fichiers ouvert derrière. Résultat :

1. **Le texte clair sur fond clair est illisible.** « ÉTAT / VEILLE / ÉCOUTE » et le
   message de Nova disparaissent presque entièrement. Le design a été pensé sur fond
   noir ; le réel n'est pas noir.
2. **La sphère se superpose au contenu du bureau** au lieu de s'y intégrer. Elle
   paraît collée, pas présente.
3. **Le rendu perd tout son éclat** hors de la maquette.

**La leçon, et c'est une règle d'architecture visuelle, pas un détail :**

> Une interface transparente n'existe pas. Il n'y a que des interfaces **posées sur
> un substrat qu'elles contrôlent**. Tout texte doit reposer sur une surface dont
> Nova maîtrise le contraste — panneau opaque, ou flou de fond suffisamment appuyé
> pour garantir un contraste minimal quel que soit ce qu'il y a derrière.

C'est exactement pour ça que les surcouches d'Apple (Spotlight, Dynamic Island) et de
Tesla sont **des panneaux**, jamais du texte flottant. La transparence y est un effet
de matière sur une surface, pas une absence de surface.

#### Le corollaire, appris à nos dépens ⚡

Le substrat est nécessaire, mais il a une **taille**. La fenêtre de Nova couvre
l'écran entier — elle doit pouvoir afficher la sphère n'importe où. Le flou natif
de macOS (`setVibrancy`), lui, s'applique à **toute la fenêtre** : c'est un
interrupteur, pas une zone. Branché sur « Nova est active », il transformait tout
le bureau en voile laiteux dès qu'elle écoutait — pour une sphère de 60 px
répondant « il est 14 h 12 ».

> **Le voile est un état, pas un mode.** Il ne s'allume que dans les états où Nova
> occupe réellement l'écran (intro, présentation de contenu). Écouter, réfléchir et
> parler depuis un coin ne voilent rien : l'écran appartient à l'utilisateur.

Deux règles d'implémentation en découlent :

- **Capter les clics et voiler l'écran sont deux choses distinctes.** Les confondre
  dans un même signal est la cause exacte du défaut ci-dessus.
- **L'apparence sombre est forcée** (`nativeTheme.themeSource = 'dark'`). Le flou
  natif prend la teinte du thème système ; en thème clair il donne du blanc, ce qui
  contredit toute la direction artistique.

---

## 2. Ce que je retiens — cinq principes

| # | Principe | Traduction |
|---|---|---|
| 1 | **Le vide est le matériau principal** | Marges généreuses, un objet fort par écran |
| 2 | **L'imperfection fait la vie** | La sphère n'est jamais parfaitement stable ni fermée |
| 3 | **Une seule lumière** | Une teinte, des variations d'intensité — jamais un arc-en-ciel |
| 4 | **Aucun ornement** | Si un élément ne porte pas d'information, il dégage |
| 5 | **Toujours un substrat** | Jamais de texte sans surface contrôlée derrière lui |

---

## 3. La direction artistique de Nova

### Le concept : **« Une seule lumière dans une pièce sombre »**

Nova n'est pas un tableau de bord. C'est **une présence discrète et un espace de
travail**. L'interface est un espace neutre, presque monochrome ; la seule chose
vivante à l'écran, c'est Nova elle-même.

### La règle fondatrice — et c'est ce qui nous éloigne le plus des références

> **L'interface est en niveaux de gris. La couleur n'existe que là où Nova pense.**

Concrètement : aucun bouton coloré, aucun lien coloré, aucun accent décoratif. La
hiérarchie se fait par le **contraste et la graisse**, jamais par la teinte. La seule
source chromatique de tout le système est la sphère.

Pourquoi c'est le bon choix :

- **C'est l'inverse exact de Jarvis**, où tout est bleu. On obtient la même sensation
  de présence avec le mécanisme opposé — donc aucune copie possible.
- **Ça donne un sens à la sphère.** Elle n'est plus une décoration : elle est le seul
  endroit où il se passe quelque chose. Quand elle change, l'œil le voit
  instantanément, même en périphérie.
- **C'est intemporel.** Les palettes colorées datent (le bleu cyan date 2010, le
  dégradé violet date 2022). Le gris neutre ne date pas.
- **C'est ce que font Apple et Tesla** : neutre partout, couleur uniquement porteuse
  de sens.

### Palette

```
Fond          --nova-void        #0A0C10   gris-bleu très sombre, jamais noir pur
Surface       --nova-surface     #12151B   panneaux, cartes
Surface haute --nova-raised      #1A1E26   éléments actifs
Bordure       --nova-line        #262B34   1px, très discrète

Texte 1       --nova-text        #E9ECF1   contenu
Texte 2       --nova-muted       #9AA3B0   métadonnées, sources
Texte 3       --nova-faint       #5C6673   labels, horodatages

Lumière       --nova-core        #FFFFFF   le cœur de la sphère
              --nova-halo        #7FE0DC   halo — teal froid désaturé

Sémantique (usage strictement réservé)
Attention     --nova-amber       #E8B36B   « à valider », mémoire incertaine
Danger        --nova-red         #D97066   destructif uniquement
```

**Sur le teal `#7FE0DC` :** volontairement décalé du cyan électrique des références
(`#00A8FF`). Il est désaturé, légèrement vert, plus proche d'une lumière froide réelle
que d'un néon. Il évoque un instrument, pas un jouet — et il est immédiatement
distinguable de tout ce qui imite Iron Man.

### Typographie

| Usage | Police | Pourquoi |
|---|---|---|
| Interface | **Inter** (SIL OFL) | Neutre, très lisible en petit, gratuite, intemporelle. Le choix « Apple » sans copier SF. |
| Technique | **JetBrains Mono** (OFL) | Citations, identifiants, horodatages, chemins. Le monospace **signale** la donnée vérifiable. |
| Logotype | Inter, capitales, interlettrage large | **Une seule fois**, sur le mot NOVA. Nulle part ailleurs. |

Règle : **l'interlettrage large est réservé au logotype.** C'est la signature du faux
futur ; en abuser ruine la crédibilité.

### La sphère — l'unique élément vivant

Ce n'est pas un logo. C'est **un indicateur d'état**, et sa forme dit ce que Nova fait.
C'est ce qui la rend crédible : elle bouge parce qu'il se passe quelque chose, jamais
pour faire joli.

| État | Ce que fait la sphère | Sensation |
|---|---|---|
| **Veille** | respiration très lente (~6 s), luminosité basse, particules quasi immobiles | présente, au repos |
| **Écoute** | l'anneau s'ouvre, les particules dérivent vers la source, réactivité à l'amplitude | tournée vers toi |
| **Réflexion** | rotation interne accélérée, les particules convergent vers le cœur | concentration |
| **Réponse** | pulsations sur le rythme du texte produit | expression |

Trois règles de fabrication :

1. **Jamais fermée, jamais parfaite.** Une déformation continue de faible amplitude.
   C'est ce détail qui produit l'impression de vie.
2. **Elle ne tourne pas en continu au repos.** Une rotation permanente est un
   *spinner* : ça dit « ça charge », pas « je suis là ».
3. **Elle est petite.** 40 à 64 px en usage normal. Elle ne s'agrandit (~200 px) que
   quand il n'y a rien d'autre à afficher — écran d'accueil, mode vocal mains libres.
   **Dès qu'il y a du contenu, le contenu gagne.**

### Mise en page

```
┌──────────────────────────────────────────────────────────┐
│  ◐  NOVA                              22:47 · 3 sources  │  56px, discret
├──────────────────────────────────────────────────────────┤
│                                                          │
│      Colonne de lecture, max 72 caractères               │
│      Interligne 1.65. Beaucoup d'air.                    │
│                                                          │
│      ┌────────────────────────────────────────┐          │
│      │ Note du 12/03 · p.7                    │          │  sources :
│      │ « extrait cité »                       │          │  panneau à part,
│      └────────────────────────────────────────┘          │  monospace
│                                                          │
├──────────────────────────────────────────────────────────┤
│  Écrire à Nova…                                      ⌘K  │
└──────────────────────────────────────────────────────────┘
```

- **Une colonne, pas un cockpit.** Le multi-panneaux est de la mise en scène ; on lit
  dans une colonne.
- **72 caractères maximum** par ligne — au-delà, l'œil perd le début de la ligne.
- **Les sources sont un objet visuel distinct**, en monospace. Voir une source doit
  être aussi immédiat que voir la réponse : c'est ce qui rend Nova vérifiable, donc
  digne de confiance.
- **Aucune bordure superflue.** La séparation se fait par l'espace, pas par des traits.

### Mouvement

| Type | Durée | Courbe |
|---|---|---|
| Micro (survol, focus) | 120 ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Transition | 200 ms | idem |
| Apparition de panneau | 320 ms | idem |
| Respiration de la sphère | 6 s | sinusoïdale |

Trois interdits : pas de rebond (infantilisant), pas d'animation d'entrée sur le
texte (on veut lire, pas regarder), et `prefers-reduced-motion` respecté — la sphère
passe alors à une variation d'opacité seule.

### Ce que Nova n'aura jamais

- ❌ anneaux concentriques décoratifs, graduations, lignes de scan
- ❌ grille hexagonale, réticules, faux radar
- ❌ dégradés multicolores, néon saturé
- ❌ texte flottant sans substrat *(la leçon de la référence C)*
- ❌ voile ou flou sur tout l'écran pour une réponse courte *(son corollaire)*
- ❌ sphère géante permanente au centre
- ❌ police « techno » à empattements anguleux
- ❌ son au démarrage

Chacun de ces éléments dit « je fais semblant d'être le futur ». Leur absence dit
« je suis un outil sérieux ». C'est exactement la différence entre un accessoire de
film et un produit.

---

## 4. Où cette DA s'applique — et où elle attend

Ta règle est explicite, et je la fais mienne : **une IA extraordinairement
intelligente avec une interface simple bat une interface spectaculaire avec une IA
médiocre.**

Conséquence directe sur la V1 : **on ne construit pas d'interface sur mesure
maintenant.** Ce document est une spécification qui sera appliquée le jour où Nova
aura quelque chose d'assez intelligent à montrer. Deux exceptions, délibérément
minuscules :

1. **La sphère** est livrée dès la V1 comme composant autonome (`ui/orb.html`) —
   sans dépendance, sans framework. Elle donne un visage à Nova pour un coût
   négligeable, et se branchera plus tard sur n'importe quelle interface.
2. **Le thème** (variables CSS ci-dessus) est appliqué à l'interface existante
   (Open WebUI accepte du CSS personnalisé). Une soirée, pas un projet.

Tout le reste de l'effort V1 va dans le cerveau. C'est ce qui donne une interface
« qu'on croirait développée dans les prochaines années » : pas les effets — le fait
qu'elle sache réellement quelque chose de toi.
