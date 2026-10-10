# Casino — casino + paris sportifs

Base complète en **jetons virtuels** (sans valeur, aucun retrait). Bun + SQLite, aucune dépendance.

## Lancer

```bash
cd casino
bun run dev        # http://localhost:3000
```

Copie `.env.example` en `.env` pour configurer. Sans `ODDS_API_KEY`, des matchs de démo
(vraies équipes, scores simulés) sont générés et joués automatiquement toutes les ~10 min.

## Vrais matchs

1. Crée une clé gratuite sur [the-odds-api.com](https://the-odds-api.com).
2. Mets-la dans `.env` : `ODDS_API_KEY=ta_cle`.
3. Choisis les compétitions dans `ODDS_SPORTS` ([liste des clés](https://the-odds-api.com/sports-odds-data/sports-apis.html)).
4. Relance `bun run dev` : le terminal affiche le nombre de matchs chargés et les crédits restants.

Les cotes affichées sont la moyenne des bookmakers européens. Les résultats ne sont demandés
que pour les compétitions qui ont un match commencé depuis plus de 2 h.

**Quota :** le plan gratuit donne 500 crédits/mois. Avec les réglages par défaut (3 compétitions,
cotes toutes les 6 h, résultats toutes les 2 h si besoin) on consomme environ 400 à 550 crédits
par mois : c'est à la limite. Pour plus de compétitions ou des cotes plus fraîches, il faut un plan payant.

## Contenu

| Module | Fichier | Détails |
|---|---|---|
| Comptes | `src/auth.ts` | Inscription/connexion, mots de passe hachés, session en cookie HttpOnly |
| Portefeuille | `src/wallet.ts` | Solde + grand livre de toutes les opérations, bonus quotidien |
| Hasard | `src/rng.ts` | `crypto.getRandomValues`, sans biais. Seule source de hasard du projet |
| Roulette | `src/games/roulette.ts` | Européenne, mises pleines et simples/douzaines/colonnes (RTP 97,3 %) |
| Machine à sous | `src/games/slots.ts` | 3 rouleaux pondérés (RTP 93,5 %, vérifiable via `bun run check:rtp`) |
| Crash | `src/games/crash.ts` | Multiplicateur qui monte, encaissement manuel ou auto ; point de crash tiré et gardé côté serveur (RTP ≈ 96,5 %) |
| Blackjack | `src/games/blackjack.ts` | Sabot 6 jeux, croupier reste sur 17, BJ payé 3:2, double |
| Paris sportifs | `src/sports/` | Simples et combinés (10 sélections max), cotes verrouillées à la prise, règlement automatique, remboursement des matchs annulés |

| Interface | `public/` | Thème sombre façon appli de paris : lobby casino, ticket qui s'ouvre en volet sur mobile, roue de roulette animée (tapis vertical sur téléphone), rouleaux qui défilent, table de blackjack, courbe du crash, compte avec historique et classement |

« NOVA » est un nom provisoire : il se change dans `public/index.html` (logo, titre de la page).

Tout le calcul (tirages, cartes, gains) se fait côté serveur ; chaque mise et son gain sont
écrits dans une même transaction SQL.

## À faire avant tout passage en argent réel

Rien de ceci n'est en place, et c'est conditionné à une licence valide pour le pays visé :

- RNG certifié par un laboratoire agréé (GLI, eCOGRA, iTech Labs…)
- Prestataire de paiement acceptant les jeux d'argent + KYC / anti-blanchiment
- Géoblocage des pays non couverts par la licence
- Jeu responsable : limites de dépôt/mise, auto-exclusion, vérification de l'âge
- Base de données de production (PostgreSQL), sauvegardes, journal d'audit conforme
