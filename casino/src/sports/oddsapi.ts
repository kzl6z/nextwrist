// Flux réel via The Odds API (https://the-odds-api.com).
// Coût en crédits : /odds = 1 par compétition et par marché, /scores?daysFrom = 2.
// Le plan gratuit donne 500 crédits/mois : voir ODDS_SYNC_MINUTES dans le README.
import { priceOf } from "./markets";
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

const SPORT_OF: Record<string, string> = {
  soccer: "football",
  basketball: "basketball",
  icehockey: "hockey",
  tennis: "tennis",
  rugbyunion: "rugby",
  rugbyleague: "rugby",
  mma: "mma",
  americanfootball: "americanfootball",
  baseball: "baseball",
};
const sportOf = (key: string) => SPORT_OF[key.split("_")[0]!] ?? key.split("_")[0]!;

const round2 = (x: number) => Math.round(x * 100) / 100;

/** Moyenne des cotes par issue, pour la ligne (point) la plus proposée par les bookmakers. */
function averageMarket(ev: any, marketKey: string) {
  const byPoint = new Map<string, Map<string, { total: number; n: number }>>();
  for (const bk of ev.bookmakers ?? [])
    for (const market of bk.markets ?? []) {
      if (market.key !== marketKey) continue;
      for (const o of market.outcomes ?? []) {
        // Pour les handicaps, la ligne est exprimée côté domicile.
        const point = marketKey === "spreads" ? (o.name === ev.home_team ? o.point : -o.point) : (o.point ?? "");
        const outcomes = byPoint.get(String(point)) ?? byPoint.set(String(point), new Map()).get(String(point))!;
        const name =
          marketKey === "totals" ? String(o.name).toLowerCase() : o.name === ev.home_team ? "home" : o.name === ev.away_team ? "away" : "draw";
        const acc = outcomes.get(name) ?? { total: 0, n: 0 };
        acc.total += o.price;
        acc.n++;
        outcomes.set(name, acc);
      }
    }
  let best: [string, Map<string, { total: number; n: number }>] | null = null;
  for (const entry of byPoint) {
    const n = [...entry[1].values()].reduce((s, x) => s + x.n, 0);
    const bn = best ? [...best[1].values()].reduce((s, x) => s + x.n, 0) : -1;
    if (n > bn) best = entry;
  }
  if (!best) return null;
  const prices = Object.fromEntries([...best[1]].map(([k, { total, n }]) => [k, round2(total / n)]));
  return { point: best[0], prices };
}

/** Probabilités sans marge à partir des cotes d'un même marché. */
function fair(prices: Record<string, number>) {
  const inv = Object.fromEntries(Object.entries(prices).map(([k, p]) => [k, 1 / p]));
  const total = Object.values(inv).reduce((s, x) => s + x, 0);
  return Object.fromEntries(Object.entries(inv).map(([k, x]) => [k, x / total]));
}

/** `markets` : h2h (toujours), et en option totals / spreads (1 crédit de plus chacun). */
export async function fetchOdds(key: string, sport: string, markets: string[] = ["h2h"]): Promise<FeedEvent[]> {
  const wanted = ["h2h", ...markets.filter((m) => m !== "h2h")];
  const data = await get(`/sports/${sport}/odds?regions=eu&markets=${wanted.join(",")}&oddsFormat=decimal`, key);
  const events: FeedEvent[] = [];
  for (const ev of data) {
    const h2h = averageMarket(ev, "h2h");
    if (!h2h?.prices.home || !h2h.prices.away) continue;
    const selections: FeedEvent["selections"] = {};
    const p = fair(h2h.prices);
    for (const o of Object.keys(h2h.prices)) selections[o] = { price: h2h.prices[o]!, prob: p[o]! };

    // Marchés dérivés du 1N2 : double chance et remboursé si nul.
    if (p.draw) {
      const derived: Record<string, number> = {
        "dc:1X": p.home! + p.draw,
        "dc:12": p.home! + p.away!,
        "dc:X2": p.draw + p.away!,
        "dnb:home": p.home! / (p.home! + p.away!),
        "dnb:away": p.away! / (p.home! + p.away!),
      };
      for (const [k, prob] of Object.entries(derived)) {
        const price = priceOf(k, prob);
        if (price) selections[k] = { price, prob };
      }
    }
    const totals = wanted.includes("totals") ? averageMarket(ev, "totals") : null;
    if (totals?.prices.over && totals.prices.under) {
      const f = fair(totals.prices);
      selections[`ou:${totals.point}:over`] = { price: totals.prices.over, prob: f.over! };
      selections[`ou:${totals.point}:under`] = { price: totals.prices.under, prob: f.under! };
    }
    const spreads = wanted.includes("spreads") ? averageMarket(ev, "spreads") : null;
    if (spreads?.prices.home && spreads.prices.away) {
      const f = fair(spreads.prices);
      selections[`ah:${spreads.point}:home`] = { price: spreads.prices.home, prob: f.home! };
      selections[`ah:${spreads.point}:away`] = { price: spreads.prices.away, prob: f.away! };
    }
    events.push({
      id: ev.id,
      sport: sportOf(ev.sport_key),
      league: ev.sport_title,
      home: ev.home_team,
      away: ev.away_team,
      startsAt: Date.parse(ev.commence_time),
      feedKey: ev.sport_key,
      selections,
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
