import { db } from "../db";
import { weightedPick } from "../rng";
import { applyTx, getBalance, parseStake } from "../wallet";

// Rouleaux pondérés : [symbole, poids, gain pour 3 identiques (× mise)].
export const SYMBOLS = [
  ["🍒", 6, 8],
  ["🍋", 5, 15],
  ["🍊", 4, 25],
  ["🍇", 3, 50],
  ["🔔", 2, 100],
  ["💎", 1, 500],
] as const;

const WEIGHTS = SYMBOLS.map(([s, w]) => [s, w] as const);
const TRIPLE = new Map<string, number>(SYMBOLS.map(([s, , m]) => [s, m]));
/** Exactement deux cerises : rembourse la moitié de la mise. */
const TWO_CHERRIES = 0.5;

export function slotMultiplier(reels: string[]): number {
  if (reels[0] === reels[1] && reels[1] === reels[2]) return TRIPLE.get(reels[0]!)!;
  if (reels.filter((s) => s === "🍒").length === 2) return TWO_CHERRIES;
  return 0;
}

export const spinSlots = db.transaction((userId: number, rawBet: unknown) => {
  const bet = parseStake(rawBet, 10_000);
  applyTx(userId, -bet, "slots_bet");
  const reels = [0, 1, 2].map(() => weightedPick(WEIGHTS));
  const multiplier = slotMultiplier(reels);
  const win = Math.floor(bet * multiplier);
  const balance = win > 0 ? applyTx(userId, win, "slots_win") : getBalance(userId);
  return { reels, multiplier, bet, win, balance };
});
