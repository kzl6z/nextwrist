// Outils partagés par les jeux de casino : parties en plusieurs étapes,
// historique des parties et règlement des gains.
import { db } from "../db";
import { HttpError } from "../http";
import { shuffle } from "../rng";
import { applyTx, getBalance, parseStake } from "../wallet";

/** Mise maximum sur un jeu de casino. */
export const CASINO_MAX = 10_000;

export const parseBet = (raw: unknown) => parseStake(raw, CASINO_MAX);

/** Arrondi vers le bas à 4 décimales (les multiplicateurs ne sont jamais arrondis en faveur du joueur). */
export const floor4 = (x: number) => Math.floor(x * 10_000 + 1e-7) / 10_000;
export const floor2 = (x: number) => Math.floor(x * 100 + 1e-7) / 100;

export function recordRound(userId: number, game: string, bet: number, payout: number) {
  db.query("INSERT INTO game_rounds (user_id, game, bet, payout, created_at) VALUES (?, ?, ?, ?, ?)").run(
    userId,
    game,
    bet,
    payout,
    Date.now(),
  );
}

/** Mise débitée au début d'une partie. */
export function takeBet(userId: number, game: string, bet: number) {
  applyTx(userId, -bet, `${game}_bet`);
}

/** Fin de partie : crédite le gain éventuel et l'inscrit à l'historique. Renvoie le solde. */
export function finishRound(userId: number, game: string, bet: number, payout: number): number {
  recordRound(userId, game, bet, payout);
  return payout > 0 ? applyTx(userId, payout, `${game}_win`) : getBalance(userId);
}

/* ---------- Parties en plusieurs étapes ---------- */
export function loadSession<T>(userId: number, game: string): T | null {
  const row = db.query("SELECT state FROM game_sessions WHERE user_id = ? AND game = ?").get(userId, game) as
    | { state: string }
    | null;
  return row ? (JSON.parse(row.state) as T) : null;
}

export function saveSession(userId: number, game: string, state: unknown) {
  db.query("INSERT OR REPLACE INTO game_sessions (user_id, game, state) VALUES (?, ?, ?)").run(
    userId,
    game,
    JSON.stringify(state),
  );
}

export function activeSession<T extends { status: string }>(userId: number, game: string): T {
  const s = loadSession<T>(userId, game);
  if (!s || s.status !== "playing") throw new HttpError(400, "Aucune partie en cours");
  return s;
}

export function assertNoActive(userId: number, game: string) {
  if (loadSession<{ status: string }>(userId, game)?.status === "playing")
    throw new HttpError(409, "Une partie est déjà en cours");
}

/* ---------- Cartes ---------- */
export const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
export const SUITS = ["♠", "♥", "♦", "♣"];

export function newDeck(decks = 1): string[] {
  const cards: string[] = [];
  for (let d = 0; d < decks; d++) for (const s of SUITS) for (const r of RANKS) cards.push(r + s);
  return shuffle(cards);
}

/** Rang de 1 (As) à 13 (Roi). */
export const rankOf = (card: string) => RANKS.indexOf(card.slice(0, -1)) + 1;

/* ---------- Historique ---------- */
export function myRounds(userId: number, game: string) {
  return db
    .query("SELECT bet, payout, created_at FROM game_rounds WHERE user_id = ? AND game = ? ORDER BY id DESC LIMIT 12")
    .all(userId, game);
}

/** Derniers gros gains, tous joueurs confondus. */
export function bigWins() {
  return db
    .query(
      `SELECT u.username, r.game, r.bet, r.payout, r.created_at FROM game_rounds r JOIN users u ON u.id = r.user_id
       WHERE r.payout >= r.bet * 2 ORDER BY r.id DESC LIMIT 24`,
    )
    .all();
}
