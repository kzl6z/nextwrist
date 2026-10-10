import { db } from "./db";
import { HttpError } from "./http";

export const MAX_STAKE = 100_000;
export const DAILY_BONUS = 500;
const DAY = 86_400_000;

/**
 * Applique un mouvement de solde (positif = crédit, négatif = débit) et l'écrit
 * dans le grand livre. À appeler dans une db.transaction quand d'autres
 * écritures doivent rester cohérentes avec ce mouvement.
 */
export function applyTx(userId: number, amount: number, kind: string, ref?: string): number {
  if (!Number.isSafeInteger(amount)) throw new Error(`montant invalide: ${amount}`);
  const row = db
    .query("UPDATE users SET balance = balance + ?1 WHERE id = ?2 AND balance + ?1 >= 0 RETURNING balance")
    .get(amount, userId) as { balance: number } | null;
  if (!row) throw new HttpError(400, "Solde insuffisant");
  db.query(
    "INSERT INTO transactions (user_id, amount, balance_after, kind, ref, created_at) VALUES (?, ?, ?, ?, ?, ?)",
  ).run(userId, amount, row.balance, kind, ref ?? null, Date.now());
  return row.balance;
}

export function parseStake(value: unknown, max = MAX_STAKE): number {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) throw new HttpError(400, "Mise invalide");
  if (n > max) throw new HttpError(400, `Mise maximum : ${max}`);
  return n;
}

export function getBalance(userId: number): number {
  return (db.query("SELECT balance FROM users WHERE id = ?").get(userId) as { balance: number }).balance;
}

export function nextBonusAt(lastBonusAt: number | null): number {
  return lastBonusAt ? lastBonusAt + DAY : 0;
}

export const claimDailyBonus = db.transaction((userId: number) => {
  const { last_bonus_at } = db.query("SELECT last_bonus_at FROM users WHERE id = ?").get(userId) as {
    last_bonus_at: number | null;
  };
  const now = Date.now();
  if (nextBonusAt(last_bonus_at) > now) throw new HttpError(429, "Bonus déjà récupéré, reviens plus tard");
  db.query("UPDATE users SET last_bonus_at = ? WHERE id = ?").run(now, userId);
  return applyTx(userId, DAILY_BONUS, "daily_bonus");
});

export function listTransactions(userId: number) {
  return db
    .query(
      "SELECT amount, balance_after, kind, ref, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 50",
    )
    .all(userId);
}

export function leaderboard() {
  return db.query("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10").all();
}
