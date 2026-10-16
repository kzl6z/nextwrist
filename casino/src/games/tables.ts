// Jeux de cartes : Baccarat (punto banco) et Video poker (Jacks or Better 9/6).
import { db } from "../db";
import { HttpError } from "../http";
import { getBalance } from "../wallet";
import {
  activeSession,
  assertNoActive,
  CASINO_MAX,
  finishRound,
  loadSession,
  newDeck,
  parseBet,
  rankOf,
  saveSession,
  takeBet,
} from "./common";

/* =========================================================
   Baccarat
   ========================================================= */
const bacValue = (card: string) => Math.min(10, rankOf(card)) % 10;
const bacTotal = (cards: string[]) => cards.reduce((s, c) => s + bacValue(c), 0) % 10;

/** Règle du tirage de la troisième carte du banquier. */
function bankerDraws(banker: number, playerThird: number | null): boolean {
  if (playerThird === null) return banker <= 5;
  if (banker <= 2) return true;
  if (banker === 3) return playerThird !== 8;
  if (banker === 4) return playerThird >= 2 && playerThird <= 7;
  if (banker === 5) return playerThird >= 4 && playerThird <= 7;
  if (banker === 6) return playerThird === 6 || playerThird === 7;
  return false;
}

export function dealBaccarat(shoe: string[]) {
  const player = [shoe.pop()!, shoe.pop()!];
  const banker = [shoe.pop()!, shoe.pop()!];
  const natural = bacTotal(player) >= 8 || bacTotal(banker) >= 8;
  let third: number | null = null;
  if (!natural) {
    if (bacTotal(player) <= 5) {
      const c = shoe.pop()!;
      player.push(c);
      third = bacValue(c);
    }
    if (bankerDraws(bacTotal(banker), third)) banker.push(shoe.pop()!);
  }
  const p = bacTotal(player);
  const b = bacTotal(banker);
  return { player, banker, playerTotal: p, bankerTotal: b, winner: p > b ? "player" : b > p ? "banker" : "tie" } as const;
}

/** Multiplicateur (mise comprise) de chaque pari selon le gagnant. */
export const BACCARAT_PAYS = {
  player: { player: 2, banker: 0, tie: 1 },
  banker: { player: 0, banker: 1.95, tie: 1 },
  tie: { player: 0, banker: 0, tie: 9 },
} as const;

export const playBaccarat = db.transaction((userId: number, rawBets: unknown) => {
  const raw = (rawBets ?? {}) as Record<string, unknown>;
  const bets = { player: 0, banker: 0, tie: 0 };
  for (const k of ["player", "banker", "tie"] as const) {
    const v = raw[k];
    if (v === undefined || v === null || v === 0 || v === "") continue;
    bets[k] = parseBet(v);
  }
  const total = bets.player + bets.banker + bets.tie;
  if (!total) throw new HttpError(400, "Place au moins une mise");
  if (total > CASINO_MAX) throw new HttpError(400, `Mise totale maximum : ${CASINO_MAX}`);
  takeBet(userId, "baccarat", total);
  const round = dealBaccarat(newDeck(8));
  let payout = 0;
  for (const k of ["player", "banker", "tie"] as const) payout += Math.floor(bets[k] * BACCARAT_PAYS[k][round.winner]);
  return { ...round, bets, total, payout, balance: finishRound(userId, "baccarat", total, payout) };
});

/* =========================================================
   Video poker — Jacks or Better
   ========================================================= */
export const POKER_PAYS: [string, string, number][] = [
  ["royal", "Quinte flush royale", 800],
  ["straight_flush", "Quinte flush", 50],
  ["four", "Carré", 25],
  ["full", "Full", 9],
  ["flush", "Couleur", 6],
  ["straight", "Quinte", 4],
  ["three", "Brelan", 3],
  ["two_pair", "Double paire", 2],
  ["jacks", "Paire de valets ou mieux", 1],
];

/** Combinaison d'une main de 5 cartes, ou null. */
export function pokerHand(cards: string[]): string | null {
  const ranks = cards.map((c) => (rankOf(c) === 1 ? 14 : rankOf(c))).sort((a, b) => a - b);
  const suits = new Set(cards.map((c) => c.slice(-1)));
  const counts = [...ranks.reduce((m, r) => m.set(r, (m.get(r) ?? 0) + 1), new Map<number, number>())].sort(
    (a, b) => b[1] - a[1] || b[0] - a[0],
  );
  const flush = suits.size === 1;
  const unique = new Set(ranks).size === 5;
  const wheel = ranks.join() === "2,3,4,5,14";
  const straight = unique && (ranks[4]! - ranks[0]! === 4 || wheel);
  if (straight && flush) return ranks[0] === 10 ? "royal" : "straight_flush";
  if (counts[0]![1] === 4) return "four";
  if (counts[0]![1] === 3 && counts[1]![1] === 2) return "full";
  if (flush) return "flush";
  if (straight) return "straight";
  if (counts[0]![1] === 3) return "three";
  if (counts[0]![1] === 2 && counts[1]![1] === 2) return "two_pair";
  if (counts[0]![1] === 2 && counts[0]![0] >= 11) return "jacks";
  return null;
}

const payOf = (hand: string | null) => POKER_PAYS.find(([k]) => k === hand)?.[2] ?? 0;

interface PokerState {
  status: "playing" | "done";
  bet: number;
  deck: string[];
  hand: string[];
  held: boolean[];
  result: string | null;
  payout: number;
}

function pokerResponse(userId: number, s: PokerState | null) {
  if (!s) return { game: null, balance: getBalance(userId) };
  return {
    game: {
      status: s.status,
      bet: s.bet,
      hand: s.hand,
      held: s.held,
      // Pendant la donne, on indique déjà la combinaison servie.
      result: s.status === "playing" ? pokerHand(s.hand) : s.result,
      payout: s.payout,
    },
    balance: getBalance(userId),
  };
}

export const getPoker = (userId: number) => pokerResponse(userId, loadSession<PokerState>(userId, "videopoker"));

export const dealPoker = db.transaction((userId: number, rawBet: unknown) => {
  assertNoActive(userId, "videopoker");
  const bet = parseBet(rawBet);
  takeBet(userId, "videopoker", bet);
  const deck = newDeck(1);
  const hand = deck.splice(0, 5);
  const s: PokerState = { status: "playing", bet, deck, hand, held: [false, false, false, false, false], result: null, payout: 0 };
  saveSession(userId, "videopoker", s);
  return pokerResponse(userId, s);
});

export const drawPoker = db.transaction((userId: number, rawHolds: unknown) => {
  const s = activeSession<PokerState>(userId, "videopoker");
  if (!Array.isArray(rawHolds) || rawHolds.length !== 5) throw new HttpError(400, "Choix des cartes invalide");
  s.held = rawHolds.map((h) => h === true);
  s.hand = s.hand.map((c, i) => (s.held[i] ? c : s.deck.shift()!));
  s.result = pokerHand(s.hand);
  s.payout = Math.floor(s.bet * payOf(s.result));
  s.status = "done";
  finishRound(userId, "videopoker", s.bet, s.payout);
  saveSession(userId, "videopoker", s);
  return pokerResponse(userId, s);
});
