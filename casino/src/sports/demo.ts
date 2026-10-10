// Flux de démo : génère des matchs fictifs entre de vraies équipes et
// les « joue » automatiquement, pour tester sans clé API.
import { db } from "../db";
import { randomFloat, randomInt } from "../rng";
import type { FeedEvent, FeedResult, Outcome } from "./types";

const LEAGUES: Record<string, { sport: string; draw: boolean; teams: string[] }> = {
  "Ligue 1": {
    sport: "football",
    draw: true,
    teams: ["PSG", "Marseille", "Lyon", "Monaco", "Lille", "Lens", "Rennes", "Nice", "Nantes", "Strasbourg"],
  },
  "Premier League": {
    sport: "football",
    draw: true,
    teams: ["Arsenal", "Liverpool", "Man City", "Chelsea", "Tottenham", "Man United", "Newcastle", "Aston Villa"],
  },
  LaLiga: {
    sport: "football",
    draw: true,
    teams: ["Real Madrid", "Barcelone", "Atlético", "Séville", "Betis", "Villarreal", "Real Sociedad", "Valence"],
  },
  "Serie A": {
    sport: "football",
    draw: true,
    teams: ["Inter", "Milan", "Juventus", "Naples", "Rome", "Lazio", "Atalanta", "Fiorentina"],
  },
  Bundesliga: {
    sport: "football",
    draw: true,
    teams: ["Bayern", "Dortmund", "Leverkusen", "Leipzig", "Francfort", "Stuttgart", "Fribourg", "Wolfsburg"],
  },
  NBA: {
    sport: "basketball",
    draw: false,
    teams: ["Celtics", "Lakers", "Warriors", "Nuggets", "Bucks", "Knicks", "Heat", "Thunder", "Mavericks", "Suns"],
  },
};

const MARGIN = 1.06;
const MIN_UPCOMING = 20;
export const demoMatchMs = () => Number(process.env.DEMO_MATCH_MINUTES ?? 10) * 60_000;

const price = (p: number) => Math.max(1.01, Math.round((100 / (p * MARGIN))) / 100);

function makeEvent(league: string, busy: Set<string>): FeedEvent | null {
  const { sport, draw } = LEAGUES[league]!;
  const teams = LEAGUES[league]!.teams.filter((t) => !busy.has(t));
  if (teams.length < 2) return null;
  const i = randomInt(teams.length);
  let j = randomInt(teams.length - 1);
  if (j >= i) j++;
  busy.add(teams[i]!).add(teams[j]!);
  const d = randomFloat() * 2 - 1; // écart de niveau, -1..1
  let odds: FeedEvent["odds"];
  if (draw) {
    const pDraw = 0.28 - 0.08 * Math.abs(d);
    const pHome = (1 - pDraw) * (0.55 + 0.35 * d);
    odds = { home: price(pHome), draw: price(pDraw), away: price(1 - pDraw - pHome) };
  } else {
    const pHome = 0.55 + 0.35 * d;
    odds = { home: price(pHome), away: price(1 - pHome) };
  }
  return {
    id: `demo-${Buffer.from(crypto.getRandomValues(new Uint8Array(8))).toString("hex")}`,
    sport,
    league,
    home: teams[i]!,
    away: teams[j]!,
    startsAt: Date.now() + (2 + randomInt(180)) * 60_000,
    odds,
  };
}

export function demoFixtures(): FeedEvent[] {
  // Une équipe ne joue qu'un match à la fois (à venir ou en cours).
  const scheduled = db
    .query("SELECT home, away FROM events WHERE id LIKE 'demo-%' AND status = 'scheduled'")
    .all() as { home: string; away: string }[];
  const busy = new Set(scheduled.flatMap((e) => [e.home, e.away]));
  const names = Object.keys(LEAGUES);
  const events: FeedEvent[] = [];
  for (let tries = 0; scheduled.length + events.length < MIN_UPCOMING && tries < 100; tries++) {
    const ev = makeEvent(names[randomInt(names.length)]!, busy);
    if (ev) events.push(ev);
  }
  return events;
}

/** Résultats tirés selon les probabilités implicites des cotes. */
export function demoResults(): FeedResult[] {
  const due = db
    .query("SELECT id, sport FROM events WHERE id LIKE 'demo-%' AND status = 'scheduled' AND starts_at <= ?")
    .all(Date.now() - demoMatchMs()) as { id: string; sport: string }[];
  return due.map(({ id, sport }) => {
    const rows = db.query("SELECT outcome, price FROM odds WHERE event_id = ?").all(id) as {
      outcome: Outcome;
      price: number;
    }[];
    const total = rows.reduce((s, r) => s + 1 / r.price, 0);
    let r = randomFloat() * total;
    let winner = rows[rows.length - 1]!.outcome;
    for (const row of rows) {
      if ((r -= 1 / row.price) < 0) {
        winner = row.outcome;
        break;
      }
    }
    const [w, l] =
      sport === "basketball"
        ? (() => {
            const w = 95 + randomInt(35);
            return [w, w - 1 - randomInt(20)];
          })()
        : (() => {
            const l = randomInt(3);
            return [l + 1 + randomInt(3), l];
          })();
    if (winner === "draw") {
      const g = randomInt(4);
      return { id, homeScore: g, awayScore: g };
    }
    return winner === "home" ? { id, homeScore: w, awayScore: l } : { id, homeScore: l, awayScore: w };
  });
}
