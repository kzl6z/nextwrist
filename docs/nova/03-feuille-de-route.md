# 03 — Feuille de route pluriannuelle

## Les trois paliers

| Palier | Ce que Nova devient | Horizon |
|---|---|---|
| **V0.1** | Nova existe. Le socle est là, remplaçable. | 30 jours |
| **V1.0** | Nova est un **second cerveau utile**. Elle te connaît, lit, cherche, se souvient, parle. | 12-14 mois |
| **V2.0** | Nova est un **partenaire de recherche**. Elle relie, veille, t'apprend, tient le carnet. | 24-36 mois |

## Principe de progression

Chaque version ajoute **une seule capacité** et n'est close que si son critère de
sortie est vérifié. Pas de version suivante tant que la précédente n'est pas stable
**et réellement utilisée au quotidien**.

Ce critère d'usage est le plus important du document. Une capacité que tu n'utilises
pas est à supprimer, pas à améliorer. C'est aussi la seule protection contre le
risque n°1 du projet (voir [`08-risques.md`](08-risques.md#r1--labandon-au-mois-3--le-risque-n1-et-de-loin)).

---

# ANNÉE 1 — Construire le second cerveau

## V0.1 — « Nova existe » · 30 jours

LibreChat + Ollama + Postgres/pgvector + RAG documentaire + prompt d'identité +
mémoire manuelle (`facts.md`) + sauvegardes testées.

**Sortie :** 5 jours d'usage d'affilée par préférence, et une réponse juste sur un de
tes documents. Détail : [`04-v01-30-jours.md`](04-v01-30-jours.md).

## V0.2 — « Nova capture et lit » · +3 semaines

⚡ *Priorité relevée par rapport à un plan naïf — voir critique n°3.*

- **Capture à friction quasi nulle** : dossier surveillé, note rapide depuis le
  téléphone, partage depuis le navigateur
- Docling pour les PDF complexes (tableaux, scans)
- Premier serveur MCP : `nova-files`
- Citations obligatoires : document + page

**Sortie :** tu ajoutes 10 éléments dans la semaine **sans y penser**, et Nova répond
dessus en citant la page.

## V0.3 — « Nova se souvient » · +4 semaines · ⚡ étape décisive

**C'est ici que Nova cesse d'être un chatbot.** Si tu ne devais faire qu'une version
après la V0.1, c'est celle-ci.

- Schéma Postgres : `facts`, `episodes`, `projects`, `decisions`
- MCP `nova-memory` et `nova-projects`
- Consolidation nocturne + validation matinale
- **Démarrage de l'extraction d'entités** — le graphe commence à se remplir alors
  qu'il ne sert encore à rien. C'est un investissement à retardement : tu ne pourras
  pas réextraire six mois de conversations après coup.

**Sortie :** après 2 semaines sans intervention manuelle, « qu'est-ce que je t'ai dit
sur X il y a 10 jours ? » reçoit une réponse juste.

## V0.4 — « Nova cherche » · +3 semaines

SearXNG + MCP `nova-search` + extraction de pages + mise en cache. Règle d'arbitrage
explicite : mémoire → documents → web, et toujours dire d'où vient l'information.
Première visualisation du graphe.

**Sortie :** réponse correcte sur une question d'actualité, sources citées, **et refus
d'inventer** quand elle ne trouve rien. Le refus est un succès.

## V0.5 — « Nova critique » · +3 semaines

⚡ *Version ajoutée : c'est une capacité à part entière, pas un effet de bord du modèle.*

- Modes de travail séparés (critique · exploration · synthèse · apprentissage), avec
  leur propre prompt système
- Mode critique : consigne adversariale, idée présentée en tierce personne, modèle
  raisonneur
- MCP `nova-learn` : questions générées depuis tes documents, répétition espacée

**Sortie :** Nova te fait changer d'avis sur quelque chose, au moins une fois.

## V0.6 — « Nova écoute et parle » · +3 semaines

Speaches (STT) + Kokoro (TTS) branchés en configuration. Prompt adapté à l'oral
(réponses courtes, pas de tableaux).

**Sortie :** 5 minutes de conversation vocale sans clavier, moins de 3 s de latence.

## V0.7 — « Nova voit » · +2 semaines

Modèle de vision, images envoyées, captures d'écran, photos de documents.
MCP `nova-vision`. Caméra : **capture à la demande uniquement**, jamais de flux — et
seulement si le manque s'est fait sentir (voir critique n°4).

## V0.8 — « Nova anticipe » · +4 semaines

Tâches planifiées, briefing du matin, détection de projets stagnants, notifications.
Première stratégie du moteur de liens : les **questions réactivées** — la plus simple
et la plus rentable.

**Sortie :** Nova t'apprend une chose utile **que tu n'as pas demandée**, une fois par
semaine.

## V1.0 — « Second cerveau » · ~12-14 mois

- `nova-orchestrator` en Python remplace l'agent LibreChat — écrit **après** en avoir
  vécu les limites, pas avant
- Moteur de liens : ponts structurels + notation LLM + boucle de vote
- Mémoire mature : révision trimestrielle, arbitrage des contradictions, historique
  des changements d'avis
- Export Markdown complet de la mémoire

**Sortie de V1.0 :** tu ne peux plus travailler sans. Concrètement : une semaine sans
Nova te coûte visiblement du temps.

---

# ANNÉES 2-3 — Du second cerveau au partenaire

## V1.x — Consolidation · mois 14-20

Ce palier n'ajoute presque aucune fonctionnalité, et c'est volontaire. C'est le
moment où l'on répare ce que l'accumulation a révélé :

- **Déduplication d'entités** (« SLM » et « modulateur spatial de lumière » sont la
  même chose) — chantier réel, sous-estimé, indispensable au moteur de liens
- Analogies distantes (stratégie 2) et calibration du filtre sur tes votes
- Recherche hybride (vectorielle + mots-clés + filtres) : nettement supérieure au
  vectoriel seul, souvent négligée
- Multi-appareils : accès depuis le téléphone via Tailscale, synchronisation
- Migration éventuelle vers vLLM/llama.cpp **si et seulement si** la vitesse gêne

## V2.0 — « Partenaire de recherche » · mois 24-36

- **Veille autonome** : Nova surveille des sujets, lit, et ne remonte que ce qui est
  nouveau *pour toi* (compte tenu de ce que tu sais déjà — c'est la partie difficile
  et c'est ce qui la distingue d'un flux RSS)
- **Carnet de laboratoire** : elle tient l'historique de tes raisonnements et sait
  dire « tu avais écarté cette approche en mars pour telle raison — qu'est-ce qui a
  changé ? »
- **Graphe mature** : ontologie personnelle, navigation visuelle, requêtes
  temporelles
- **Agents de recherche encadrés** : tâches longues avec points de contrôle humains
  (pas d'autonomie totale — voir [`09-faisabilite-honnete.md`](09-faisabilite-honnete.md))
- **Conception assistée de projets** : Nova connaît tes contraintes, ton matériel,
  tes échecs passés, et en tient compte

## Au-delà — ce qui dépend de l'état de l'art

À réévaluer, pas à planifier : conversation vocale à interruption naturelle,
personnalisation par adaptation légère du modèle (LoRA), agents véritablement
autonomes. Ces trois sujets bougent vite. **L'architecture est construite pour les
accueillir sans réécriture** — c'est tout ce qu'on peut garantir aujourd'hui.

---

## Calendrier et rythme

| Version | Cumul | Repère |
|---|---|---|
| V0.1 | 1 mois | Nova existe |
| V0.3 | 3 mois | ⚡ Nova te connaît |
| V0.5 | 5 mois | Nova te contredit |
| V0.8 | 9 mois | Nova anticipe |
| **V1.0** | **12-14 mois** | **Second cerveau** |
| V1.x | 20 mois | Consolidation |
| **V2.0** | **24-36 mois** | **Partenaire de recherche** |

Rythme calculé pour ~5-8 h/semaine. Il **doublera** si tu changes de matériel en
cours de route ou si tu mènes plusieurs versions en parallèle.

Et une permission explicite, parce qu'elle compte : **il est parfaitement acceptable
de rester un an en V0.3.** Une Nova qui se souvient et lit tes documents est déjà
plus utile que 95 % de ce qui existe. La feuille de route est une direction, pas une
obligation de résultat.
