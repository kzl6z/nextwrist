// Jeux à tirage unique : Dice, Limbo, Plinko, Roue, Keno.
// Tous les tirages se font ici, côté serveur, avec le RNG du projet.
import { db } from "../db";
import { HttpError } from "../http";
import { randomFloat, randomInt, shuffle } from "../rng";
import { finishRound, floor2, floor4, parseBet, takeBet } from "./common";

/* =========================================================
   Dice : tirage de 0,00 à 99,99, au-dessus ou en dessous d'un seuil
   ========================================================= */
export const DICE_EDGE = 0.99;

export const playDice = db.transaction((userId: number, rawBet: unknown, rawTarget: unknown, rawOver: unknown) => {
  const bet = parseBet(rawBet);
  const target = Math.round(Number(rawTarget) * 100) / 100;
  if (!Number.isFinite(target) || target < 2 || target > 98) throw new HttpError(400, "Seuil entre 2 et 98");
  const over = rawOver === true;
  const chance = over ? (100 - target) / 100 : target / 100;
  const multiplier = floor4(DICE_EDGE / chance);
  takeBet(userId, "dice", bet);
  const roll = randomInt(10_000) / 100;
  const win = over ? roll >= target : roll < target;
  const payout = win ? Math.floor(bet * multiplier) : 0;
  return { roll, win, multiplier, payout, balance: finishRound(userId, "dice", bet, payout) };
});

/* =========================================================
   Limbo : un multiplicateur est tiré, on gagne s'il atteint la cible
   ========================================================= */
export const LIMBO_EDGE = 0.99;
export const LIMBO_MAX = 1_000_000;

export function drawLimbo(): number {
  return Math.min(LIMBO_MAX, Math.max(1, floor2(LIMBO_EDGE / (1 - randomFloat()))));
}

export const playLimbo = db.transaction((userId: number, rawBet: unknown, rawTarget: unknown) => {
  const bet = parseBet(rawBet);
  const target = floor2(Number(rawTarget));
  if (!Number.isFinite(target) || target < 1.01 || target > 10_000) throw new HttpError(400, "Cible entre ×1,01 et ×10 000");
  takeBet(userId, "limbo", bet);
  const result = drawLimbo();
  const win = result >= target;
  const payout = win ? Math.floor(bet * target) : 0;
  return { result, target, win, payout, balance: finishRound(userId, "limbo", bet, payout) };
});

/* =========================================================
   Plinko : une bille rebondit sur N rangées de picots
   ========================================================= */
export type PlinkoRisk = "low" | "medium" | "high";
const sym = (half: number[]) => [...half, ...half.slice(0, -1).reverse()];
export const PLINKO: Record<number, Record<PlinkoRisk, number[]>> = {
  8: {
    low: sym([5.6, 2.1, 1.1, 1, 0.5]),
    medium: sym([13, 3, 1.3, 0.7, 0.4]),
    high: sym([29, 4, 1.5, 0.3, 0.2]),
  },
  12: {
    low: sym([10, 3, 1.6, 1.4, 1.1, 1, 0.5]),
    medium: sym([33, 11, 4, 2, 1.1, 0.6, 0.3]),
    high: sym([170, 24, 8.1, 2, 0.7, 0.2, 0.2]),
  },
  16: {
    low: sym([16, 9, 2, 1.4, 1.4, 1.2, 1.1, 1, 0.5]),
    medium: sym([110, 41, 10, 5, 3, 1.5, 1, 0.5, 0.3]),
    high: sym([1000, 130, 26, 9, 4, 2, 0.2, 0.2, 0.2]),
  },
};

export const playPlinko = db.transaction((userId: number, rawBet: unknown, rawRows: unknown, rawRisk: unknown) => {
  const bet = parseBet(rawBet);
  const rows = Number(rawRows);
  const risk = String(rawRisk) as PlinkoRisk;
  const table = PLINKO[rows]?.[risk];
  if (!table) throw new HttpError(400, "Réglages Plinko invalides");
  takeBet(userId, "plinko", bet);
  // 0 = rebond à gauche, 1 = à droite ; la case d'arrivée est le nombre de rebonds à droite.
  const path = Array.from({ length: rows }, () => randomInt(2));
  const slot = path.reduce((s, x) => s + x, 0);
  const multiplier = table[slot]!;
  const payout = Math.floor(bet * multiplier);
  return { path, slot, multiplier, payout, balance: finishRound(userId, "plinko", bet, payout) };
});

/* =========================================================
   Roue : 30 cases, trois niveaux de risque
   ========================================================= */
export type WheelRisk = "low" | "medium" | "high";
const WHEEL_COMPOSITION: Record<WheelRisk, [number, number][]> = {
  low: [
    [0, 9],
    [1.2, 10],
    [1.5, 9],
    [2, 2],
  ],
  medium: [
    [0, 17],
    [1.6, 5],
    [2, 4],
    [3, 3],
    [4.6, 1],
  ],
  high: [
    [0, 29],
    [29.6, 1],
  ],
};

/** Répartit les multiplicateurs autour de la roue (les gros gains bien espacés). */
function layout(comp: [number, number][]): number[] {
  const slots: (number | null)[] = Array(30).fill(null);
  const sorted = [...comp].filter(([m]) => m > 0).sort((a, b) => b[0] - a[0]);
  for (const [m, n] of sorted) {
    for (let i = 0; i < n; i++) {
      let pos = Math.round(((i + 0.5) * 30) / n + m * 7) % 30;
      while (slots[pos] !== null) pos = (pos + 1) % 30;
      slots[pos] = m;
    }
  }
  return slots.map((s) => s ?? 0);
}
export const WHEEL: Record<WheelRisk, number[]> = {
  low: layout(WHEEL_COMPOSITION.low),
  medium: layout(WHEEL_COMPOSITION.medium),
  high: layout(WHEEL_COMPOSITION.high),
};

export const playWheel = db.transaction((userId: number, rawBet: unknown, rawRisk: unknown) => {
  const bet = parseBet(rawBet);
  const segments = WHEEL[String(rawRisk) as WheelRisk];
  if (!segments) throw new HttpError(400, "Risque invalide");
  takeBet(userId, "wheel", bet);
  const index = randomInt(segments.length);
  const multiplier = segments[index]!;
  const payout = Math.floor(bet * multiplier);
  return { index, multiplier, payout, balance: finishRound(userId, "wheel", bet, payout) };
});

/* =========================================================
   Keno : 40 numéros, 10 tirés, de 1 à 10 choisis
   ========================================================= */
/** KENO[n][k] = multiplicateur avec k numéros trouvés sur n choisis. */
export const KENO: Record<number, number[]> = {
  1: [0.4, 2.7],
  2: [0, 1.8, 5],
  3: [0, 1, 1.65, 26],
  4: [0, 0.5, 1.8, 5.5, 70],
  5: [0, 0.25, 1.4, 4, 14, 110],
  6: [0, 0, 1, 2.8, 7.5, 55, 300],
  7: [0, 0, 0.5, 2, 5.8, 22, 180, 600],
  8: [0, 0, 0, 2, 4, 12, 50, 300, 900],
  9: [0, 0, 0, 1.5, 3, 6.5, 24, 100, 500, 1000],
  10: [0, 0, 0, 1.3, 2.2, 4, 12, 50, 250, 600, 1000],
};

export const playKeno = db.transaction((userId: number, rawBet: unknown, rawPicks: unknown) => {
  const bet = parseBet(rawBet);
  if (!Array.isArray(rawPicks)) throw new HttpError(400, "Choisis tes numéros");
  const picks = [...new Set(rawPicks.map(Number))];
  if (picks.length !== rawPicks.length || picks.length < 1 || picks.length > 10 || !picks.every((n) => Number.isInteger(n) && n >= 1 && n <= 40))
    throw new HttpError(400, "Choisis de 1 à 10 numéros entre 1 et 40");
  takeBet(userId, "keno", bet);
  const drawn = shuffle(Array.from({ length: 40 }, (_, i) => i + 1)).slice(0, 10);
  const hits = picks.filter((n) => drawn.includes(n));
  const multiplier = KENO[picks.length]![hits.length]!;
  const payout = Math.floor(bet * multiplier);
  return { drawn, hits, multiplier, payout, balance: finishRound(userId, "keno", bet, payout) };
});

/** Réglages publics des jeux, pour que l'interface affiche les vraies tables. */
export function casinoConfig() {
  return { plinko: PLINKO, wheel: WHEEL, keno: KENO, diceEdge: DICE_EDGE, limboEdge: LIMBO_EDGE };
}
