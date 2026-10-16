import { db } from "../db";
import { HttpError } from "../http";
import { applyTx, getBalance, parseStake } from "../wallet";
import { grade, type Detail } from "./markets";
import type { FeedEvent, FeedResult } from "./types";

const MAX_LEGS = 10;
const MAX_TOTAL_ODDS = 5_000;
/** Un match réel sans résultat après ce délai est annulé (paris remboursés). */
const STALE_MS = 3 * 86_400_000;
/** Part de la valeur estimée d'un pari rendue au cash out. */
const CASHOUT_RATE = 0.95;
const MAIN = ["home", "draw", "away"];

/* =========================================================
   Flux réel
   ========================================================= */
export const upsertEvents = db.transaction((events: FeedEvent[]) => {
  const now = Date.now();
  const upsert = db.query(
    `INSERT INTO events (id, sport, league, home, away, starts_at, feed_key, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET starts_at = excluded.starts_at, updated_at = excluded.updated_at
     WHERE events.status = 'scheduled'`,
  );
  const close = db.query("UPDATE selections SET price = NULL WHERE event_id = ?");
  const setSel = db.query(
    `INSERT INTO selections (event_id, key, price, prob) VALUES (?, ?, ?, ?)
     ON CONFLICT(event_id, key) DO UPDATE SET price = excluded.price, prob = excluded.prob`,
  );
  for (const e of events) {
    if (e.startsAt <= now) continue;
    upsert.run(e.id, e.sport, e.league, e.home, e.away, e.startsAt, e.feedKey ?? null, now);
    close.run(e.id);
    for (const [key, s] of Object.entries(e.selections)) setSel.run(e.id, key, s.price, s.prob);
  }
});

export const applyResults = db.transaction((results: FeedResult[]) => {
  const finish = db.query(
    `UPDATE events SET status = 'finished', home_score = ?, away_score = ?, clock = 'Terminé', updated_at = ?
     WHERE id = ? AND status = 'scheduled' AND virtual = 0`,
  );
  for (const r of results) finish.run(r.homeScore, r.awayScore, Date.now(), r.id);
  db.query(
    "UPDATE events SET status = 'cancelled', updated_at = ?1 WHERE status = 'scheduled' AND virtual = 0 AND starts_at < ?2",
  ).run(Date.now(), Date.now() - STALE_MS);
});

/** Compétitions ayant au moins un match commencé depuis assez longtemps pour être fini. */
export function feedKeysAwaitingResults(minAgeMs: number): string[] {
  return (
    db
      .query(
        `SELECT DISTINCT feed_key FROM events
         WHERE status = 'scheduled' AND virtual = 0 AND feed_key IS NOT NULL AND starts_at < ?`,
      )
      .all(Date.now() - minAgeMs) as { feed_key: string }[]
  ).map((r) => r.feed_key);
}

/* =========================================================
   Lecture
   ========================================================= */
interface EventRow {
  id: string;
  sport: string;
  league: string;
  home: string;
  away: string;
  starts_at: number;
  status: string;
  virtual: number;
  clock: string | null;
  home_score: number | null;
  away_score: number | null;
  detail: string | null;
  suspended_until: number | null;
}

const EVENT_COLS = `e.id, e.sport, e.league, e.home, e.away, e.starts_at, e.status, e.virtual, e.clock,
  e.home_score, e.away_score, e.detail, e.suspended_until`;

/** Un match est-il ouvert aux paris (avant le coup d'envoi, ou en direct pour les virtuels) ? */
const isOpen = (e: EventRow, now: number) =>
  (e.status === "scheduled" && e.starts_at > now) || (e.status === "live" && e.virtual === 1);

function present(e: EventRow, now: number, full = false) {
  const live = e.status === "live" || (e.status === "scheduled" && e.starts_at <= now);
  const detail = e.detail ? (JSON.parse(e.detail) as Detail) : null;
  return {
    id: e.id,
    sport: e.sport,
    league: e.league,
    home: e.home,
    away: e.away,
    starts_at: e.starts_at,
    status: e.status,
    virtual: !!e.virtual,
    live,
    open: isOpen(e, now),
    suspended: (e.suspended_until ?? 0) > now,
    clock: e.clock,
    score: live || e.status === "finished" ? [e.home_score ?? 0, e.away_score ?? 0] : null,
    // Les listes n'ont besoin que des derniers faits de jeu.
    detail: detail && !full ? { ...detail, timeline: detail.timeline?.slice(-3) } : detail,
  };
}

function withMainOdds(rows: EventRow[], now: number) {
  if (!rows.length) return [];
  const ids = rows.map((r) => r.id);
  const odds = db
    .query(
      `SELECT event_id, key, price FROM selections
       WHERE event_id IN (${ids.map(() => "?").join(",")}) AND price IS NOT NULL`,
    )
    .all(...ids) as { event_id: string; key: string; price: number }[];
  const main = new Map<string, Record<string, number>>();
  const count = new Map<string, number>();
  for (const o of odds) {
    count.set(o.event_id, (count.get(o.event_id) ?? 0) + 1);
    if (MAIN.includes(o.key)) (main.get(o.event_id) ?? main.set(o.event_id, {}).get(o.event_id)!)[o.key] = o.price;
  }
  return rows.map((e) => ({ ...present(e, now), odds: main.get(e.id) ?? {}, markets: count.get(e.id) ?? 0 }));
}

export function listEvents() {
  const now = Date.now();
  const rows = db
    .query(`SELECT ${EVENT_COLS} FROM events e WHERE e.status = 'scheduled' AND e.starts_at > ? ORDER BY e.starts_at LIMIT 250`)
    .all(now) as EventRow[];
  return withMainOdds(rows, now);
}

/** Matchs en cours : virtuels en direct (cotes ouvertes) et réels commencés (paris fermés). */
export function liveEvents() {
  const now = Date.now();
  const rows = db
    .query(
      `SELECT ${EVENT_COLS} FROM events e
       WHERE e.status = 'live' OR (e.status = 'scheduled' AND e.virtual = 0 AND e.starts_at <= ? AND e.starts_at > ?)
       ORDER BY e.starts_at LIMIT 60`,
    )
    .all(now, now - 3 * 60 * 60_000) as EventRow[];
  return withMainOdds(rows, now);
}

export function recentResults() {
  const now = Date.now();
  return (
    db
      .query(`SELECT ${EVENT_COLS} FROM events e WHERE e.status IN ('finished', 'cancelled') ORDER BY e.updated_at DESC LIMIT 24`)
      .all() as EventRow[]
  ).map((e) => present(e, now));
}

export function eventDetail(id: string) {
  const now = Date.now();
  const e = db.query(`SELECT ${EVENT_COLS} FROM events e WHERE e.id = ?`).get(id) as EventRow | null;
  if (!e) throw new HttpError(404, "Match introuvable");
  const rows = db.query("SELECT key, price FROM selections WHERE event_id = ?").all(id) as { key: string; price: number | null }[];
  const selections: Record<string, number | null> = {};
  for (const r of rows) selections[r.key] = r.price;
  return { ...present(e, now, true), selections };
}

/* =========================================================
   Prise de pari
   ========================================================= */
export const placeBet = db.transaction((userId: number, rawLegs: unknown, rawStake: unknown, acceptChanges: unknown) => {
  const stake = parseStake(rawStake);
  if (!Array.isArray(rawLegs) || rawLegs.length === 0) throw new HttpError(400, "Ticket vide");
  if (rawLegs.length > MAX_LEGS) throw new HttpError(400, `Maximum ${MAX_LEGS} sélections`);

  const now = Date.now();
  const seen = new Set<string>();
  let changed = false;
  const legs = rawLegs.map((l: any) => {
    const eventId = String(l?.eventId ?? "");
    const key = String(l?.key ?? l?.outcome ?? "");
    if (!eventId || !key || key.length > 40) throw new HttpError(400, "Sélection invalide");
    if (seen.has(eventId)) throw new HttpError(400, "Un seul pronostic par match dans un combiné");
    seen.add(eventId);
    const row = db
      .query(
        `SELECT ${EVENT_COLS}, s.price FROM events e JOIN selections s ON s.event_id = e.id WHERE e.id = ? AND s.key = ?`,
      )
      .get(eventId, key) as (EventRow & { price: number | null }) | null;
    if (!row) throw new HttpError(404, "Match ou pronostic introuvable");
    const name = `${row.home} - ${row.away}`;
    if (!isOpen(row, now)) throw new HttpError(400, `${name} : les paris sont fermés`);
    if ((row.suspended_until ?? 0) > now) throw new HttpError(409, `${name} : marché suspendu quelques secondes`);
    if (row.price === null) throw new HttpError(409, `${name} : ce pronostic n'est plus proposé`);
    if (Number(l?.price) !== row.price) {
      if (acceptChanges !== true) throw new HttpError(409, `La cote de ${name} a changé, vérifie ton ticket`);
      changed = true;
    }
    return { eventId, key, price: row.price };
  });

  const totalOdds = Math.round(legs.reduce((p, l) => p * l.price, 1) * 100) / 100;
  if (totalOdds > MAX_TOTAL_ODDS) throw new HttpError(400, `Cote totale maximum : ${MAX_TOTAL_ODDS}`);
  const potentialWin = Math.floor(stake * totalOdds);
  const { id } = db
    .query(
      "INSERT INTO bets (user_id, stake, total_odds, potential_win, created_at) VALUES (?, ?, ?, ?, ?) RETURNING id",
    )
    .get(userId, stake, totalOdds, potentialWin, now) as { id: number };
  const insertLeg = db.query("INSERT INTO bet_legs (bet_id, event_id, outcome, price) VALUES (?, ?, ?, ?)");
  for (const l of legs) insertLeg.run(id, l.eventId, l.key, l.price);
  const balance = applyTx(userId, -stake, "sport_bet", `bet:${id}`);
  return { betId: id, totalOdds, potentialWin, balance, changed };
});

/* =========================================================
   Règlement
   ========================================================= */
/** Règle les sélections des matchs terminés, puis paie les tickets complets. */
export const settleBets = db.transaction(() => {
  const pending = db
    .query(
      `SELECT l.rowid AS rid, l.outcome, e.status, e.home_score, e.away_score, e.detail
       FROM bet_legs l JOIN events e ON e.id = l.event_id
       WHERE l.result = 'pending' AND e.status IN ('finished', 'cancelled')`,
    )
    .all() as { rid: number; outcome: string; status: string; home_score: number | null; away_score: number | null; detail: string | null }[];
  const setResult = db.query("UPDATE bet_legs SET result = ? WHERE rowid = ?");
  for (const l of pending)
    setResult.run(grade(l.outcome, { ...l, detail: l.detail ? JSON.parse(l.detail) : null }), l.rid);

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
      // Une sélection remboursée compte pour une cote de 1.
      const odds = legs.reduce((p, l) => p * (l.result === "won" ? l.price : 1), 1);
      payout = Math.floor((bet.stake * Math.round(odds * 100)) / 100);
    }
    db.query("UPDATE bets SET status = ?, payout = ?, settled_at = ? WHERE id = ?").run(status, payout, Date.now(), bet.id);
    if (payout > 0) applyTx(bet.user_id, payout, status === "void" ? "sport_refund" : "sport_win", `bet:${bet.id}`);
  }
  return ready.length;
});

/* =========================================================
   Cash out
   ========================================================= */
interface LegState {
  outcome: string;
  price: number;
  result: string;
  status: string;
  virtual: number;
  starts_at: number;
  suspended_until: number | null;
  prob: number | null;
}

/** Montant proposé pour solder le pari maintenant, ou null si indisponible. */
function cashoutValue(bet: { id: number; stake: number; potential_win: number }, now: number): number | null {
  const legs = db
    .query(
      `SELECT l.outcome, l.price, l.result, e.status, e.virtual, e.starts_at, e.suspended_until, s.prob
       FROM bet_legs l JOIN events e ON e.id = l.event_id
       LEFT JOIN selections s ON s.event_id = l.event_id AND s.key = l.outcome
       WHERE l.bet_id = ?`,
    )
    .all(bet.id) as LegState[];
  let value = bet.stake;
  for (const l of legs) {
    if (l.result === "lost") return null;
    if (l.result === "won") value *= l.price;
    else if (l.result === "pending") {
      const open = (l.status === "scheduled" && l.starts_at > now) || (l.status === "live" && l.virtual === 1);
      if (!open || l.prob === null || (l.suspended_until ?? 0) > now) return null;
      value *= l.price * l.prob;
    }
  }
  const amount = Math.min(bet.potential_win, Math.floor(value * CASHOUT_RATE));
  return amount >= 1 ? amount : null;
}

export const cashOut = db.transaction((userId: number, rawBetId: unknown, rawExpected: unknown) => {
  const betId = Number(rawBetId);
  const bet = db
    .query("SELECT id, stake, potential_win, status FROM bets WHERE id = ? AND user_id = ?")
    .get(betId, userId) as { id: number; stake: number; potential_win: number; status: string } | null;
  if (!bet) throw new HttpError(404, "Pari introuvable");
  if (bet.status !== "open") throw new HttpError(400, "Ce pari est déjà réglé");
  const value = cashoutValue(bet, Date.now());
  if (value === null) throw new HttpError(409, "Cash out indisponible pour le moment", { value: null });
  const expected = Number(rawExpected);
  if (Number.isFinite(expected) && value < expected)
    throw new HttpError(409, `Le montant a changé : ${value.toLocaleString("fr-FR")}`, { value });
  db.query("UPDATE bets SET status = 'cashout', payout = ?, settled_at = ? WHERE id = ?").run(value, Date.now(), bet.id);
  const balance = applyTx(userId, value, "sport_cashout", `bet:${bet.id}`);
  return { value, balance };
});

export function myBets(userId: number) {
  const now = Date.now();
  const bets = db
    .query(
      "SELECT id, stake, total_odds, potential_win, payout, status, created_at FROM bets WHERE user_id = ? ORDER BY id DESC LIMIT 40",
    )
    .all(userId) as { id: number; stake: number; potential_win: number; status: string }[];
  const legs = db.query(
    `SELECT l.event_id, l.outcome, l.price, l.result, e.sport, e.home, e.away, e.league, e.starts_at, e.status,
       e.home_score, e.away_score, e.clock
     FROM bet_legs l JOIN events e ON e.id = l.event_id WHERE l.bet_id = ?`,
  );
  return {
    bets: bets.map((b) => ({
      ...b,
      legs: legs.all(b.id),
      cashout: b.status === "open" ? cashoutValue(b, now) : null,
    })),
    balance: getBalance(userId),
  };
}
