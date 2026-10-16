// Jeux à tirage unique, deuxième série : Dragon Tiger, Sic Bo, Diamonds, Ticket à gratter,
// Fléchettes, Coffres, Course hippique et machine à sous 5 rouleaux « Nuit dorée ».
// Tous les tirages se font ici, côté serveur.
import { db } from "../db";
import { HttpError } from "../http";
import { randomFloat, randomInt, shuffle, weightedPick } from "../rng";
import { getBalance } from "../wallet";
import { CASINO_MAX, finishRound, floor2, loadSession, newDeck, parseBet, rankOf, saveSession, takeBet } from "./common";

/* =========================================================
   Dragon Tiger : une carte chacun, la plus haute gagne
   ========================================================= */
export const DT_PAYS = {
  dragon: { dragon: 2, tiger: 0, tie: 0.5 },
  tiger: { dragon: 0, tiger: 2, tie: 0.5 },
  tie: { dragon: 0, tiger: 0, tie: 13 },
} as const;

function readBets<K extends string>(raw: unknown, keys: readonly K[]): Record<K, number> {
  const src = (raw ?? {}) as Record<string, unknown>;
  const bets = Object.fromEntries(keys.map((k) => [k, 0])) as Record<K, number>;
  for (const k of keys) {
    const v = src[k];
    if (v === undefined || v === null || v === 0 || v === "") continue;
    bets[k] = parseBet(v);
  }
  const total = keys.reduce((s, k) => s + bets[k], 0);
  if (!total) throw new HttpError(400, "Place au moins une mise");
  if (total > CASINO_MAX) throw new HttpError(400, `Mise totale maximum : ${CASINO_MAX}`);
  return bets;
}

export const playDragonTiger = db.transaction((userId: number, rawBets: unknown) => {
  const bets = readBets(rawBets, ["dragon", "tiger", "tie"] as const);
  const total = bets.dragon + bets.tiger + bets.tie;
  takeBet(userId, "dragontiger", total);
  const shoe = newDeck(8);
  const dragon = shoe.pop()!;
  const tiger = shoe.pop()!;
  const d = rankOf(dragon);
  const t = rankOf(tiger);
  const winner = d > t ? "dragon" : t > d ? "tiger" : "tie";
  let payout = 0;
  for (const k of ["dragon", "tiger", "tie"] as const) payout += Math.floor(bets[k] * DT_PAYS[k][winner]);
  return { dragon, tiger, winner, bets, total, payout, balance: finishRound(userId, "dragontiger", total, payout) };
});

/* =========================================================
   Sic Bo : trois dés
   ========================================================= */
/** Gain (pour 1 misé, mise non comprise) d'un total précis. */
export const SICBO_TOTALS: Record<number, number> = { 4: 60, 5: 30, 6: 17, 7: 12, 8: 8, 9: 6, 10: 6, 11: 6, 12: 6, 13: 8, 14: 12, 15: 17, 16: 30, 17: 60 };

/** Multiplicateur (mise comprise) d'un pari Sic Bo pour un lancer. */
export function sicboPay(type: string, value: number | undefined, dice: number[]): number {
  const sum = dice[0]! + dice[1]! + dice[2]!;
  const triple = dice[0] === dice[1] && dice[1] === dice[2];
  const count = (v: number) => dice.filter((x) => x === v).length;
  switch (type) {
    case "small":
      return !triple && sum >= 4 && sum <= 10 ? 2 : 0;
    case "big":
      return !triple && sum >= 11 && sum <= 17 ? 2 : 0;
    case "odd":
      return !triple && sum % 2 === 1 ? 2 : 0;
    case "even":
      return !triple && sum % 2 === 0 ? 2 : 0;
    case "total":
      return sum === value ? SICBO_TOTALS[value!]! + 1 : 0;
    case "anytriple":
      return triple ? 31 : 0;
    case "triple":
      return triple && dice[0] === value ? 181 : 0;
    case "double":
      return count(value!) >= 2 ? 11 : 0;
    case "single": {
      const n = count(value!);
      return n ? n + 1 : 0;
    }
  }
  return 0;
}

function validSicbo(type: string, value: number | undefined) {
  if (["small", "big", "odd", "even", "anytriple"].includes(type)) return true;
  if (type === "total") return Number.isInteger(value) && value! >= 4 && value! <= 17;
  if (["triple", "double", "single"].includes(type)) return Number.isInteger(value) && value! >= 1 && value! <= 6;
  return false;
}

export const playSicbo = db.transaction((userId: number, rawBets: unknown) => {
  if (!Array.isArray(rawBets) || !rawBets.length || rawBets.length > 60) throw new HttpError(400, "Aucune mise");
  const bets = rawBets.map((b: any) => {
    const type = String(b?.type);
    const value = b?.value === undefined ? undefined : Number(b.value);
    if (!validSicbo(type, value)) throw new HttpError(400, `Mise invalide : ${type}`);
    return { type, value, amount: parseBet(b?.amount) };
  });
  const total = bets.reduce((s, b) => s + b.amount, 0);
  if (total > CASINO_MAX) throw new HttpError(400, `Mise totale maximum : ${CASINO_MAX}`);
  takeBet(userId, "sicbo", total);
  const dice = [1 + randomInt(6), 1 + randomInt(6), 1 + randomInt(6)];
  const results = bets.map((b) => ({ ...b, win: Math.floor(b.amount * sicboPay(b.type, b.value, dice)) }));
  const payout = results.reduce((s, b) => s + b.win, 0);
  return { dice, bets: results, total, payout, balance: finishRound(userId, "sicbo", total, payout) };
});

/* =========================================================
   Diamonds : cinq gemmes parmi sept couleurs
   ========================================================= */
export const DIAMOND_COLORS = 7;
export const DIAMOND_PAYS: [string, string, number][] = [
  ["five", "Cinq identiques", 50],
  ["four", "Quatre identiques", 5],
  ["full", "Full", 4],
  ["three", "Trois identiques", 3],
  ["twopair", "Deux paires", 2],
  ["pair", "Une paire", 0.1],
  ["none", "Rien", 0],
];

export function diamondHand(gems: number[]): string {
  const counts = [...gems.reduce((m, g) => m.set(g, (m.get(g) ?? 0) + 1), new Map<number, number>()).values()].sort((a, b) => b - a);
  if (counts[0] === 5) return "five";
  if (counts[0] === 4) return "four";
  if (counts[0] === 3 && counts[1] === 2) return "full";
  if (counts[0] === 3) return "three";
  if (counts[0] === 2 && counts[1] === 2) return "twopair";
  if (counts[0] === 2) return "pair";
  return "none";
}

export const playDiamonds = db.transaction((userId: number, rawBet: unknown) => {
  const bet = parseBet(rawBet);
  takeBet(userId, "diamonds", bet);
  const gems = Array.from({ length: 5 }, () => randomInt(DIAMOND_COLORS));
  const hand = diamondHand(gems);
  const multiplier = DIAMOND_PAYS.find(([k]) => k === hand)![2];
  const payout = Math.floor(bet * multiplier);
  return { gems, hand, multiplier, payout, balance: finishRound(userId, "diamonds", bet, payout) };
});

/* =========================================================
   Ticket à gratter : trois symboles identiques sur neuf cases
   ========================================================= */
/** [symbole, multiplicateur, probabilité]. Le reste du temps, le ticket est perdant. */
export const SCRATCH_PRIZES: [string, number, number][] = [
  ["crown", 1000, 0.00005],
  ["diamond", 100, 0.0006],
  ["seven", 20, 0.006],
  ["bell", 10, 0.015],
  ["clover", 5, 0.035],
  ["cherry", 2, 0.1],
  ["coin", 1, 0.2],
];
const SCRATCH_SYMBOLS = SCRATCH_PRIZES.map(([s]) => s);

/** Grille de 9 symboles avec exactement un triplé (le gain) ou aucun. */
function scratchGrid(prize: string | null): string[] {
  for (;;) {
    const cells: string[] = [];
    if (prize) cells.push(prize, prize, prize);
    // Les autres symboles apparaissent au plus deux fois chacun.
    const others = shuffle(SCRATCH_SYMBOLS.filter((s) => s !== prize).flatMap((s) => [s, s]));
    while (cells.length < 9) cells.push(others.pop()!);
    const grid = shuffle(cells);
    const triples = SCRATCH_SYMBOLS.filter((s) => grid.filter((c) => c === s).length >= 3);
    if (triples.length === (prize ? 1 : 0)) return grid;
  }
}

export const playScratch = db.transaction((userId: number, rawBet: unknown) => {
  const bet = parseBet(rawBet);
  takeBet(userId, "scratch", bet);
  let r = randomFloat();
  let prize: [string, number, number] | null = null;
  for (const p of SCRATCH_PRIZES) {
    if (r < p[2]) {
      prize = p;
      break;
    }
    r -= p[2];
  }
  const grid = scratchGrid(prize?.[0] ?? null);
  const multiplier = prize?.[1] ?? 0;
  const payout = Math.floor(bet * multiplier);
  return { grid, symbol: prize?.[0] ?? null, multiplier, payout, balance: finishRound(userId, "scratch", bet, payout) };
});

/* =========================================================
   Fléchettes : la zone touchée donne le multiplicateur
   ========================================================= */
export type DartsRisk = "low" | "medium" | "high";
/** Zones de la cible, du centre vers l'extérieur : [multiplicateur, poids sur 1000]. */
export const DARTS: Record<DartsRisk, [number, number][]> = {
  low: [
    [5, 20],
    [2, 80],
    [1.5, 170],
    [1.2, 250],
    [0.6, 280],
    [0, 200],
  ],
  medium: [
    [12, 15],
    [4, 50],
    [2, 120],
    [1.2, 230],
    [0.3, 280],
    [0, 305],
  ],
  high: [
    [60, 5],
    [12, 20],
    [3, 70],
    [1.5, 135],
    [0.3, 100],
    [0, 670],
  ],
};

export const playDarts = db.transaction((userId: number, rawBet: unknown, rawRisk: unknown) => {
  const bet = parseBet(rawBet);
  const zones = DARTS[String(rawRisk) as DartsRisk];
  if (!zones) throw new HttpError(400, "Risque invalide");
  takeBet(userId, "darts", bet);
  const ring = weightedPick(zones.map(([, w], i) => [i, w] as const));
  const multiplier = zones[ring]![0];
  const payout = Math.floor(bet * multiplier);
  // Position décorative de la fléchette dans l'anneau touché (angle libre).
  const angle = randomFloat() * 360;
  return { ring, angle, multiplier, payout, balance: finishRound(userId, "darts", bet, payout) };
});

/* =========================================================
   Coffres : un coffre s'ouvre sur un multiplicateur
   ========================================================= */
export type ChestRisk = "low" | "medium" | "high";
export const CHESTS: Record<ChestRisk, [number, number][]> = {
  low: [
    [0.2, 200],
    [0.5, 250],
    [0.9, 240],
    [1.2, 170],
    [1.8, 80],
    [3, 50],
    [10, 10],
  ],
  medium: [
    [0, 423],
    [0.4, 200],
    [1, 190],
    [2, 110],
    [4, 60],
    [10, 15],
    [50, 2],
  ],
  high: [
    [0, 689.6],
    [0.5, 200],
    [2, 60],
    [5, 40],
    [20, 8],
    [100, 2],
    [500, 0.4],
  ],
};

export const playChest = db.transaction((userId: number, rawBet: unknown, rawRisk: unknown) => {
  const bet = parseBet(rawBet);
  const table = CHESTS[String(rawRisk) as ChestRisk];
  if (!table) throw new HttpError(400, "Risque invalide");
  takeBet(userId, "chest", bet);
  const total = table.reduce((s, [, w]) => s + w, 0);
  let r = randomFloat() * total;
  let index = table.length - 1;
  for (let i = 0; i < table.length; i++) {
    if (r < table[i]![1]) {
      index = i;
      break;
    }
    r -= table[i]![1];
  }
  const multiplier = table[index]![0];
  const payout = Math.floor(bet * multiplier);
  return { index, multiplier, payout, balance: finishRound(userId, "chest", bet, payout) };
});

/* =========================================================
   Course hippique virtuelle : six chevaux, cotes affichées avant le départ
   ========================================================= */
const HORSE_NAMES = [
  "Éclair d'Or",
  "Belle de Chantilly",
  "Roi du Vent",
  "Nuit Blanche",
  "Comète",
  "Sirocco",
  "Mistral",
  "Duchesse",
  "Tonnerre",
  "Prince d'Oise",
  "Valse Lente",
  "Fleur de Sel",
  "Orage",
  "Bel Ami",
  "Étoile Filante",
  "Grand Large",
];
const RACE_MARGIN = 0.94;

interface RaceCard {
  horses: { name: string; p: number; win: number; place: number }[];
}

/** Probabilité de finir dans les deux premiers (modèle de Plackett-Luce). */
export function placeProb(p: number[], i: number) {
  let s = p[i]!;
  for (let j = 0; j < p.length; j++) if (j !== i) s += (p[j]! * p[i]!) / (1 - p[j]!);
  return s;
}

export function newRace(): RaceCard {
  const names = shuffle([...HORSE_NAMES]).slice(0, 6);
  const strength = names.map(() => Math.exp(randomFloat() * 1.6));
  const total = strength.reduce((s, x) => s + x, 0);
  const p = strength.map((x) => x / total);
  return {
    horses: names.map((name, i) => ({
      name,
      p: p[i]!,
      win: floor2(RACE_MARGIN / p[i]!),
      place: Math.max(1.01, floor2(RACE_MARGIN / placeProb(p, i))),
    })),
  };
}

const racePublic = (card: RaceCard) => card.horses.map(({ name, win, place }) => ({ name, win, place }));

export function getRace(userId: number) {
  let card = loadSession<RaceCard>(userId, "race");
  if (!card) {
    card = newRace();
    saveSession(userId, "race", card);
  }
  return { horses: racePublic(card), balance: getBalance(userId) };
}

export const playRace = db.transaction((userId: number, rawBet: unknown, rawHorse: unknown, rawType: unknown) => {
  const card = loadSession<RaceCard>(userId, "race") ?? newRace();
  const bet = parseBet(rawBet);
  const horse = Number(rawHorse);
  const type = String(rawType);
  if (!Number.isInteger(horse) || horse < 0 || horse >= card.horses.length) throw new HttpError(400, "Cheval invalide");
  if (type !== "win" && type !== "place") throw new HttpError(400, "Type de pari invalide");
  takeBet(userId, "race", bet);
  // Ordre d'arrivée tiré selon les forces (Plackett-Luce).
  const order: number[] = [];
  const left = card.horses.map((h, i) => [i, h.p] as [number, number]);
  while (left.length) {
    const total = left.reduce((s, [, p]) => s + p, 0);
    let r = randomFloat() * total;
    let k = left.length - 1;
    for (let j = 0; j < left.length; j++) {
      if (r < left[j]![1]) {
        k = j;
        break;
      }
      r -= left[j]![1];
    }
    order.push(left[k]![0]);
    left.splice(k, 1);
  }
  const rank = order.indexOf(horse);
  const won = type === "win" ? rank === 0 : rank <= 1;
  const odds = type === "win" ? card.horses[horse]!.win : card.horses[horse]!.place;
  const payout = won ? Math.floor(bet * odds) : 0;
  const result = { order, horses: racePublic(card), horse, type, odds, won, payout };
  // Nouvelle course pour la suite.
  const next = newRace();
  saveSession(userId, "race", next);
  return { ...result, next: racePublic(next), balance: finishRound(userId, "race", bet, payout) };
});

/* =========================================================
   Nuit dorée : machine à sous 5 rouleaux × 3 rangées, 10 lignes
   ========================================================= */
/** Symboles et poids (identiques sur chaque rouleau). W = joker, S = étoile (scatter). */
export const SLOT5_WEIGHTS: [string, number][] = [
  ["10", 24],
  ["J", 22],
  ["Q", 20],
  ["K", 17],
  ["A", 15],
  ["bell", 9],
  ["crown", 7],
  ["gem", 5],
  ["W", 3],
  ["S", 4],
];
/** Gains par ligne (× mise par ligne) pour 3, 4 et 5 symboles alignés depuis la gauche. */
export const SLOT5_PAYS: Record<string, [number, number, number]> = {
  "10": [15, 30, 100],
  J: [15, 35, 110],
  Q: [16, 45, 140],
  K: [20, 60, 180],
  A: [25, 80, 250],
  bell: [50, 200, 600],
  crown: [75, 300, 1000],
  gem: [120, 500, 2000],
  W: [250, 1250, 5000],
};
/** Étoiles n'importe où (× mise totale). */
export const SLOT5_SCATTER: Record<number, number> = { 3: 4, 4: 20, 5: 100 };
export const SLOT5_LINES: number[][] = [
  [1, 1, 1, 1, 1],
  [0, 0, 0, 0, 0],
  [2, 2, 2, 2, 2],
  [0, 1, 2, 1, 0],
  [2, 1, 0, 1, 2],
  [0, 0, 1, 2, 2],
  [2, 2, 1, 0, 0],
  [1, 0, 0, 0, 1],
  [1, 2, 2, 2, 1],
  [0, 1, 1, 1, 0],
];

/** Gain d'une ligne (× mise par ligne) : symboles identiques depuis la gauche, le joker remplace tout sauf l'étoile. */
export function slot5LinePay(symbols: string[]): { pay: number; symbol: string | null; count: number } {
  let best = { pay: 0, symbol: null as string | null, count: 0 };
  // Joker seul : suite de jokers depuis la gauche.
  let w = 0;
  while (w < 5 && symbols[w] === "W") w++;
  if (w >= 3) best = { pay: SLOT5_PAYS.W![w - 3]!, symbol: "W", count: w };
  const target = symbols.find((s) => s !== "W");
  if (target && target !== "S") {
    let n = 0;
    while (n < 5 && (symbols[n] === target || symbols[n] === "W")) n++;
    if (n >= 3 && SLOT5_PAYS[target]![n - 3]! > best.pay) best = { pay: SLOT5_PAYS[target]![n - 3]!, symbol: target, count: n };
  }
  return best;
}

export const playSlot5 = db.transaction((userId: number, rawBet: unknown) => {
  const bet = parseBet(rawBet);
  if (bet < 10 || bet % 10 !== 0) throw new HttpError(400, "Mise par multiples de 10 (une part par ligne)");
  takeBet(userId, "slot5", bet);
  const lineBet = bet / 10;
  // grid[rouleau][rangée]
  const grid = Array.from({ length: 5 }, () => Array.from({ length: 3 }, () => weightedPick(SLOT5_WEIGHTS)));
  const wins: { line: number; symbol: string; count: number; win: number }[] = [];
  SLOT5_LINES.forEach((rows, line) => {
    const r = slot5LinePay(rows.map((row, reel) => grid[reel]![row]!));
    if (r.pay) wins.push({ line, symbol: r.symbol!, count: r.count, win: Math.floor(r.pay * lineBet) });
  });
  const scatters = grid.flat().filter((s) => s === "S").length;
  const scatterWin = Math.floor(bet * (SLOT5_SCATTER[Math.min(5, scatters)] ?? 0));
  const payout = wins.reduce((s, w) => s + w.win, 0) + scatterWin;
  return { grid, wins, scatters, scatterWin, payout, balance: finishRound(userId, "slot5", bet, payout) };
});

/** Réglages publics de cette série de jeux. */
export function moreConfig() {
  return {
    sicboTotals: SICBO_TOTALS,
    diamonds: DIAMOND_PAYS,
    scratch: SCRATCH_PRIZES.map(([s, m]) => [s, m]),
    darts: DARTS,
    chests: CHESTS,
    slot5: { pays: SLOT5_PAYS, scatter: SLOT5_SCATTER, lines: SLOT5_LINES },
  };
}
