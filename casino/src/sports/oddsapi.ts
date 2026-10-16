// Flux réel via The Odds API (https://the-odds-api.com).
// Coût en crédits : /sports = 0 ; /odds = 1 par marché et par région ;
// /events/{id}/odds = 1 par marché renvoyé et par région ; /scores = 1 (2 avec daysFrom).
import { priceOf } from "./markets";
import type { FeedEvent, FeedResult } from "./types";

const BASE = "https://api.the-odds-api.com/v4";

export const quota = { remaining: null as number | null, used: null as number | null, spent: 0 };

async function get(path: string, key: string): Promise<any> {
  const url = `${BASE}${path}${path.includes("?") ? "&" : "?"}apiKey=${encodeURIComponent(key)}`;
  const res = await fetch(url);
  const remaining = res.headers.get("x-requests-remaining");
  const used = res.headers.get("x-requests-used");
  const last = res.headers.get("x-requests-last");
  if (remaining !== null) quota.remaining = Number(remaining);
  if (used !== null) quota.used = Number(used);
  if (last !== null) quota.spent += Number(last) || 0;
  if (res.status === 401) throw new Error("The Odds API : clé invalide (ODDS_API_KEY)");
  if (res.status === 429) throw new Error("The Odds API : quota épuisé ou trop de requêtes");
  if (res.status === 422) return [];
  if (!res.ok) throw new Error(`The Odds API ${res.status} sur ${path.split("?")[0]} : ${(await res.text()).slice(0, 200)}`);
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
  boxing: "boxing",
  americanfootball: "americanfootball",
  baseball: "baseball",
  cricket: "cricket",
  aussierules: "aussierules",
  handball: "handball",
  volleyball: "volleyball",
  lacrosse: "lacrosse",
  golf: "golf",
};
export const sportOf = (key: string) => SPORT_OF[key.split("_")[0]!] ?? key.split("_")[0]!;

/* =========================================================
   Liste des sports (gratuit)
   ========================================================= */
export interface FeedSport {
  key: string;
  group: string;
  title: string;
  active: boolean;
  has_outrights: boolean;
}

/** Compétitions en cours, hors paris « vainqueur final » (outrights). */
export async function listSports(key: string): Promise<FeedSport[]> {
  const data = (await get("/sports", key)) as FeedSport[];
  return data.filter((s) => s.active && !s.has_outrights);
}

/* =========================================================
   Lecture des marchés
   ========================================================= */
type Prices = Record<string, number>;
const round2 = (x: number) => Math.round(x * 100) / 100;

/** Nom d'issue normalisé : home / away / draw, over / under, yes / no. */
function outcomeName(ev: any, marketKey: string, o: any): string {
  if (marketKey.includes("totals")) return String(o.name).toLowerCase();
  if (marketKey === "btts") return String(o.name).toLowerCase();
  return o.name === ev.home_team ? "home" : o.name === ev.away_team ? "away" : "draw";
}

/** Ligne exprimée côté domicile (handicaps), sinon telle quelle. */
function pointOf(ev: any, marketKey: string, o: any): string {
  if (o.point === undefined || o.point === null) return "";
  if (marketKey.includes("spreads")) return String(o.name === ev.home_team ? o.point : -o.point);
  return String(o.point);
}

/** Pour les totaux par équipe : à quelle équipe se rapporte l'issue (champ description). */
function teamOf(ev: any, o: any): "home" | "away" | null {
  const d = o.description;
  return d === ev.home_team ? "home" : d === ev.away_team ? "away" : null;
}

/** Cotes moyennes par (ligne, issue) sur tous les bookmakers, avec le nombre de bookmakers. */
function collect(ev: any, marketKey: string, team?: "home" | "away") {
  const byPoint = new Map<string, Map<string, { total: number; n: number }>>();
  for (const bk of ev.bookmakers ?? [])
    for (const market of bk.markets ?? []) {
      if (market.key !== marketKey) continue;
      for (const o of market.outcomes ?? []) {
        if (team && teamOf(ev, o) !== team) continue;
        if (!(o.price > 1)) continue;
        const point = pointOf(ev, marketKey, o);
        const outcomes = byPoint.get(point) ?? byPoint.set(point, new Map()).get(point)!;
        const name = outcomeName(ev, marketKey, o);
        const acc = outcomes.get(name) ?? { total: 0, n: 0 };
        acc.total += o.price;
        acc.n++;
        outcomes.set(name, acc);
      }
    }
  return [...byPoint].map(([point, outcomes]) => ({
    point,
    n: [...outcomes.values()].reduce((s, x) => s + x.n, 0),
    prices: Object.fromEntries([...outcomes].map(([k, { total, n }]) => [k, round2(total / n)])) as Prices,
  }));
}

/** La ligne proposée par le plus de bookmakers (marchés principaux). */
function mainLine(ev: any, marketKey: string, team?: "home" | "away") {
  const lines = collect(ev, marketKey, team);
  return lines.sort((a, b) => b.n - a.n)[0] ?? null;
}

/** Probabilités sans marge à partir des cotes d'un même marché. */
function fair(prices: Prices) {
  const inv = Object.fromEntries(Object.entries(prices).map(([k, p]) => [k, 1 / p]));
  const total = Object.values(inv).reduce((s, x) => s + x, 0);
  return Object.fromEntries(Object.entries(inv).map(([k, x]) => [k, x / total]));
}

/**
 * Lignes entières ou à demi-point uniquement (les lignes entières sont remboursées en cas
 * d'égalité). Les lignes asiatiques en quart de point, qui partagent la mise, sont ignorées.
 */
const lineKey = (point: string) => {
  const L = Number(point);
  return point !== "" && Number.isFinite(L) && Number.isInteger(L * 2) ? String(L) : null;
};

type Selections = FeedEvent["selections"];

function addPair(out: Selections, prices: Prices, keys: Record<string, string>) {
  const names = Object.keys(keys);
  if (!names.every((n) => prices[n])) return;
  const f = fair(Object.fromEntries(names.map((n) => [n, prices[n]!])));
  for (const n of names) out[keys[n]!] = { price: prices[n]!, prob: f[n]! };
}

/** Convertit les marchés d'un événement en pronostics (clés de markets.ts). */
export function parseMarkets(ev: any, out: Selections = {}): Selections {
  const keys = new Set<string>((ev.bookmakers ?? []).flatMap((b: any) => (b.markets ?? []).map((m: any) => m.key)));

  // 1N2 et marchés dérivés.
  const h2h = keys.has("h2h") ? mainLine(ev, "h2h") : null;
  if (h2h?.prices.home && h2h.prices.away) {
    const p = fair(h2h.prices);
    for (const o of Object.keys(h2h.prices)) out[o] = { price: h2h.prices[o]!, prob: p[o]! };
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
        if (price) out[k] = { price, prob };
      }
    }
  }
  // Handicap et total : ligne principale, puis lignes alternatives.
  for (const [market, all] of [
    ["spreads", false],
    ["alternate_spreads", true],
  ] as const) {
    if (!keys.has(market)) continue;
    for (const line of all ? collect(ev, market) : [mainLine(ev, market)].filter(Boolean)) {
      const L = lineKey(line!.point);
      if (L !== null) addPair(out, line!.prices, { home: `ah:${L}:home`, away: `ah:${L}:away` });
    }
  }
  for (const [market, all] of [
    ["totals", false],
    ["alternate_totals", true],
  ] as const) {
    if (!keys.has(market)) continue;
    for (const line of all ? collect(ev, market) : [mainLine(ev, market)].filter(Boolean)) {
      const L = lineKey(line!.point);
      if (L !== null) addPair(out, line!.prices, { over: `ou:${L}:over`, under: `ou:${L}:under` });
    }
  }
  // Totaux par équipe.
  for (const [market, all] of [
    ["team_totals", false],
    ["alternate_team_totals", true],
  ] as const) {
    if (!keys.has(market)) continue;
    for (const team of ["home", "away"] as const) {
      const prefix = team === "home" ? "th" : "ta";
      for (const line of all ? collect(ev, market, team) : [mainLine(ev, market, team)].filter(Boolean)) {
        const L = lineKey(line!.point);
        if (L !== null) addPair(out, line!.prices, { over: `${prefix}:${L}:over`, under: `${prefix}:${L}:under` });
      }
    }
  }
  // Les deux équipes marquent, remboursé si nul (cotes réelles plutôt que dérivées).
  if (keys.has("btts")) {
    const line = mainLine(ev, "btts");
    if (line) addPair(out, line.prices, { yes: "btts:yes", no: "btts:no" });
  }
  if (keys.has("draw_no_bet")) {
    const line = mainLine(ev, "draw_no_bet");
    if (line) addPair(out, line.prices, { home: "dnb:home", away: "dnb:away" });
  }
  return out;
}

/* =========================================================
   Appels
   ========================================================= */
export const REGIONS = (process.env.ODDS_REGIONS ?? "eu").replace(/\s/g, "");

/** Cotes de toutes les rencontres d'une compétition (à venir et en cours). */
export async function fetchOdds(key: string, sport: string, markets: string[] = ["h2h"]): Promise<FeedEvent[]> {
  const wanted = ["h2h", ...markets.filter((m) => m !== "h2h")];
  const data = await get(`/sports/${sport}/odds?regions=${REGIONS}&markets=${wanted.join(",")}&oddsFormat=decimal`, key);
  const events: FeedEvent[] = [];
  for (const ev of data) {
    const selections = parseMarkets(ev);
    if (!selections.home || !selections.away) continue;
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

/** Marchés supplémentaires demandés pour un match, selon le sport. */
export function extraMarketsFor(sportKey: string): string[] {
  const group = sportKey.split("_")[0]!;
  if (group === "soccer") return ["btts", "draw_no_bet", "alternate_totals", "alternate_spreads", "team_totals"];
  if (["americanfootball", "basketball", "baseball", "icehockey"].includes(group))
    return ["alternate_spreads", "alternate_totals", "team_totals", "alternate_team_totals"];
  return ["alternate_spreads", "alternate_totals"];
}

/** Marchés supplémentaires d'un seul match (endpoint par événement). */
export async function fetchEventOdds(key: string, sportKey: string, eventId: string): Promise<FeedEvent["selections"] | null> {
  const markets = ["h2h", "spreads", "totals", ...extraMarketsFor(sportKey)];
  const ev = await get(
    `/sports/${sportKey}/events/${encodeURIComponent(eventId)}/odds?regions=${REGIONS}&markets=${markets.join(",")}&oddsFormat=decimal`,
    key,
  );
  if (!ev || Array.isArray(ev)) return null;
  return parseMarkets(ev);
}

export interface FeedScore extends FeedResult {
  completed: boolean;
}

/** Scores : matchs en cours (sans daysFrom) ou terminés des derniers jours (avec daysFrom). */
export async function fetchScores(key: string, sport: string, daysFrom?: number): Promise<FeedScore[]> {
  const data = await get(`/sports/${sport}/scores${daysFrom ? `?daysFrom=${daysFrom}` : ""}`, key);
  const results: FeedScore[] = [];
  for (const ev of data) {
    if (!ev.scores) continue;
    const score = (team: string) => Number(ev.scores.find((s: any) => s.name === team)?.score);
    const homeScore = score(ev.home_team);
    const awayScore = score(ev.away_team);
    if (Number.isFinite(homeScore) && Number.isFinite(awayScore))
      results.push({ id: ev.id, homeScore, awayScore, completed: !!ev.completed });
  }
  return results;
}

/** Compatibilité : résultats des matchs terminés uniquement. */
export async function fetchResults(key: string, sport: string): Promise<FeedResult[]> {
  return (await fetchScores(key, sport, 3)).filter((r) => r.completed);
}
