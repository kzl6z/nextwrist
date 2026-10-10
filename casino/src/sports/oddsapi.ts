// Flux réel via The Odds API (https://the-odds-api.com).
// Coût en crédits : /odds = 1 par compétition et par marché, /scores?daysFrom = 2.
// Le plan gratuit donne 500 crédits/mois : voir ODDS_SYNC_MINUTES dans le README.
import type { FeedEvent, FeedResult } from "./types";

const BASE = "https://api.the-odds-api.com/v4";

export const quota = { remaining: null as number | null, used: null as number | null };

async function get(path: string, key: string): Promise<any[]> {
  const url = `${BASE}${path}${path.includes("?") ? "&" : "?"}apiKey=${encodeURIComponent(key)}`;
  const res = await fetch(url);
  const remaining = res.headers.get("x-requests-remaining");
  const used = res.headers.get("x-requests-used");
  if (remaining !== null) quota.remaining = Number(remaining);
  if (used !== null) quota.used = Number(used);
  if (res.status === 401) throw new Error("The Odds API : clé invalide (ODDS_API_KEY)");
  if (res.status === 429) throw new Error("The Odds API : quota épuisé ou trop de requêtes");
  if (!res.ok) throw new Error(`The Odds API ${res.status} sur ${path} : ${await res.text()}`);
  return res.json();
}

function sportOf(key: string) {
  const group = key.split("_")[0]!;
  return group === "soccer" ? "football" : group;
}

export async function fetchOdds(key: string, sport: string): Promise<FeedEvent[]> {
  const data = await get(`/sports/${sport}/odds?regions=eu&markets=h2h&oddsFormat=decimal`, key);
  const events: FeedEvent[] = [];
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
      feedKey: ev.sport_key,
      odds,
    });
  }
  return events;
}

export async function fetchResults(key: string, sport: string): Promise<FeedResult[]> {
  const data = await get(`/sports/${sport}/scores?daysFrom=3`, key);
  const results: FeedResult[] = [];
  for (const ev of data) {
    if (!ev.completed || !ev.scores) continue;
    const score = (team: string) => Number(ev.scores.find((s: any) => s.name === team)?.score);
    const homeScore = score(ev.home_team);
    const awayScore = score(ev.away_team);
    if (Number.isFinite(homeScore) && Number.isFinite(awayScore)) results.push({ id: ev.id, homeScore, awayScore });
  }
  return results;
}
