import { db } from "../db";
import { HttpError } from "../http";
import { shuffle } from "../rng";
import { applyTx, getBalance, parseStake } from "../wallet";
import { recordRound } from "./common";

// Sabot de 6 jeux remélangé à chaque main. Croupier reste sur tous les 17.
// Blackjack payé 3:2. Pas de split ni d'assurance pour l'instant.

type Status = "playing" | "won" | "lost" | "push" | "blackjack";
interface Hand {
  deck: string[];
  player: string[];
  dealer: string[];
  bet: number;
  status: Status;
  payout: number;
}

const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
const SUITS = ["♠", "♥", "♦", "♣"];

function newShoe(): string[] {
  const cards: string[] = [];
  for (let d = 0; d < 6; d++) for (const s of SUITS) for (const r of RANKS) cards.push(r + s);
  return shuffle(cards);
}

export function handValue(cards: string[]): number {
  let total = 0;
  let aces = 0;
  for (const c of cards) {
    const r = c.slice(0, -1);
    if (r === "A") {
      aces++;
      total += 11;
    } else total += ["J", "Q", "K"].includes(r) ? 10 : Number(r);
  }
  while (total > 21 && aces > 0) {
    total -= 10;
    aces--;
  }
  return total;
}

const isBlackjack = (cards: string[]) => cards.length === 2 && handValue(cards) === 21;

function load(userId: number): Hand | null {
  const row = db.query("SELECT state FROM blackjack_hands WHERE user_id = ?").get(userId) as { state: string } | null;
  return row ? JSON.parse(row.state) : null;
}

function save(userId: number, hand: Hand) {
  db.query("INSERT OR REPLACE INTO blackjack_hands (user_id, state) VALUES (?, ?)").run(userId, JSON.stringify(hand));
}

function view(hand: Hand | null, balance: number) {
  if (!hand) return { hand: null, balance };
  const hidden = hand.status === "playing";
  const dealer = hidden ? [hand.dealer[0]!, "??"] : hand.dealer;
  return {
    hand: {
      player: hand.player,
      dealer,
      playerValue: handValue(hand.player),
      dealerValue: hidden ? handValue([hand.dealer[0]!]) : handValue(hand.dealer),
      bet: hand.bet,
      status: hand.status,
      payout: hand.payout,
      canDouble: hand.status === "playing" && hand.player.length === 2,
    },
    balance,
  };
}

function settle(userId: number, hand: Hand, status: Exclude<Status, "playing">) {
  hand.status = status;
  hand.payout = { blackjack: hand.bet + Math.floor(hand.bet * 1.5), won: hand.bet * 2, push: hand.bet, lost: 0 }[status];
  if (hand.payout > 0) applyTx(userId, hand.payout, "blackjack_win");
  recordRound(userId, "blackjack", hand.bet, hand.payout);
}

function dealerPlays(userId: number, hand: Hand) {
  while (handValue(hand.dealer) < 17) hand.dealer.push(hand.deck.pop()!);
  const p = handValue(hand.player);
  const d = handValue(hand.dealer);
  settle(userId, hand, d > 21 || p > d ? "won" : p === d ? "push" : "lost");
}

function playing(userId: number): Hand {
  const hand = load(userId);
  if (!hand || hand.status !== "playing") throw new HttpError(400, "Aucune main en cours");
  return hand;
}

function finishPlayerTurn(userId: number, hand: Hand) {
  const v = handValue(hand.player);
  if (v > 21) settle(userId, hand, "lost");
  else if (v === 21) dealerPlays(userId, hand);
}

export function getBlackjack(userId: number) {
  return view(load(userId), getBalance(userId));
}

export const startBlackjack = db.transaction((userId: number, rawBet: unknown) => {
  if (load(userId)?.status === "playing") throw new HttpError(409, "Une main est déjà en cours");
  const bet = parseStake(rawBet, 10_000);
  applyTx(userId, -bet, "blackjack_bet");
  const deck = newShoe();
  const hand: Hand = { deck, player: [deck.pop()!], dealer: [deck.pop()!], bet, status: "playing", payout: 0 };
  hand.player.push(deck.pop()!);
  hand.dealer.push(deck.pop()!);

  const pBJ = isBlackjack(hand.player);
  const dBJ = isBlackjack(hand.dealer);
  if (pBJ || dBJ) settle(userId, hand, pBJ && dBJ ? "push" : pBJ ? "blackjack" : "lost");
  save(userId, hand);
  return view(hand, getBalance(userId));
});

export const hitBlackjack = db.transaction((userId: number) => {
  const hand = playing(userId);
  hand.player.push(hand.deck.pop()!);
  finishPlayerTurn(userId, hand);
  save(userId, hand);
  return view(hand, getBalance(userId));
});

export const standBlackjack = db.transaction((userId: number) => {
  const hand = playing(userId);
  dealerPlays(userId, hand);
  save(userId, hand);
  return view(hand, getBalance(userId));
});

export const doubleBlackjack = db.transaction((userId: number) => {
  const hand = playing(userId);
  if (hand.player.length !== 2) throw new HttpError(400, "Doubler uniquement sur les 2 premières cartes");
  applyTx(userId, -hand.bet, "blackjack_bet");
  hand.bet *= 2;
  hand.player.push(hand.deck.pop()!);
  if (handValue(hand.player) > 21) settle(userId, hand, "lost");
  else dealerPlays(userId, hand);
  save(userId, hand);
  return view(hand, getBalance(userId));
});
