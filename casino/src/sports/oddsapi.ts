// Flux réel via The Odds API (https://the-odds-api.com). Le plan gratuit a un
// quota mensuel de requêtes : chaque synchro coûte ~2 requêtes par sport.
import type { FeedEvent, FeedResult } from "./types";

const BASE = "https://api.the-odds-api.com/v4";

async function get(path: string, key: string): Promise<any[]> {
  const url = `${BASE}${path}${path.includes("?") ? "&" : "?"}apiKey=${encodeURIComponent(key)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`The Odds API ${res.status}: ${await res.text()}`);
  return res.json();
}

function sportOf(key: string) {
  return key.split("_")[0] === "soccer" ? "football" : key.split("_")[0]!;
}

export async function fetchOdds(key: string, sports: string[]): Promise<FeedEvent[]> {
  const events: FeedEvent[] = [];
  for (const sport of sports) {
    const data = await get(`/sports/${sport}/odds?regions=eu&markets=h2h&oddsFormat=decimal`, key);
    for (const ev of data) {
      // Moyenne des cotes de tous les bookmakers pour chaque issue.
      const sums: Record<string, { total: number; n: number }> = {};
      for (const bk of ev.bookmakers ?? [])
        for (const market of bk.markets ?? [])
          if (market.key === "h2h")
            for (const o of market.outcomes ?? []) {
              const outcome = o.name === ev.home_team ? "home" : o.name === ev.away_team ? "away" : "draw";
              (sums[outcome] ??= { total: 0, n: 0 }).total += o.price;
              sums[outcome]!.n++;
            }
      const odds = Object.fromEntries(
        Object.entries(sums).map(([k, { total, n }]) => [k, Math.round((total / n) * 100) / 100]),
      );
      if (!odds.home || !odds.away) continue;
      events.push({
        id: ev.id,
        sport: sportOf(ev.sport_key),
        league: ev.sport_title,
        home: ev.home_team,
        away: ev.away_team,
        startsAt: Date.parse(ev.commence_time),
        odds,
      });
    }
  }
  return events;
}

export async function fetchResults(key: string, sports: string[]): Promise<FeedResult[]> {
  const results: FeedResult[] = [];
  for (const sport of sports) {
    const data = await get(`/sports/${sport}/scores?daysFrom=3`, key);
    for (const ev of data) {
      if (!ev.completed || !ev.scores) continue;
      const score = (team: string) => Number(ev.scores.find((s: any) => s.name === team)?.score);
      const homeScore = score(ev.home_team);
      const awayScore = score(ev.away_team);
      if (Number.isFinite(homeScore) && Number.isFinite(awayScore)) results.push({ id: ev.id, homeScore, awayScore });
    }
  }
  return results;
}
