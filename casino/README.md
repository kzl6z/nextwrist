# Casino — casino + paris sportifs

Base complète en **jetons virtuels** (sans valeur, aucun retrait). Bun + SQLite, aucune dépendance.

## Lancer

```bash
cd casino
bun run dev        # http://localhost:3000
```

Copie `.env.example` en `.env` pour configurer. Sans `ODDS_API_KEY`, des matchs de démo
(vraies équipes, scores simulés) sont générés et joués automatiquement toutes les ~10 min.
Avec une clé [The Odds API](https://the-odds-api.com), les cotes et résultats sont réels.

## Contenu

| Module | Fichier | Détails |
|---|---|---|
| Comptes | `src/auth.ts` | Inscription/connexion, mots de passe hachés, session en cookie HttpOnly |
| Portefeuille | `src/wallet.ts` | Solde + grand livre de toutes les opérations, bonus quotidien |
| Hasard | `src/rng.ts` | `crypto.getRandomValues`, sans biais. Seule source de hasard du projet |
| Roulette | `src/games/roulette.ts` | Européenne, mises pleines et simples/douzaines/colonnes (RTP 97,3 %) |
| Machine à sous | `src/games/slots.ts` | 3 rouleaux pondérés (RTP 93,5 %, vérifiable via `bun run check:rtp`) |
| Blackjack | `src/games/blackjack.ts` | Sabot 6 jeux, croupier reste sur 17, BJ payé 3:2, double |
| Paris sportifs | `src/sports/` | Simples et combinés (10 sélections max), cotes verrouillées à la prise, règlement automatique, remboursement des matchs annulés |

Tout le calcul (tirages, cartes, gains) se fait côté serveur ; chaque mise et son gain sont
écrits dans une même transaction SQL.

## À faire avant tout passage en argent réel

Rien de ceci n'est en place, et c'est conditionné à une licence valide pour le pays visé :

- RNG certifié par un laboratoire agréé (GLI, eCOGRA, iTech Labs…)
- Prestataire de paiement acceptant les jeux d'argent + KYC / anti-blanchiment
- Géoblocage des pays non couverts par la licence
- Jeu responsable : limites de dépôt/mise, auto-exclusion, vérification de l'âge
- Base de données de production (PostgreSQL), sauvegardes, journal d'audit conforme
