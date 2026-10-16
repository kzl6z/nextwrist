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
| Sports virtuels | 16 sports : football, basketball, tennis, rugby, hockey sur glace, MMA, boxe, handball, volley-ball, tennis de table, badminton, fléchettes, snooker, baseball, football américain, e-sport (Counter-Strike 2) |
| Marchés | 1N2, double chance, remboursé si nul, plus/moins (buts, points, sets, jeux, manches, legs, frames, cartes), totaux par équipe, handicaps, les deux équipes marquent, score exact, écart de victoire, pair/impair, mi-temps, 1er quart-temps, 1er set/manche/carte, méthode et round de fin (MMA, boxe) |
| Direct | Les matchs virtuels se jouent en direct : les cotes sont recalculées toutes les 3 secondes selon le score et le temps restant, et les marchés se suspendent quelques secondes après un but, un essai ou un touchdown |
| Ticket | Simples et combinés (10 sélections, un pronostic par match), option « Accepter les variations de cote » |
| Cash out | Encaissement avant la fin, à 95 % de la valeur estimée du pari (probabilités actuelles), avec confirmation en deux temps |
| Navigation | Filtres par sport et par compétition, compteurs de matchs, recherche côté serveur (adapté à des centaines de matchs réels) |

Chaque pronostic est une clé texte (`ou:2.5:over`, `ah:-1.5:home`, `cs:2-1`…) décrite dans
`src/sports/markets.ts`. La même définition sert à coter et à régler, ce qui garantit que les deux
restent cohérents (vérifié par `tests/models.test.ts`). Les modèles de chaque sport sont dans
`src/sports/models.ts` et `src/sports/models-extra.ts`.

### Vrais matchs (The Odds API)

Flashscore et les sites de résultats similaires interdisent la reprise de leurs données
(conditions d'utilisation) : le site utilise donc **The Odds API**, un fournisseur de cotes prévu pour ça.

1. Crée une clé sur [the-odds-api.com](https://the-odds-api.com) (gratuite ou payante).
2. Dans `.env` : `ODDS_API_KEY=ta_cle` et `ODDS_MONTHLY_CREDITS=` le nombre de crédits de ton abonnement.
3. Choisis les compétitions dans `ODDS_SPORTS` : une liste, ou `all` pour **toutes** celles que le
   fournisseur couvre (football de dizaines de pays, NBA, NHL, NFL, MLB, tennis ATP/WTA, rugby, MMA,
   boxe, cricket, football australien, handball, volley, golf…). La liste est relue toutes les 12 h.
4. Relance `bun run dev` : le terminal affiche les compétitions chargées et les crédits restants.

Marchés des vrais matchs :

- pour tous les matchs : 1N2 (moyenne des bookmakers), double chance et remboursé si nul calculés
  à partir du 1N2, et en option plus/moins et handicap (`ODDS_MARKETS=h2h,totals,spreads`) ;
- sur la fiche d'un match (`ODDS_EXTRA_MARKETS=on`) : les deux équipes marquent, remboursé si nul,
  toutes les lignes alternatives de plus/moins et de handicap, totaux par équipe.

Seuls les marchés qui se règlent avec le score final sont proposés : le fournisseur ne donne ni les
buteurs, ni les corners, ni le score par période, donc ces paris-là restent réservés aux matchs virtuels.

**Budget de crédits.** Le serveur répartit lui-même les crédits du mois (matchs à venir, direct,
marchés supplémentaires, résultats) et ralentit les mises à jour plutôt que de dépasser le budget ;
sous 25 crédits restants, il ne demande plus que les résultats. Ordres de grandeur :

| Abonnement | Réglage conseillé |
|---|---|
| Gratuit, 500 crédits/mois | 2 ou 3 compétitions, `ODDS_LIVE=off` : paris avant le match seulement |
| 20 000 crédits/mois | `ODDS_SPORTS=all`, `ODDS_LIVE=off`, ou direct sur une sélection de compétitions |
| 100 000 crédits/mois | `ODDS_SPORTS=all` et `ODDS_LIVE=on` : direct et cash out sur les vrais matchs, mais le rythme ralentit quand beaucoup de matchs se jouent en même temps |
| 5 000 000 crédits/mois | `ODDS_SPORTS=all`, `ODDS_LIVE=on`, `ODDS_LIVE_SECONDS=30` : direct fluide sur tout le calendrier |

Avec `ODDS_LIVE=on`, un match réel commencé reste ouvert aux paris et au cash out tant que ses cotes
sont fraîches (2 min 30 avec le réglage par défaut) ; si le budget ne permet plus de les rafraîchir,
il est fermé jusqu'au résultat. Sans direct, les vrais matchs ferment au coup d'envoi. Les matchs virtuels restent actifs
à côté (signalés « (virtuel) ») ; `VIRTUAL_SPORTS=off` les retire.

## Casino

28 jeux, en quatre familles.

| Jeu | Fichier | RTP |
|---|---|---|
| Crash | `src/games/crash.ts` | ≈ 96,5 % |
| Plinko (8, 12 ou 16 rangées, 3 risques) | `src/games/instant.ts` | ≈ 99 % |
| Dice, Limbo | `src/games/instant.ts` | 99 % |
| Roue (3 risques) | `src/games/instant.ts` | 98,3 à 98,7 % |
| Keno (1 à 10 numéros) | `src/games/instant.ts` | 97,5 à 98,6 % |
| Mines, Hi-Lo | `src/games/steps.ts` | 99 % |
| Tower (4 difficultés), Pile ou face | `src/games/steps.ts` | 98 % |
| Diamonds | `src/games/more.ts` | 98,3 % |
| Traversée (4 difficultés), Ballon (4 risques) | `src/games/more-steps.ts` | 98 % |
| Penalty (gardien normal ou difficile) | `src/games/more-steps.ts` | 97 % |
| Pierre-feuille-ciseaux | `src/games/more-steps.ts` | 98 % |
| Fléchettes, Coffres (3 risques chacun) | `src/games/more.ts` | 97,9 à 98,3 % |
| Course hippique (gagnant ou placé) | `src/games/more.ts` | ≈ 94 % |
| Baccarat | `src/games/tables.ts` | 98,9 % (banquier) |
| Video poker Jacks or Better 9/6 | `src/games/tables.ts` | 99,5 % en jeu optimal |
| Roulette européenne | `src/games/roulette.ts` | 97,3 % |
| Blackjack (3:2, croupier reste sur 17) | `src/games/blackjack.ts` | — |
| Dragon Tiger | `src/games/more.ts` | 96,3 % (égalité 97,1 %) |
| Sic Bo | `src/games/more.ts` | 97,2 % sur petit/grand, 81 à 92 % sur les autres paris (table de Macao) |
| Three Card Poker | `src/games/more-steps.ts` | 97,7 % (Pair Plus), ≈ 98 % (Ante + Play, jeu optimal) |
| Machine à sous Fruit Frenzy | `src/games/slots.ts` | 93,5 % |
| Machine à sous Nuit dorée (5 rouleaux, 10 lignes) | `src/games/more.ts` | 96,4 % |
| Ticket à gratter | `src/games/more.ts` | 95,5 % |

`bun run check:rtp` recalcule chacun de ces taux (exact quand c'est possible, sinon par simulation).

Tous les tirages se font côté serveur (`src/rng.ts`, `crypto.getRandomValues`). Les jeux en plusieurs
étapes gardent l'état secret (mines, pièges, cartes du croupier, moment où le ballon éclate) côté
serveur jusqu'à la fin de la partie. Chaque mise et chaque gain sont écrits dans le grand livre
dans la même transaction SQL ; les tests vérifient que le solde est toujours égal à la somme du grand livre.

## Interface

`public/` : HTML, CSS et modules JavaScript natifs, sans outil de build.

| Fichier | Rôle |
|---|---|
| `style.css`, `sports.css`, `games.css`, `games-more.css` | Thème « salon privé » : noir laqué, ivoire, accent laiton, motif guilloché |
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
