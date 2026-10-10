import { db } from "../db";
import { HttpError } from "../http";
import { applyTx, getBalance, parseStake } from "../wallet";
import type { FeedEvent, FeedResult, Outcome } from "./types";

const OUTCOMES: Outcome[] = ["home", "draw", "away"];
const MAX_LEGS = 10;
/** Un match réel sans résultat après ce délai est annulé (paris remboursés). */
const STALE_MS = 3 * 86_400_000;

export const upsertEvents = db.transaction((events: FeedEvent[]) => {
  const now = Date.now();
  const upsert = db.query(
    `INSERT INTO events (id, sport, league, home, away, starts_at, feed_key, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET starts_at = excluded.starts_at, updated_at = excluded.updated_at
     WHERE events.status = 'scheduled'`,
  );
  const setOdds = db.query(
    `INSERT INTO odds (event_id, outcome, price) VALUES (?, ?, ?)
     ON CONFLICT(event_id, outcome) DO UPDATE SET price = excluded.price`,
  );
  for (const e of events) {
    if (e.startsAt <= now) continue;
    upsert.run(e.id, e.sport, e.league, e.home, e.away, e.startsAt, e.feedKey ?? null, now);
    for (const o of OUTCOMES) if (e.odds[o]) setOdds.run(e.id, o, e.odds[o]!);
  }
});

export const applyResults = db.transaction((results: FeedResult[]) => {
  const finish = db.query(
    `UPDATE events SET status = 'finished', home_score = ?, away_score = ?, updated_at = ?
     WHERE id = ? AND status = 'scheduled'`,
  );
  for (const r of results) finish.run(r.homeScore, r.awayScore, Date.now(), r.id);
  db.query(
    "UPDATE events SET status = 'cancelled', updated_at = ?1 WHERE status = 'scheduled' AND starts_at < ?2",
  ).run(Date.now(), Date.now() - STALE_MS);
});

/** Compétitions ayant au moins un match commencé depuis assez longtemps pour être fini. */
export function feedKeysAwaitingResults(minAgeMs: number): string[] {
  return (
    db
      .query(
        `SELECT DISTINCT feed_key FROM events
         WHERE status = 'scheduled' AND feed_key IS NOT NULL AND starts_at < ?`,
      )
      .all(Date.now() - minAgeMs) as { feed_key: string }[]
  ).map((r) => r.feed_key);
}

export function listEvents() {
  const events = db
    .query(
      `SELECT id, sport, league, home, away, starts_at FROM events
       WHERE status = 'scheduled' AND starts_at > ? ORDER BY starts_at LIMIT 200`,
    )
    .all(Date.now()) as any[];
  const odds = db
    .query(
      `SELECT o.event_id, o.outcome, o.price FROM odds o JOIN events e ON e.id = o.event_id
       WHERE e.status = 'scheduled' AND e.starts_at > ?`,
    )
    .all(Date.now()) as { event_id: string; outcome: Outcome; price: number }[];
  const byEvent = new Map<string, Record<string, number>>();
  for (const o of odds) (byEvent.get(o.event_id) ?? byEvent.set(o.event_id, {}).get(o.event_id)!)[o.outcome] = o.price;
  return events.map((e) => ({ ...e, odds: byEvent.get(e.id) ?? {} }));
}

/** Matchs commencés mais pas encore terminés (paris fermés). */
export function liveEvents() {
  const now = Date.now();
  return db
    .query(
      `SELECT id, sport, league, home, away, starts_at FROM events
       WHERE status = 'scheduled' AND starts_at <= ? AND starts_at > ? ORDER BY starts_at DESC LIMIT 30`,
    )
    .all(now, now - 3 * 60 * 60_000);
}

export function recentResults() {
  return db
    .query(
      `SELECT id, sport, league, home, away, starts_at, status, home_score, away_score FROM events
       WHERE status != 'scheduled' ORDER BY updated_at DESC LIMIT 20`,
    )
    .all();
}

export const placeBet = db.transaction((userId: number, rawLegs: unknown, rawStake: unknown) => {
  const stake = parseStake(rawStake);
  if (!Array.isArray(rawLegs) || rawLegs.length === 0) throw new HttpError(400, "Ticket vide");
  if (rawLegs.length > MAX_LEGS) throw new HttpError(400, `Maximum ${MAX_LEGS} sélections`);

  const now = Date.now();
  const seen = new Set<string>();
  const legs = rawLegs.map((l: any) => {
    const eventId = String(l?.eventId);
    const outcome = String(l?.outcome);
    if (seen.has(eventId)) throw new HttpError(400, "Un seul pronostic par match dans un combiné");
    seen.add(eventId);
    const row = db
      .query(
        `SELECT e.status, e.starts_at, e.home, e.away, o.price FROM events e
         JOIN odds o ON o.event_id = e.id WHERE e.id = ? AND o.outcome = ?`,
      )
      .get(eventId, outcome) as { status: string; starts_at: number; home: string; away: string; price: number } | null;
    if (!row) throw new HttpError(404, "Match ou pronostic introuvable");
    if (row.status !== "scheduled" || row.starts_at <= now)
      throw new HttpError(400, `${row.home} - ${row.away} a déjà commencé`);
    if (Number(l?.price) !== row.price)
      throw new HttpError(409, `La cote de ${row.home} - ${row.away} a changé, vérifie ton ticket`);
    return { eventId, outcome, price: row.price };
  });

  const totalOdds = Math.round(legs.reduce((p, l) => p * l.price, 1) * 100) / 100;
  const potentialWin = Math.floor(stake * totalOdds);
  const { id } = db
    .query(
      "INSERT INTO bets (user_id, stake, total_odds, potential_win, created_at) VALUES (?, ?, ?, ?, ?) RETURNING id",
    )
    .get(userId, stake, totalOdds, potentialWin, now) as { id: number };
  const insertLeg = db.query("INSERT INTO bet_legs (bet_id, event_id, outcome, price) VALUES (?, ?, ?, ?)");
  for (const l of legs) insertLeg.run(id, l.eventId, l.outcome, l.price);
  const balance = applyTx(userId, -stake, "sport_bet", `bet:${id}`);
  return { betId: id, totalOdds, potentialWin, balance };
});

/** Règle les sélections des matchs terminés, puis paie les tickets complets. */
export const settleBets = db.transaction(() => {
  db.run(`
    UPDATE bet_legs SET result = (
      SELECT CASE
        WHEN e.status = 'cancelled' THEN 'void'
        WHEN (bet_legs.outcome = 'home' AND e.home_score > e.away_score)
          OR (bet_legs.outcome = 'away' AND e.away_score > e.home_score)
          OR (bet_legs.outcome = 'draw' AND e.home_score = e.away_score) THEN 'won'
        ELSE 'lost' END
      FROM events e WHERE e.id = bet_legs.event_id)
    WHERE result = 'pending'
      AND event_id IN (SELECT id FROM events WHERE status IN ('finished', 'cancelled'))`);

  const ready = db
    .query(
      `SELECT id, user_id, stake FROM bets b WHERE status = 'open'
       AND NOT EXISTS (SELECT 1 FROM bet_legs WHERE bet_id = b.id AND result = 'pending')`,
    )
    .all() as { id: number; user_id: number; stake: number }[];

  for (const bet of ready) {
    const legs = db.query("SELECT price, result FROM bet_legs WHERE bet_id = ?").all(bet.id) as {
      price: number;
      result: string;
    }[];
    let status: "won" | "lost" | "void";
    let payout = 0;
    if (legs.some((l) => l.result === "lost")) status = "lost";
    else if (legs.every((l) => l.result === "void")) {
      status = "void";
      payout = bet.stake;
    } else {
      status = "won";
      // Une sélection annulée compte pour une cote de 1.
      const odds = legs.reduce((p, l) => p * (l.result === "won" ? l.price : 1), 1);
      payout = Math.floor(bet.stake * Math.round(odds * 100) / 100);
    }
    db.query("UPDATE bets SET status = ?, payout = ?, settled_at = ? WHERE id = ?").run(status, payout, Date.now(), bet.id);
    if (payout > 0) applyTx(bet.user_id, payout, status === "void" ? "sport_refund" : "sport_win", `bet:${bet.id}`);
  }
  return ready.length;
});

export function myBets(userId: number) {
  const bets = db
    .query(
      "SELECT id, stake, total_odds, potential_win, payout, status, created_at FROM bets WHERE user_id = ? ORDER BY id DESC LIMIT 30",
    )
    .all(userId) as any[];
  const legs = db.query(
    `SELECT l.outcome, l.price, l.result, e.home, e.away, e.league, e.starts_at, e.home_score, e.away_score
     FROM bet_legs l JOIN events e ON e.id = l.event_id WHERE l.bet_id = ?`,
  );
  return { bets: bets.map((b) => ({ ...b, legs: legs.all(b.id) })), balance: getBalance(userId) };
}
