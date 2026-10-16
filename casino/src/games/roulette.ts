import { db } from "../db";
import { HttpError } from "../http";
import { randomInt } from "../rng";
import { applyTx, getBalance, MAX_STAKE, parseStake } from "../wallet";
import { recordRound } from "./common";

// Roulette européenne (un seul zéro).
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);

export type RouletteBet = { type: string; value?: number; amount: number };

export function colorOf(n: number): "green" | "red" | "black" {
  return n === 0 ? "green" : RED.has(n) ? "red" : "black";
}

/** Multiplicateur de paiement mise comprise (0 = perdu). */
function payout(bet: RouletteBet, n: number): number {
  switch (bet.type) {
    case "number":
      return n === bet.value ? 36 : 0;
    case "red":
      return colorOf(n) === "red" ? 2 : 0;
    case "black":
      return colorOf(n) === "black" ? 2 : 0;
    case "even":
      return n !== 0 && n % 2 === 0 ? 2 : 0;
    case "odd":
      return n % 2 === 1 ? 2 : 0;
    case "low":
      return n >= 1 && n <= 18 ? 2 : 0;
    case "high":
      return n >= 19 ? 2 : 0;
    case "dozen":
      return n !== 0 && Math.ceil(n / 12) === bet.value ? 3 : 0;
    case "column":
      return n !== 0 && ((n - 1) % 3) + 1 === bet.value ? 3 : 0;
    default:
      return 0;
  }
}

function validate(raw: unknown): RouletteBet[] {
  if (!Array.isArray(raw) || raw.length === 0 || raw.length > 50) throw new HttpError(400, "Aucune mise");
  return raw.map((b: any) => {
    const amount = parseStake(b?.amount);
    const type = String(b?.type);
    const value = b?.value === undefined ? undefined : Number(b.value);
    const ok =
      ["red", "black", "even", "odd", "low", "high"].includes(type) ||
      (type === "number" && Number.isInteger(value) && value! >= 0 && value! <= 36) ||
      ((type === "dozen" || type === "column") && [1, 2, 3].includes(value!));
    if (!ok) throw new HttpError(400, `Mise invalide : ${type}`);
    return { type, value, amount };
  });
}

export const spinRoulette = db.transaction((userId: number, rawBets: unknown) => {
  const bets = validate(rawBets);
  const totalBet = bets.reduce((s, b) => s + b.amount, 0);
  if (totalBet > MAX_STAKE) throw new HttpError(400, `Mise totale maximum : ${MAX_STAKE}`);

  applyTx(userId, -totalBet, "roulette_bet");
  const number = randomInt(37);
  const results = bets.map((b) => ({ ...b, win: b.amount * payout(b, number) }));
  const totalWin = results.reduce((s, b) => s + b.win, 0);
  const balance = totalWin > 0 ? applyTx(userId, totalWin, "roulette_win") : getBalance(userId);
  recordRound(userId, "roulette", totalBet, totalWin);

  return {
    number,
    color: colorOf(number),
    bets: results,
    totalBet,
    totalWin,
    balance,
  };
});
