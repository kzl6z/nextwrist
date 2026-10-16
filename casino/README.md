# PilotCasino — paris sportifs et casino

Base complète en **jetons virtuels** (sans valeur, aucun retrait). Bun + SQLite, aucune dépendance.

## Lancer

```bash
cd casino
bun run dev        # http://localhost:3000
bun test           # tests (règlement des paris, cash out, jeux, flux de cotes)
bun run check:rtp  # taux de redistribution de chaque jeu
```

Copie `.env.example` en `.env` pour configurer. Sans `ODDS_API_KEY`, le site tourne entièrement
sur des **matchs virtuels** : de vraies équipes, des matchs simulés minute par minute, avec score,
horloge, cotes en direct et règlement automatique.

## Paris sportifs

| | |
|---|---|
| Sports | Football, basketball, tennis, rugby, hockey sur glace, MMA |
| Marchés | 1N2, double chance, remboursé si nul, plus/moins (buts, points, sets, jeux), totaux par équipe, handicaps, les deux équipes marquent, score exact, écart de victoire, pair/impair, mi-temps, 1er quart-temps, 1er set, méthode et round de fin (MMA) |
| Direct | Les matchs virtuels se jouent en direct : les cotes sont recalculées toutes les 3 secondes selon le score et le temps restant, et les marchés se suspendent 7 secondes après un but ou un essai |
| Ticket | Simples et combinés (10 sélections, un pronostic par match), option « Accepter les variations de cote » |
| Cash out | Encaissement avant la fin, à 95 % de la valeur estimée du pari (probabilités actuelles), avec confirmation en deux temps |

Chaque pronostic est une clé texte (`ou:2.5:over`, `ah:-1.5:home`, `cs:2-1`…) décrite dans
`src/sports/markets.ts`. La même définition sert à coter et à régler, ce qui garantit que les deux
restent cohérents (vérifié par `tests/models.test.ts`).

### Vrais matchs (The Odds API)

1. Crée une clé gratuite sur [the-odds-api.com](https://the-odds-api.com).
2. Mets-la dans `.env` : `ODDS_API_KEY=ta_cle`.
3. Choisis les compétitions dans `ODDS_SPORTS` ([liste des clés](https://the-odds-api.com/sports-odds-data/sports-apis.html)).
4. Relance `bun run dev` : le terminal affiche le nombre de matchs chargés et les crédits restants.

Avec le flux réel : 1N2 (moyenne des bookmakers européens), double chance et remboursé si nul
calculés à partir du 1N2, et en option plus/moins et handicap (`ODDS_MARKETS=h2h,totals,spreads`).
Les matchs virtuels restent actifs à côté (signalés « (virtuel) ») pour garder le direct ; `VIRTUAL_SPORTS=off` les retire.

**Limites du plan gratuit :** 500 crédits/mois. Avec les réglages par défaut (3 compétitions,
cotes toutes les 6 h, résultats toutes les 2 h si besoin), on consomme environ 400 à 550 crédits
par mois. Chaque marché ou compétition en plus multiplie la consommation. Les cotes réelles ne sont
donc pas mises à jour pendant les matchs : pas de paris en direct ni de cash out après le coup
d'envoi sur ces matchs, seulement avant.

## Casino

| Jeu | Fichier | RTP |
|---|---|---|
| Crash | `src/games/crash.ts` | ≈ 96,5 % |
| Plinko (8, 12 ou 16 rangées, 3 risques) | `src/games/instant.ts` | ≈ 99 % |
| Dice, Limbo | `src/games/instant.ts` | 99 % |
| Roue (3 risques) | `src/games/instant.ts` | 98,3 à 98,7 % |
| Keno (1 à 10 numéros) | `src/games/instant.ts` | 97,5 à 98,6 % |
| Mines, Hi-Lo | `src/games/steps.ts` | 99 % |
| Tower (4 difficultés), Pile ou face | `src/games/steps.ts` | 98 % |
| Baccarat | `src/games/tables.ts` | 98,9 % (banquier) |
| Video poker Jacks or Better 9/6 | `src/games/tables.ts` | 99,5 % en jeu optimal |
| Roulette européenne | `src/games/roulette.ts` | 97,3 % |
| Blackjack (3:2, croupier reste sur 17) | `src/games/blackjack.ts` | — |
| Machine à sous Fruit Frenzy | `src/games/slots.ts` | 93,5 % |

Tous les tirages se font côté serveur (`src/rng.ts`, `crypto.getRandomValues`). Les jeux en plusieurs
étapes (Mines, Hi-Lo, Tower, Pile ou face, Video poker) gardent l'état secret (mines, pièges, paquet)
côté serveur jusqu'à la fin de la partie. Chaque mise et chaque gain sont écrits dans le grand livre
dans la même transaction SQL ; les tests vérifient que le solde est toujours égal à la somme du grand livre.

## Interface

`public/` : HTML, CSS et modules JavaScript natifs, sans outil de build.

| Fichier | Rôle |
|---|---|
| `style.css`, `sports.css`, `games.css` | Thème « salon privé » : noir laqué, ivoire, accent laiton, motif guilloché |
| `fonts/` | Bodoni Moda (titres, scores) et Geist (interface), hébergées localement, licence OFL |
| `js/core.js` | État, appels API, routeur, utilitaires |
| `js/icons.js` | Icônes, illustrations des jeux et motif guilloché, dessinés en SVG |
| `js/sports.js`, `js/markets.js` | Paris sportifs, direct, fiche match, ticket, cash out |
| `js/casino.js`, `js/games/*.js` | Lobby et un module par jeu |
| `js/account.js` | Compte, mouvements du solde, classement |

## À faire avant tout passage en argent réel

Rien de ceci n'est en place, et c'est conditionné à une licence valide pour le pays visé
(en France, l'ANJ n'agrée que les paris sportifs, hippiques et le poker en ligne) :

- RNG certifié par un laboratoire agréé (GLI, eCOGRA, iTech Labs…)
- Fournisseur de cotes en direct sous contrat, et procédure de suspension des marchés
- Prestataire de paiement acceptant les jeux d'argent + KYC / anti-blanchiment
- Géoblocage des pays non couverts par la licence
- Jeu responsable : limites de dépôt/mise, auto-exclusion, vérification de l'âge
- Base de données de production (PostgreSQL), sauvegardes, journal d'audit conforme
