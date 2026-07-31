# 08 — Registre des risques

Classement par **probabilité réelle**, pas par gravité théorique. Les trois premiers
sont ceux qui tuent effectivement ce genre de projet ; les risques techniques
spectaculaires arrivent loin derrière.

| # | Risque | Prob. | Impact | Traitement |
|---|---|---|---|---|
| R1 | Abandon au mois 3 | **Élevée** | Fatal | Voir ci-dessous |
| R2 | Second cerveau sous-alimenté | **Élevée** | Fatal | Capture < 5 s, dossier surveillé |
| R3 | Dérive de la complexité | **Élevée** | Grave | 1 capacité/version, critère de sortie |
| R4 | Bruit du moteur de liens | Élevée | Grave | Filtre 3 passes + vote |
| R5 | Pourrissement de la mémoire | Moyenne | Grave | Dates, confiance, validation humaine |
| R6 | Sycophantie / fausse confiance | Moyenne | **Grave** | Mode critique séparé |
| R7 | Matériel insuffisant | Moyenne | Grave | Dimensionner bas, mesurer tôt |
| R8 | Perte de données | Faible | **Fatal** | restic + restauration testée |
| R9 | Casse à la mise à jour | Moyenne | Modéré | Versions épinglées, RUNBOOK |
| R10 | Fuite de données | Faible | **Grave** | Tailscale, jamais d'exposition publique |
| R11 | Enfermement technologique | Faible | Modéré | MCP + Postgres + Markdown |
| R12 | Dette de code incompréhensible | Moyenne | Grave | Ne pas fusionner ce qu'on ne sait pas expliquer |

---

## R1 — L'abandon au mois 3 · le risque n°1, et de loin

**Mécanisme.** La valeur d'un second cerveau croît avec l'accumulation : elle est
quasi nulle les trois premiers mois, puis devient forte. Ton énergie suit la courbe
inverse : maximale au démarrage, déclinante ensuite. Les deux courbes se croisent
vers le mois 3 — c'est là que la plupart des projets meurent, au moment précis où ils
allaient commencer à servir.

```
énergie  ▔▔▔▔▔╲___________
valeur   ______╱▔▔▔▔▔▔▔▔▔▔
              ↑ mois 3 : le point de rupture
```

**Traitement.**
- Chaque version doit apporter une valeur **immédiate**, indépendamment de
  l'accumulation. C'est pour ça que la V0.1 contient le RAG documentaire : il est
  utile dès le premier jour, contrairement à la mémoire.
- Critère de sortie de chaque version : *utilisée 5 jours d'affilée par préférence*.
  Si tu ne l'utilises pas, la version suivante n'est pas le problème.
- Interdire les mois sans livrable. Un système en chantier permanent n'est jamais
  utilisé, donc jamais nourri, donc jamais utile.
- Accepter de rester en V0.3 pendant six mois. Ce n'est pas un échec : la V0.3 est
  déjà plus utile que la plupart des assistants existants.

---

## R2 — Le second cerveau reste vide

**Mécanisme.** Traité en détail dans la critique n°3. Si donner une information à
Nova coûte plus de dix secondes, tu ne le feras pas. Au bout de six semaines, la base
contient trois PDF et le système ne peut rien relier.

**Traitement.** Capture prioritaire sur tout le reste : note en une ligne depuis le
téléphone, dossier surveillé, partage depuis le navigateur, ingestion automatique de
tes propres conversations. **Optimiser l'entrée avant la sortie.**

**Indicateur d'alerte :** moins de 5 éléments ajoutés par semaine pendant un mois.

---

## R3 — La dérive de la complexité

**Mécanisme.** Chaque brique semble raisonnable isolément. À 15 conteneurs, plus
rien ne démarre, une mise à jour casse trois services, et tu passes tes soirées à
administrer au lieu de construire. Le système devient son propre projet.

**Traitement.** Une capacité par version. Toute brique nouvelle doit répondre à un
manque *constaté à l'usage*, jamais anticipé. Et une question à chaque ajout : **que
se passe-t-il si ce service tombe ?** Si la réponse est « Nova ne démarre plus »,
c'est une mauvaise architecture — les capacités doivent être facultatives.

---

## R4 — Le moteur de liens produit du bruit

Traité dans [`07-moteur-de-liens.md`](07-moteur-de-liens.md#8--attentes-réalistes--à-lire-avant-de-commencer).
Résumé : filtre à trois passes, maximum 3 liens par semaine, vote obligatoire. Et une
attente calibrée à **un lien vraiment utile par semaine**.

---

## R5 — Le pourrissement de la mémoire

**Mécanisme.** Insidieux et sous-estimé. Au bout d'un an, la mémoire contient : des
faits périmés (« je travaille sur X » alors que X est abandonné depuis 8 mois), des
contradictions jamais arbitrées, des inférences hasardeuses du modèle prises pour des
faits. Nova devient confiante et fausse — pire que Nova ignorante.

**Traitement.**
- Tout fait porte une **date**, une **source** et un **niveau de confiance**.
- Aucun fait n'entre en mémoire sans **validation humaine** (la revue du matin).
- Distinguer strictement les faits *déclarés par toi* des faits *inférés par le
  modèle*. Ne jamais les mélanger dans la même table sans marqueur.
- Révision trimestrielle : Nova liste ses 20 faits les plus anciens et demande s'ils
  tiennent toujours.
- Un fait contredit n'est pas écrasé, il est **daté et archivé**. L'historique des
  changements d'avis a de la valeur.

---

## R6 — La sycophantie et la fausse confiance

**Mécanisme.** Traité dans la critique n°2. Un second cerveau qui valide tout te rend
plus confiant sans te rendre plus juste. C'est le risque le plus dangereux du projet,
parce qu'il est invisible : rien ne casse, tout a l'air de fonctionner.

**Traitement.** Mode critique avec prompt adversarial et modèle raisonneur ; ne
jamais présenter une idée comme la tienne quand tu demandes une critique ; exiger des
sources. Et un réflexe personnel : **quand Nova est d'accord avec toi, c'est le
moment de te méfier**, pas de te réjouir.

---

## R7 — Matériel insuffisant

**Mécanisme.** Modèle trop gros → 2 tokens/seconde → tu ne l'utilises plus au bout de
dix jours. Ou : trois modèles se disputent la VRAM (texte, vision, transcription) et
chaque bascule prend trente secondes.

**Traitement.** Dimensionner **en dessous** de ce que la machine peut théoriquement
faire. Mesurer la vitesse dès le jour 3, avant de construire quoi que ce soit dessus.
Un modèle rapide et moyen bat un modèle excellent et inutilisable — sans discussion,
parce que le premier sera utilisé.

---

## R8 — La perte de données · faible probabilité, conséquence fatale

**Mécanisme.** Un `docker compose down -v` de trop, un disque qui lâche, et trois ans
de mémoire disparaissent. C'est la seule chose du projet qui ne se re-télécharge pas.

**Traitement.**
- restic, chiffré, quotidien, sur un support distinct + une copie hors du domicile.
- **Restauration testée le premier mois, puis tous les six mois.** Une sauvegarde
  jamais restaurée n'est pas une sauvegarde, c'est une intention.
- Ne sauvegarder que ce qui compte (`postgres`, `documents`) : une sauvegarde simple
  est une sauvegarde qui sera réellement faite.
- Export périodique de la mémoire en **Markdown lisible**. Même si tout le système
  disparaît, tu gardes tes faits et tes résumés dans un format que n'importe qui peut
  lire dans vingt ans.

---

## R9 — La casse à la mise à jour

`:latest` fonctionne jusqu'au mardi soir où il ne fonctionne plus. Versions épinglées
partout, montée de version décidée et testée, notée dans le RUNBOOK. Et un commit git
avant chaque mise à jour.

---

## R10 — La fuite de données

**Mécanisme.** Nova contiendra, à terme, plus d'informations sur toi que n'importe
quel service que tu utilises. C'est tout l'intérêt du local — et c'est aussi une
concentration de risque : une seule machine, un seul disque, une seule faille.

**Traitement.**
- **Jamais de port ouvert sur Internet.** Accès distant par Tailscale uniquement.
- Chiffrement du disque de la machine hôte.
- Sauvegardes chiffrées (restic le fait par défaut).
- Vigilance sur les serveurs MCP tiers : **un serveur MCP s'exécute sur ta machine
  avec tes droits.** N'en installe aucun sans avoir lu son code. C'est le vecteur
  d'attaque le plus plausible de toute l'architecture.
- Question à te poser avant d'ingérer un document : *si cette base fuitait, qu'est-ce
  que ça changerait ?* Certaines choses n'ont pas besoin d'être dans Nova.

---

## R11 — L'enfermement technologique

Faible, parce que l'architecture est conçue contre : deux frontières standard (API
OpenAI-compatible, MCP), des données dans Postgres (SQL, exportable), des documents
en Markdown. Tu peux quitter n'importe quelle brique.

Point de vigilance résiduel : **le modèle d'embeddings**. En changer impose de tout
re-vectoriser. Choisis-le une fois, note-le, n'y touche plus sans raison.

---

## R12 — La dette de code incompréhensible

**Mécanisme.** Tu utilises l'IA comme accélérateur — c'est légitime et je te le
recommande. Le risque est de te retrouver, au mois 8, avec 4000 lignes que tu n'as
jamais comprises, un bug quelque part dedans, et aucune capacité à le trouver. Le
projet s'arrête là, sans qu'aucune décision d'arrêt n'ait été prise.

**Traitement.**
- **Tu ne fusionnes pas du code que tu ne peux pas expliquer à voix haute.**
- Demander à l'IA d'expliquer avant de générer, et de générer petit.
- Chaque module reste sous ~150 lignes. Si ça déborde, c'est qu'il faut découper.
- Écrire, pour chaque serveur MCP, cinq lignes en français : ce qu'il fait, pourquoi
  il existe, ce qui casse s'il tombe.

---

## Les quatre indicateurs à surveiller

Si l'un de ces quatre voyants est au rouge, arrête d'ajouter des fonctionnalités et
traite la cause. Aucune version suivante ne règlera le problème.

| Indicateur | Seuil d'alerte |
|---|---|
| Jours d'utilisation par semaine | < 3 |
| Éléments ajoutés par semaine | < 5 |
| Temps d'administration / temps d'usage | > 1 |
| Dernière restauration testée | > 6 mois |
