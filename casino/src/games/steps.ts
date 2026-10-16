// Jeux en plusieurs étapes, où l'on peut encaisser à tout moment :
// Mines, Hi-Lo, Tower, Pile ou face. L'état (mines, pièges, cartes) reste côté serveur.
import { db } from "../db";
import { HttpError } from "../http";
import { randomInt, shuffle } from "../rng";
import { getBalance } from "../wallet";
import {
  activeSession,
  assertNoActive,
  finishRound,
  floor4,
  loadSession,
  parseBet,
  RANKS,
  SUITS,
  saveSession,
  takeBet,
} from "./common";

type Status = "playing" | "won" | "lost";

/* =========================================================
   Mines : grille 5×5, éviter les mines
   ========================================================= */
const MINES_EDGE = 0.99;
const CELLS = 25;

interface MinesState {
  status: Status;
  bet: number;
  mines: number;
  bombs: number[];
  revealed: number[];
  payout: number;
}

export function minesMultiplier(mines: number, safe: number): number {
  let m = MINES_EDGE;
  for (let i = 0; i < safe; i++) m *= (CELLS - i) / (CELLS - mines - i);
  return safe === 0 ? 1 : floor4(m);
}

function minesView(s: MinesState) {
  const playing = s.status === "playing";
  return {
    status: s.status,
    bet: s.bet,
    mines: s.mines,
    revealed: s.revealed,
    // Les mines ne sont révélées qu'à la fin de la partie.
    bombs: playing ? undefined : s.bombs,
    multiplier: minesMultiplier(s.mines, s.revealed.length),
    next: minesMultiplier(s.mines, s.revealed.length + 1),
    payout: s.payout,
  };
}

const minesResponse = (userId: number, s: MinesState | null) => ({
  game: s ? minesView(s) : null,
  balance: getBalance(userId),
});

export const getMines = (userId: number) => minesResponse(userId, loadSession<MinesState>(userId, "mines"));

export const startMines = db.transaction((userId: number, rawBet: unknown, rawMines: unknown) => {
  assertNoActive(userId, "mines");
  const bet = parseBet(rawBet);
  const mines = Number(rawMines);
  if (!Number.isInteger(mines) || mines < 1 || mines > 24) throw new HttpError(400, "De 1 à 24 mines");
  takeBet(userId, "mines", bet);
  const bombs = shuffle(Array.from({ length: CELLS }, (_, i) => i)).slice(0, mines);
  const s: MinesState = { status: "playing", bet, mines, bombs, revealed: [], payout: 0 };
  saveSession(userId, "mines", s);
  return minesResponse(userId, s);
});

function cashMines(userId: number, s: MinesState) {
  s.status = "won";
  s.payout = Math.floor(s.bet * minesMultiplier(s.mines, s.revealed.length));
  finishRound(userId, "mines", s.bet, s.payout);
}

export const revealMines = db.transaction((userId: number, rawCell: unknown) => {
  const s = activeSession<MinesState>(userId, "mines");
  const cell = Number(rawCell);
  if (!Number.isInteger(cell) || cell < 0 || cell >= CELLS) throw new HttpError(400, "Case invalide");
  if (s.revealed.includes(cell)) throw new HttpError(400, "Case déjà retournée");
  s.revealed.push(cell);
  if (s.bombs.includes(cell)) {
    s.status = "lost";
    finishRound(userId, "mines", s.bet, 0);
  } else if (s.revealed.length === CELLS - s.mines) cashMines(userId, s);
  saveSession(userId, "mines", s);
  return { ...minesResponse(userId, s), hit: s.bombs.includes(cell) };
});

export const cashoutMines = db.transaction((userId: number) => {
  const s = activeSession<MinesState>(userId, "mines");
  if (!s.revealed.length) throw new HttpError(400, "Retourne au moins une case");
  cashMines(userId, s);
  saveSession(userId, "mines", s);
  return minesResponse(userId, s);
});

/* =========================================================
   Hi-Lo : la carte suivante sera-t-elle plus haute ou plus basse ?
   ========================================================= */
const HILO_EDGE = 0.99;
const randomCard = () => RANKS[randomInt(13)]! + SUITS[randomInt(4)]!;
const rank = (card: string) => RANKS.indexOf(card.slice(0, -1)) + 1;

/** Probabilité de gagner avec « plus haut » (hi) ou « plus bas » (lo) depuis le rang r. */
export function hiloChance(r: number, dir: "hi" | "lo"): number {
  if (r === 1) return dir === "hi" ? 12 / 13 : 1 / 13; // As : plus haut, ou égal
  if (r === 13) return dir === "lo" ? 12 / 13 : 1 / 13; // Roi : plus bas, ou égal
  return dir === "hi" ? (14 - r) / 13 : r / 13; // « ou égal » inclus
}
function hiloWins(r: number, next: number, dir: "hi" | "lo"): boolean {
  if (r === 1) return dir === "hi" ? next > 1 : next === 1;
  if (r === 13) return dir === "lo" ? next < 13 : next === 13;
  return dir === "hi" ? next >= r : next <= r;
}

interface HiloState {
  status: Status;
  bet: number;
  card: string;
  /** Produit des 1/p des pronostics réussis. */
  fair: number;
  steps: number;
  history: { card: string; dir: string; ok: boolean }[];
  payout: number;
}

const hiloMult = (s: HiloState) => (s.steps ? floor4(s.fair * HILO_EDGE) : 1);

function hiloResponse(userId: number, s: HiloState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  const r = rank(s.card);
  return {
    game: {
      status: s.status,
      bet: s.bet,
      card: s.card,
      history: s.history,
      multiplier: hiloMult(s),
      payout: s.payout,
      steps: s.steps,
      odds: {
        hi: { chance: hiloChance(r, "hi"), multiplier: floor4(s.fair * HILO_EDGE / hiloChance(r, "hi")) },
        lo: { chance: hiloChance(r, "lo"), multiplier: floor4(s.fair * HILO_EDGE / hiloChance(r, "lo")) },
      },
    },
    balance: getBalance(userId),
  };
}

export const getHilo = (userId: number) => hiloResponse(userId, loadSession<HiloState>(userId, "hilo"));

export const startHilo = db.transaction((userId: number, rawBet: unknown) => {
  assertNoActive(userId, "hilo");
  const bet = parseBet(rawBet);
  takeBet(userId, "hilo", bet);
  const s: HiloState = { status: "playing", bet, card: randomCard(), fair: 1, steps: 0, history: [], payout: 0 };
  saveSession(userId, "hilo", s);
  return hiloResponse(userId, s);
});

export const guessHilo = db.transaction((userId: number, rawDir: unknown) => {
  const s = activeSession<HiloState>(userId, "hilo");
  const dir = String(rawDir);
  if (dir !== "hi" && dir !== "lo" && dir !== "skip") throw new HttpError(400, "Choix invalide");
  const next = randomCard();
  if (dir === "skip") {
    if (s.history.filter((h) => h.dir === "skip").length >= 52) throw new HttpError(400, "Trop de cartes passées");
    s.history.push({ card: s.card, dir, ok: true });
  } else {
    const r = rank(s.card);
    const ok = hiloWins(r, rank(next), dir);
    s.history.push({ card: s.card, dir, ok });
    if (ok) {
      s.fair /= hiloChance(r, dir);
      s.steps++;
    } else {
      s.status = "lost";
      finishRound(userId, "hilo", s.bet, 0);
    }
  }
  s.card = next;
  saveSession(userId, "hilo", s);
  return hiloResponse(userId, s);
});

export const cashoutHilo = db.transaction((userId: number) => {
  const s = activeSession<HiloState>(userId, "hilo");
  if (!s.steps) throw new HttpError(400, "Fais au moins un pronostic");
  s.status = "won";
  s.payout = Math.floor(s.bet * hiloMult(s));
  finishRound(userId, "hilo", s.bet, s.payout);
  saveSession(userId, "hilo", s);
  return hiloResponse(userId, s);
});

/* =========================================================
   Tower : 8 étages, une case sûre à trouver par étage
   ========================================================= */
const TOWER_EDGE = 0.98;
const TOWER_LEVELS = 8;
export const TOWER: Record<string, { cols: number; traps: number }> = {
  easy: { cols: 4, traps: 1 },
  medium: { cols: 3, traps: 1 },
  hard: { cols: 2, traps: 1 },
  expert: { cols: 3, traps: 2 },
};

interface TowerState {
  status: Status;
  bet: number;
  difficulty: string;
  /** traps[étage] = colonnes piégées. */
  traps: number[][];
  picks: number[];
  payout: number;
}

export function towerMultiplier(difficulty: string, level: number): number {
  const { cols, traps } = TOWER[difficulty]!;
  return level === 0 ? 1 : floor4(TOWER_EDGE * (cols / (cols - traps)) ** level);
}

function towerResponse(userId: number, s: TowerState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  return {
    game: {
      status: s.status,
      bet: s.bet,
      difficulty: s.difficulty,
      picks: s.picks,
      traps: s.status === "playing" ? undefined : s.traps,
      multiplier: towerMultiplier(s.difficulty, s.picks.length),
      ladder: Array.from({ length: TOWER_LEVELS }, (_, i) => towerMultiplier(s.difficulty, i + 1)),
      payout: s.payout,
    },
    balance: getBalance(userId),
  };
}

export const getTower = (userId: number) => towerResponse(userId, loadSession<TowerState>(userId, "tower"));

export const startTower = db.transaction((userId: number, rawBet: unknown, rawDifficulty: unknown) => {
  assertNoActive(userId, "tower");
  const bet = parseBet(rawBet);
  const difficulty = String(rawDifficulty);
  const conf = TOWER[difficulty];
  if (!conf) throw new HttpError(400, "Difficulté invalide");
  takeBet(userId, "tower", bet);
  const traps = Array.from({ length: TOWER_LEVELS }, () =>
    shuffle(Array.from({ length: conf.cols }, (_, i) => i)).slice(0, conf.traps),
  );
  const s: TowerState = { status: "playing", bet, difficulty, traps, picks: [], payout: 0 };
  saveSession(userId, "tower", s);
  return towerResponse(userId, s);
});

function cashTower(userId: number, s: TowerState) {
  s.status = "won";
  s.payout = Math.floor(s.bet * towerMultiplier(s.difficulty, s.picks.length));
  finishRound(userId, "tower", s.bet, s.payout);
}

export const pickTower = db.transaction((userId: number, rawCol: unknown) => {
  const s = activeSession<TowerState>(userId, "tower");
  const col = Number(rawCol);
  if (!Number.isInteger(col) || col < 0 || col >= TOWER[s.difficulty]!.cols) throw new HttpError(400, "Case invalide");
  const level = s.picks.length;
  s.picks.push(col);
  if (s.traps[level]!.includes(col)) {
    s.status = "lost";
    finishRound(userId, "tower", s.bet, 0);
  } else if (s.picks.length === TOWER_LEVELS) cashTower(userId, s);
  saveSession(userId, "tower", s);
  return towerResponse(userId, s);
});

export const cashoutTower = db.transaction((userId: number) => {
  const s = activeSession<TowerState>(userId, "tower");
  if (!s.picks.length) throw new HttpError(400, "Monte au moins un étage");
  cashTower(userId, s);
  saveSession(userId, "tower", s);
  return towerResponse(userId, s);
});

/* =========================================================
   Pile ou face : enchaîne les bons choix, multiplicateur ×2 à chaque fois
   ========================================================= */
const COIN_EDGE = 0.98;
const COIN_MAX_FLIPS = 20;

interface CoinState {
  status: Status;
  bet: number;
  flips: { side: string; result: string }[];
  streak: number;
  payout: number;
}

const coinMult = (streak: number) => (streak ? floor4(COIN_EDGE * 2 ** streak) : 1);

function coinResponse(userId: number, s: CoinState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  return {
    game: {
      status: s.status,
      bet: s.bet,
      flips: s.flips,
      streak: s.streak,
      multiplier: coinMult(s.streak),
      next: coinMult(s.streak + 1),
      payout: s.payout,
    },
    balance: getBalance(userId),
  };
}

export const getCoin = (userId: number) => coinResponse(userId, loadSession<CoinState>(userId, "coinflip"));

function flip(userId: number, s: CoinState, rawSide: unknown) {
  const side = String(rawSide);
  if (side !== "heads" && side !== "tails") throw new HttpError(400, "Choisis pile ou face");
  const result = randomInt(2) === 0 ? "heads" : "tails";
  s.flips.push({ side, result });
  if (result === side) {
    s.streak++;
    if (s.streak === COIN_MAX_FLIPS) {
      s.status = "won";
      s.payout = Math.floor(s.bet * coinMult(s.streak));
      finishRound(userId, "coinflip", s.bet, s.payout);
    }
  } else {
    s.status = "lost";
    finishRound(userId, "coinflip", s.bet, 0);
  }
}

export const startCoin = db.transaction((userId: number, rawBet: unknown, rawSide: unknown) => {
  assertNoActive(userId, "coinflip");
  const bet = parseBet(rawBet);
  takeBet(userId, "coinflip", bet);
  const s: CoinState = { status: "playing", bet, flips: [], streak: 0, payout: 0 };
  flip(userId, s, rawSide);
  saveSession(userId, "coinflip", s);
  return coinResponse(userId, s);
});

export const flipCoin = db.transaction((userId: number, rawSide: unknown) => {
  const s = activeSession<CoinState>(userId, "coinflip");
  flip(userId, s, rawSide);
  saveSession(userId, "coinflip", s);
  return coinResponse(userId, s);
});

export const cashoutCoin = db.transaction((userId: number) => {
  const s = activeSession<CoinState>(userId, "coinflip");
  if (!s.streak) throw new HttpError(400, "Aucun lancer gagné à encaisser");
  s.status = "won";
  s.payout = Math.floor(s.bet * coinMult(s.streak));
  finishRound(userId, "coinflip", s.bet, s.payout);
  saveSession(userId, "coinflip", s);
  return coinResponse(userId, s);
});
