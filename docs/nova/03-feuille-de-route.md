# 03 — Feuille de route V0.1 → V1.0

## Principe de progression

Chaque version ajoute **une seule capacité**, et n'est déclarée terminée que si son
critère de sortie est vérifié. Pas de version suivante tant que la précédente n'est
pas stable et *réellement utilisée au quotidien*.

Le critère d'usage réel est le plus important : une capacité que tu n'utilises pas
est une capacité à supprimer, pas à améliorer. C'est aussi ce qui te protège du
syndrome du chantier permanent.

---

## V0.1 — « Nova parle » · 30 jours

**Capacité :** conversation locale, documents ingérés, souvenirs manuels.

| Brique | Détail |
|---|---|
| LibreChat | interface, version épinglée |
| Ollama | Qwen 3 (taille selon ta machine) |
| Postgres + pgvector | base unique |
| RAG LibreChat | ingestion de documents |
| Prompt système Nova | identité, ton, règles, versionné dans git |
| `facts.md` | mémoire manuelle, injectée dans le prompt |

**Critère de sortie :** pendant 5 jours d'affilée, tu as utilisé Nova *par
préférence* et pas par discipline, et elle a répondu correctement à au moins une
question portant sur un de tes documents.

Détail complet dans [`04-v01-30-jours.md`](04-v01-30-jours.md).

---

## V0.2 — « Nova lit » · +2 semaines

**Capacité :** ingestion documentaire sérieuse et automatique.

- Docling pour les PDF complexes (tableaux, scans, mise en page)
- Dossier surveillé : tout fichier déposé est ingéré automatiquement
- Premier serveur MCP : `nova-files` (`search_docs`, `read_doc`)
- Découpage intelligent (par section, pas par nombre de caractères)
- **Citations obligatoires** : Nova cite toujours le document et la page

**Critère de sortie :** tu déposes un PDF de 100 pages, et 5 minutes plus tard Nova
répond dessus **en citant la page**. Une réponse sans source est un échec.

---

## V0.3 — « Nova se souvient » · +3 semaines · ⚡ étape décisive

**Capacité :** mémoire persistante et automatique. **C'est ici que Nova cesse d'être
un chatbot.** Si tu ne dois faire qu'une seule version après la V0.1, c'est
celle-ci.

- Schéma Postgres : `facts`, `episodes`, `projects`, `decisions`
- MCP `nova-memory` : `remember`, `recall`, `forget`
- MCP `nova-projects` : suivi des projets et objectifs
- **Consolidation nocturne** : résumé du jour, extraction des faits et décisions
- **Validation matinale** : « J'ai retenu ceci hier, tu confirmes ? »

**Critère de sortie :** après 2 semaines sans intervention manuelle, tu demandes
« qu'est-ce que je t'ai dit sur X il y a 10 jours ? » et la réponse est juste.

---

## V0.4 — « Nova cherche » · +2 semaines

**Capacité :** recherche web et synthèse.

- SearXNG auto-hébergé
- MCP `nova-search` : `web_search`, `fetch_page` (extraction de contenu propre)
- Règle d'arbitrage explicite dans le prompt : mémoire → documents → web, dans cet
  ordre, et toujours dire d'où vient l'information
- Mise en cache des pages consultées dans la base documentaire

**Critère de sortie :** Nova répond correctement à une question d'actualité en citant
ses sources, **et refuse d'inventer** quand elle ne trouve rien. Le refus est un
succès, pas un échec.

---

## V0.5 — « Nova écoute et parle » · +3 semaines

**Capacité :** conversation vocale.

- Speaches (STT) + Kokoro (TTS), branchés dans `librechat.yaml`
- Mode mains libres dans LibreChat
- Prompt adapté : réponses courtes à l'oral, on ne lit pas un tableau à voix haute

**Critère de sortie :** une conversation vocale de 5 minutes sans toucher au clavier,
avec moins de 3 secondes de latence entre ta question et le début de la réponse.

---

## V0.6 — « Nova voit » · +3 semaines

**Capacité :** compréhension d'images.

- Modèle de vision (Gemma 3 ou Qwen3-VL) dans Ollama
- Analyse d'images envoyées, captures d'écran, photos de documents
- MCP `nova-vision` : `describe_image`
- Caméra : capture d'une image à la demande, **jamais de flux continu**

> ⚠️ **Point d'attention important.** La caméra est la seule brique du projet qui
> change la nature du système : elle enregistre un espace physique, potentiellement
> d'autres personnes que toi. Décide *avant* de l'installer : qui peut être filmé,
> qui est informé, combien de temps les images sont conservées, y a-t-il un
> indicateur lumineux d'activité. Analyse à la demande plutôt que surveillance
> continue — c'est plus simple, plus sobre, et ça évite de construire un système de
> surveillance domestique par accident. Vérifie aussi les règles applicables si des
> tiers sont concernés.

**Critère de sortie :** Nova décrit correctement une photo et lit le texte d'une
capture d'écran.

---

## V0.7 — « Nova anticipe » · +4 semaines

**Capacité :** proactivité. Le vrai saut vers Jarvis.

- Tâches planifiées (`cron` → serveur MCP `nova-system`)
- Briefing du matin : ce que tu as prévu, ce qui est en retard, ce que Nova a retenu
- Détection de projets stagnants
- Notifications (ntfy, auto-hébergé)

**Critère de sortie :** Nova t'apprend quelque chose d'utile **que tu ne lui as pas
demandé**, au moins une fois par semaine.

---

## V0.8 — « Nova agit » · +4 semaines

**Capacité :** actions sur ton environnement numérique.

- Connecteurs : calendrier (CalDAV), notes (Obsidian/Markdown), tâches, e-mail (lecture)
- **Toute action modifiante passe par une confirmation explicite.** Non négociable.
- Journal d'audit : toute action est tracée, réversible autant que possible

---

## V1.0 — « Nova pense avec toi » · +8 semaines

**Capacité :** partenaire de réflexion.

- `nova-orchestrator` remplace l'agent LibreChat (écrit *après* avoir vécu ses limites)
- Modes de travail : critique, exploration, synthèse, décision
- Nova challenge tes idées au lieu de les valider, connaît l'historique de tes
  raisonnements et sait dire « tu avais écarté cette approche en mars, pour telle
  raison — qu'est-ce qui a changé ? »
- Graphe de connaissances reliant projets, décisions, personnes et documents

---

## Calendrier réaliste

| Version | Cumul | Repère |
|---|---|---|
| V0.1 | 1 mois | Nova existe |
| V0.3 | 3 mois | ⚡ Nova te connaît |
| V0.5 | 5 mois | Nova te parle |
| V0.7 | 8 mois | Nova anticipe |
| V1.0 | 12-14 mois | Nova réfléchit avec toi |

Ce rythme suppose ~5-8 h/semaine. Il **doublera** si tu changes de matériel en cours
de route ou si tu essaies de tout mener en parallèle. À l'inverse, il est
parfaitement acceptable de rester 6 mois en V0.3 : c'est déjà, et de loin, plus utile
que 95 % des assistants existants.
