// Jeux en plusieurs étapes, deuxième série : Three Card Poker, Traversée, Ballon, Penalty,
// Pierre-feuille-ciseaux. L'état secret (cartes du croupier, éclatement du ballon) reste côté serveur.
import { db } from "../db";
import { HttpError } from "../http";
import { randomInt, shuffle } from "../rng";
import { getBalance } from "../wallet";
import {
  activeSession,
  assertNoActive,
  CASINO_MAX,
  finishRound,
  floor4,
  loadSession,
  newDeck,
  parseBet,
  rankOf,
  saveSession,
  takeBet,
} from "./common";

type Status = "playing" | "won" | "lost";

/* =========================================================
   Three Card Poker : Ante / Play contre le croupier, Pair Plus en option
   ========================================================= */
export const TCP_HANDS = ["high", "pair", "flush", "straight", "trips", "straightflush"] as const;
export type TcpHand = (typeof TCP_HANDS)[number];
export const TCP_NAMES: Record<TcpHand, string> = {
  high: "Carte haute",
  pair: "Paire",
  flush: "Couleur",
  straight: "Suite",
  trips: "Brelan",
  straightflush: "Quinte flush",
};
/** Pair Plus (gain pour 1, mise non comprise). */
export const PAIR_PLUS: Partial<Record<TcpHand, number>> = { pair: 1, flush: 4, straight: 6, trips: 30, straightflush: 40 };
/** Bonus d'Ante, payé quelle que soit la main du croupier. */
export const ANTE_BONUS: Partial<Record<TcpHand, number>> = { straight: 1, trips: 4, straightflush: 5 };

/** Valeur d'une carte pour le poker : 2 à 14 (As haut). */
const pokerRank = (card: string) => {
  const r = rankOf(card);
  return r === 1 ? 14 : r;
};

/** Main à trois cartes : [catégorie, valeurs pour départager]. */
export function tcpEvaluate(cards: string[]): { hand: TcpHand; score: number[] } {
  const v = cards.map(pokerRank).sort((a, b) => b - a);
  const flush = cards.every((c) => c.slice(-1) === cards[0]!.slice(-1));
  const wheel = v[0] === 14 && v[1] === 3 && v[2] === 2;
  const straight = (v[0]! - v[1]! === 1 && v[1]! - v[2]! === 1) || wheel;
  const top = wheel ? 3 : v[0]!;
  if (straight && flush) return { hand: "straightflush", score: [5, top] };
  if (v[0] === v[2]) return { hand: "trips", score: [4, v[0]!] };
  if (straight) return { hand: "straight", score: [3, top] };
  if (flush) return { hand: "flush", score: [2, ...v] };
  if (v[0] === v[1] || v[1] === v[2]) {
    const pair = v[1]!;
    const kicker = v[0] === v[1] ? v[2]! : v[0]!;
    return { hand: "pair", score: [1, pair, kicker] };
  }
  return { hand: "high", score: [0, ...v] };
}

export function tcpCompare(a: number[], b: number[]) {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d) return Math.sign(d);
  }
  return 0;
}

/** Le croupier se qualifie avec Dame haute ou mieux. */
export const tcpQualifies = (score: number[]) => score[0]! > 0 || score[1]! >= 12;

interface TcpState {
  status: "playing" | "done";
  ante: number;
  pairPlus: number;
  play: number;
  player: string[];
  dealer: string[];
  result?: {
    folded: boolean;
    qualifies: boolean;
    outcome: "win" | "lose" | "push" | "noqualify" | "fold";
    playerHand: TcpHand;
    dealerHand: TcpHand;
    anteWin: number;
    playWin: number;
    bonusWin: number;
    pairPlusWin: number;
  };
  payout: number;
}

function tcpResponse(userId: number, s: TcpState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  const playing = s.status === "playing";
  return {
    game: {
      status: s.status,
      ante: s.ante,
      pairPlus: s.pairPlus,
      play: s.play,
      player: s.player,
      playerHand: tcpEvaluate(s.player).hand,
      dealer: playing ? undefined : s.dealer,
      result: s.result,
      payout: s.payout,
    },
    balance: getBalance(userId),
  };
}

export const getThreeCard = (userId: number) => tcpResponse(userId, loadSession<TcpState>(userId, "threecard"));

export const dealThreeCard = db.transaction((userId: number, rawAnte: unknown, rawPairPlus: unknown) => {
  assertNoActive(userId, "threecard");
  const ante = parseBet(rawAnte);
  const pairPlus = rawPairPlus === undefined || rawPairPlus === null || Number(rawPairPlus) === 0 ? 0 : parseBet(rawPairPlus);
  if (ante * 2 + pairPlus > CASINO_MAX) throw new HttpError(400, `Mise totale maximum : ${CASINO_MAX} (Ante + Play + Pair Plus)`);
  takeBet(userId, "threecard", ante + pairPlus);
  const deck = newDeck();
  const s: TcpState = {
    status: "playing",
    ante,
    pairPlus,
    play: 0,
    player: [deck.pop()!, deck.pop()!, deck.pop()!],
    dealer: [deck.pop()!, deck.pop()!, deck.pop()!],
    payout: 0,
  };
  saveSession(userId, "threecard", s);
  return tcpResponse(userId, s);
});

export const decideThreeCard = db.transaction((userId: number, rawAction: unknown) => {
  const s = activeSession<TcpState>(userId, "threecard");
  const action = String(rawAction);
  if (action !== "play" && action !== "fold") throw new HttpError(400, "Choisis Jouer ou Se coucher");
  const p = tcpEvaluate(s.player);
  const d = tcpEvaluate(s.dealer);
  const pairPlusWin = s.pairPlus && PAIR_PLUS[p.hand] ? s.pairPlus * (PAIR_PLUS[p.hand]! + 1) : 0;
  let anteWin = 0;
  let playWin = 0;
  let bonusWin = 0;
  let outcome: NonNullable<TcpState["result"]>["outcome"] = "fold";
  const qualifies = tcpQualifies(d.score);
  if (action === "play") {
    s.play = s.ante;
    takeBet(userId, "threecard", s.play);
    bonusWin = ANTE_BONUS[p.hand] ? s.ante * ANTE_BONUS[p.hand]! : 0;
    if (!qualifies) {
      outcome = "noqualify";
      anteWin = s.ante * 2;
      playWin = s.play;
    } else {
      const c = tcpCompare(p.score, d.score);
      outcome = c > 0 ? "win" : c < 0 ? "lose" : "push";
      anteWin = c > 0 ? s.ante * 2 : c === 0 ? s.ante : 0;
      playWin = c > 0 ? s.play * 2 : c === 0 ? s.play : 0;
    }
  }
  s.payout = anteWin + playWin + bonusWin + pairPlusWin;
  s.status = "done";
  s.result = {
    folded: action === "fold",
    qualifies,
    outcome,
    playerHand: p.hand,
    dealerHand: d.hand,
    anteWin,
    playWin,
    bonusWin,
    pairPlusWin,
  };
  finishRound(userId, "threecard", s.ante + s.pairPlus + s.play, s.payout);
  saveSession(userId, "threecard", s);
  return tcpResponse(userId, s);
});

/* =========================================================
   Moteur commun des jeux « avance ou encaisse »
   ========================================================= */
interface LadderState {
  status: Status;
  bet: number;
  mode: string;
  steps: number;
  payout: number;
}

function cashLadder<S extends LadderState>(userId: number, game: string, s: S, mult: number) {
  s.status = "won";
  s.payout = Math.floor(s.bet * mult);
  finishRound(userId, game, s.bet, s.payout);
}

/* =========================================================
   Traversée : traverser les voies une à une sans se faire renverser
   ========================================================= */
const CROSS_EDGE = 0.98;
export const CROSSING: Record<string, { p: number; lanes: number }> = {
  easy: { p: 0.92, lanes: 24 },
  medium: { p: 0.84, lanes: 20 },
  hard: { p: 0.72, lanes: 16 },
  expert: { p: 0.6, lanes: 12 },
};
export const crossMultiplier = (mode: string, steps: number) =>
  steps === 0 ? 1 : floor4(CROSS_EDGE / CROSSING[mode]!.p ** steps);

interface CrossState extends LadderState {
  /** Voie où la voiture a percuté (fin de partie). */
  hitAt?: number;
}

function crossResponse(userId: number, s: CrossState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  const conf = CROSSING[s.mode]!;
  return {
    game: {
      ...s,
      lanes: conf.lanes,
      chance: conf.p,
      multiplier: crossMultiplier(s.mode, s.steps),
      ladder: Array.from({ length: conf.lanes }, (_, i) => crossMultiplier(s.mode, i + 1)),
    },
    balance: getBalance(userId),
  };
}

export const getCrossing = (userId: number) => crossResponse(userId, loadSession<CrossState>(userId, "crossing"));

export const startCrossing = db.transaction((userId: number, rawBet: unknown, rawMode: unknown) => {
  assertNoActive(userId, "crossing");
  const bet = parseBet(rawBet);
  const mode = String(rawMode);
  if (!CROSSING[mode]) throw new HttpError(400, "Difficulté invalide");
  takeBet(userId, "crossing", bet);
  const s: CrossState = { status: "playing", bet, mode, steps: 0, payout: 0 };
  saveSession(userId, "crossing", s);
  return crossResponse(userId, s);
});

export const stepCrossing = db.transaction((userId: number) => {
  const s = activeSession<CrossState>(userId, "crossing");
  const conf = CROSSING[s.mode]!;
  // Probabilité p, tirée sur 1 000 000 pour rester entière.
  const safe = randomInt(1_000_000) < Math.round(conf.p * 1_000_000);
  if (!safe) {
    s.status = "lost";
    s.hitAt = s.steps;
    finishRound(userId, "crossing", s.bet, 0);
  } else {
    s.steps++;
    if (s.steps === conf.lanes) cashLadder(userId, "crossing", s, crossMultiplier(s.mode, s.steps));
  }
  saveSession(userId, "crossing", s);
  return crossResponse(userId, s);
});

export const cashoutCrossing = db.transaction((userId: number) => {
  const s = activeSession<CrossState>(userId, "crossing");
  if (!s.steps) throw new HttpError(400, "Traverse au moins une voie");
  cashLadder(userId, "crossing", s, crossMultiplier(s.mode, s.steps));
  saveSession(userId, "crossing", s);
  return crossResponse(userId, s);
});

/* =========================================================
   Ballon : gonfler sans le faire éclater
   ========================================================= */
const BALLOON_EDGE = 0.98;
const BALLOON_SLOTS = 25;
/** Nombre de « cases piégées » parmi 25 : plus il y en a, plus le ballon est fragile. */
export const BALLOON: Record<string, number> = { low: 1, medium: 3, high: 5, expert: 10 };

export function balloonMultiplier(mode: string, pumps: number): number {
  const m = BALLOON[mode]!;
  let x = BALLOON_EDGE;
  for (let i = 0; i < pumps; i++) x *= (BALLOON_SLOTS - i) / (BALLOON_SLOTS - m - i);
  return pumps === 0 ? 1 : floor4(x);
}

interface BalloonState extends LadderState {
  /** Coup de pompe qui fait éclater le ballon (secret jusqu'à la fin). */
  burstAt: number;
}

function balloonResponse(userId: number, s: BalloonState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  const { burstAt, ...pub } = s;
  const max = BALLOON_SLOTS - BALLOON[s.mode]!;
  return {
    game: {
      ...pub,
      burstAt: s.status === "playing" ? undefined : burstAt,
      max,
      multiplier: balloonMultiplier(s.mode, s.steps),
      next: s.steps < max ? balloonMultiplier(s.mode, s.steps + 1) : null,
      chance: s.steps < max ? (BALLOON_SLOTS - BALLOON[s.mode]! - s.steps) / (BALLOON_SLOTS - s.steps) : 0,
    },
    balance: getBalance(userId),
  };
}

export const getBalloon = (userId: number) => balloonResponse(userId, loadSession<BalloonState>(userId, "balloon"));

export const startBalloon = db.transaction((userId: number, rawBet: unknown, rawMode: unknown) => {
  assertNoActive(userId, "balloon");
  const bet = parseBet(rawBet);
  const mode = String(rawMode);
  if (!BALLOON[mode]) throw new HttpError(400, "Risque invalide");
  takeBet(userId, "balloon", bet);
  // Les cases piégées sont placées au hasard ; le ballon éclate à la première atteinte.
  const order = shuffle(Array.from({ length: BALLOON_SLOTS }, (_, i) => i));
  const burstAt = 1 + Math.min(...order.slice(0, BALLOON[mode]!));
  const s: BalloonState = { status: "playing", bet, mode, steps: 0, payout: 0, burstAt };
  saveSession(userId, "balloon", s);
  return balloonResponse(userId, s);
});

export const pumpBalloon = db.transaction((userId: number) => {
  const s = activeSession<BalloonState>(userId, "balloon");
  if (s.steps + 1 === s.burstAt) {
    s.status = "lost";
    finishRound(userId, "balloon", s.bet, 0);
  } else {
    s.steps++;
    if (s.steps === BALLOON_SLOTS - BALLOON[s.mode]!) cashLadder(userId, "balloon", s, balloonMultiplier(s.mode, s.steps));
  }
  saveSession(userId, "balloon", s);
  return balloonResponse(userId, s);
});

export const cashoutBalloon = db.transaction((userId: number) => {
  const s = activeSession<BalloonState>(userId, "balloon");
  if (!s.steps) throw new HttpError(400, "Gonfle au moins une fois");
  cashLadder(userId, "balloon", s, balloonMultiplier(s.mode, s.steps));
  saveSession(userId, "balloon", s);
  return balloonResponse(userId, s);
});

/* =========================================================
   Penalty : 5 zones, le gardien en couvre une (ou deux en mode difficile)
   ========================================================= */
const PENALTY_EDGE = 0.97;
const PENALTY_ZONES = 5;
export const PENALTY: Record<string, { keepers: number; kicks: number }> = {
  normal: { keepers: 1, kicks: 10 },
  hard: { keepers: 2, kicks: 8 },
};
const penaltyChance = (mode: string) => (PENALTY_ZONES - PENALTY[mode]!.keepers) / PENALTY_ZONES;
export const penaltyMultiplier = (mode: string, goals: number) =>
  goals === 0 ? 1 : floor4(PENALTY_EDGE / penaltyChance(mode) ** goals);

interface PenaltyState extends LadderState {
  kicks: { zone: number; dive: number[]; goal: boolean }[];
}

function penaltyResponse(userId: number, s: PenaltyState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  const conf = PENALTY[s.mode]!;
  return {
    game: {
      ...s,
      maxKicks: conf.kicks,
      chance: penaltyChance(s.mode),
      multiplier: penaltyMultiplier(s.mode, s.steps),
      ladder: Array.from({ length: conf.kicks }, (_, i) => penaltyMultiplier(s.mode, i + 1)),
    },
    balance: getBalance(userId),
  };
}

export const getPenalty = (userId: number) => penaltyResponse(userId, loadSession<PenaltyState>(userId, "penalty"));

export const startPenalty = db.transaction((userId: number, rawBet: unknown, rawMode: unknown) => {
  assertNoActive(userId, "penalty");
  const bet = parseBet(rawBet);
  const mode = String(rawMode);
  if (!PENALTY[mode]) throw new HttpError(400, "Mode invalide");
  takeBet(userId, "penalty", bet);
  const s: PenaltyState = { status: "playing", bet, mode, steps: 0, payout: 0, kicks: [] };
  saveSession(userId, "penalty", s);
  return penaltyResponse(userId, s);
});

export const shootPenalty = db.transaction((userId: number, rawZone: unknown) => {
  const s = activeSession<PenaltyState>(userId, "penalty");
  const zone = Number(rawZone);
  if (!Number.isInteger(zone) || zone < 0 || zone >= PENALTY_ZONES) throw new HttpError(400, "Zone invalide");
  const dive = shuffle(Array.from({ length: PENALTY_ZONES }, (_, i) => i)).slice(0, PENALTY[s.mode]!.keepers);
  const goal = !dive.includes(zone);
  s.kicks.push({ zone, dive, goal });
  if (!goal) {
    s.status = "lost";
    finishRound(userId, "penalty", s.bet, 0);
  } else {
    s.steps++;
    if (s.steps === PENALTY[s.mode]!.kicks) cashLadder(userId, "penalty", s, penaltyMultiplier(s.mode, s.steps));
  }
  saveSession(userId, "penalty", s);
  return penaltyResponse(userId, s);
});

export const cashoutPenalty = db.transaction((userId: number) => {
  const s = activeSession<PenaltyState>(userId, "penalty");
  if (!s.steps) throw new HttpError(400, "Marque au moins un but");
  cashLadder(userId, "penalty", s, penaltyMultiplier(s.mode, s.steps));
  saveSession(userId, "penalty", s);
  return penaltyResponse(userId, s);
});

/* =========================================================
   Pierre-feuille-ciseaux : chaque victoire double le gain, l'égalité se rejoue
   ========================================================= */
const RPS_EDGE = 0.98;
const RPS_MAX = 15;
const MOVES = ["rock", "paper", "scissors"] as const;
type Move = (typeof MOVES)[number];
const BEATS: Record<Move, Move> = { rock: "scissors", paper: "rock", scissors: "paper" };
export const rpsMultiplier = (wins: number) => (wins === 0 ? 1 : floor4(RPS_EDGE * 2 ** wins));

interface RpsState extends LadderState {
  rounds: { you: Move; house: Move; result: "win" | "draw" | "lose" }[];
}

function rpsResponse(userId: number, s: RpsState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  return {
    game: { ...s, max: RPS_MAX, multiplier: rpsMultiplier(s.steps), next: rpsMultiplier(s.steps + 1) },
    balance: getBalance(userId),
  };
}

export const getRps = (userId: number) => rpsResponse(userId, loadSession<RpsState>(userId, "rps"));

function throwRps(userId: number, s: RpsState, rawMove: unknown) {
  const you = String(rawMove) as Move;
  if (!MOVES.includes(you)) throw new HttpError(400, "Choisis pierre, feuille ou ciseaux");
  const house = MOVES[randomInt(3)]!;
  const result = you === house ? "draw" : BEATS[you] === house ? "win" : "lose";
  s.rounds.push({ you, house, result });
  if (s.rounds.length > 200) s.rounds.shift();
  if (result === "lose") {
    s.status = "lost";
    finishRound(userId, "rps", s.bet, 0);
  } else if (result === "win") {
    s.steps++;
    if (s.steps === RPS_MAX) cashLadder(userId, "rps", s, rpsMultiplier(s.steps));
  }
}

export const startRps = db.transaction((userId: number, rawBet: unknown, rawMove: unknown) => {
  assertNoActive(userId, "rps");
  const bet = parseBet(rawBet);
  if (!MOVES.includes(String(rawMove) as Move)) throw new HttpError(400, "Choisis pierre, feuille ou ciseaux");
  takeBet(userId, "rps", bet);
  const s: RpsState = { status: "playing", bet, mode: "classic", steps: 0, payout: 0, rounds: [] };
  throwRps(userId, s, rawMove);
  saveSession(userId, "rps", s);
  return rpsResponse(userId, s);
});

export const playRps = db.transaction((userId: number, rawMove: unknown) => {
  const s = activeSession<RpsState>(userId, "rps");
  throwRps(userId, s, rawMove);
  saveSession(userId, "rps", s);
  return rpsResponse(userId, s);
});

export const cashoutRps = db.transaction((userId: number) => {
  const s = activeSession<RpsState>(userId, "rps");
  if (!s.steps) throw new HttpError(400, "Gagne au moins une manche");
  cashLadder(userId, "rps", s, rpsMultiplier(s.steps));
  saveSession(userId, "rps", s);
  return rpsResponse(userId, s);
});

export function moreStepsConfig() {
  return {
    threecard: { pairPlus: PAIR_PLUS, anteBonus: ANTE_BONUS, names: TCP_NAMES },
    crossing: CROSSING,
    balloon: BALLOON,
    penalty: PENALTY,
  };
}
