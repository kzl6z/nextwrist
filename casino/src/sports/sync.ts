import {
  applyResults,
  applyScores,
  feedConfig,
  feedHooks,
  feedKeysAwaitingResults,
  feedKeysLive,
  settleBets,
  storeDeepMarkets,
  upsertEvents,
} from "./betting";
import { applyLiveStates, engineFeedKeys, enginePrematch, tickEngine } from "./engine";
import { extraMarketsFor, fetchEventOdds, fetchOdds, fetchResults, fetchScores, listSports, quota, REGIONS } from "./oddsapi";
import { tickVirtual } from "./sim";

const env = process.env;
const KEY = env.ODDS_API_KEY;
/** "all" : toutes les compétitions en cours chez le fournisseur ; sinon une liste de clés. */
const SPORTS_SETTING = (env.ODDS_SPORTS ?? "soccer_france_ligue_one,soccer_epl,soccer_uefa_champs_league").trim();
const ALL_SPORTS = SPORTS_SETTING === "all";
/** Marchés demandés pour toutes les rencontres (chacun coûte 1 crédit par compétition). */
const MARKETS = (env.ODDS_MARKETS ?? "h2h")
  .split(",")
  .map((s) => s.trim())
  .filter((m) => ["h2h", "totals", "spreads"].includes(m));
/** Crédits de l'abonnement par mois : le rythme des mises à jour s'adapte à ce budget. */
const MONTHLY_CREDITS = Math.max(100, Number(env.ODDS_MONTHLY_CREDITS ?? 500));
/** Délai minimum entre deux mises à jour d'une même compétition (matchs à venir). */
const MIN_REFRESH_MS = Number(env.ODDS_SYNC_MINUTES ?? 30) * 60_000;
/** Recherche des résultats des matchs commencés depuis plus de 2 h. */
const SCORES_EVERY_MS = Number(env.SCORES_SYNC_MINUTES ?? 60) * 60_000;
/** Direct sur les vrais matchs (nécessite un abonnement avec assez de crédits). */
const LIVE = env.ODDS_LIVE === "on";
const LIVE_EVERY_MS = Math.max(15, Number(env.ODDS_LIVE_SECONDS ?? 60)) * 1000;
/**
 * Moteur de cotes maison : pendant les vrais matchs, seuls les scores sont demandés au fournisseur
 * (1 crédit par compétition), et nos modèles recalculent toutes les cotes. Ignoré si ODDS_LIVE=on.
 */
const ENGINE = !LIVE && env.ODDS_LIVE_ENGINE === "on";
const ENGINE_EVERY_MS = Math.max(15, Number(env.ODDS_LIVE_ENGINE_SECONDS ?? 60)) * 1000;
/** Recalcul des cotes en direct par le moteur (le temps qui passe fait bouger les cotes). */
const ENGINE_TICK_MS = 10_000;
/** Marchés supplémentaires chargés à l'ouverture d'une fiche match. */
const EXTRA = env.ODDS_EXTRA_MARKETS !== "off";
const EXTRA_EVERY_MS = Number(env.ODDS_EXTRA_MINUTES ?? 15) * 60_000;
/** Pas du moteur des matchs virtuels. */
const VIRTUAL_TICK_MS = 3_000;
const MATCH_MIN_MS = 2 * 60 * 60_000;
const regions = REGIONS.split(",").length;

export const feedMode = KEY ? "the-odds-api" : "demo";
/** Matchs virtuels (direct et cash out en cours de match) : toujours actifs sans clé, désactivables avec. */
export const virtualOn = !KEY || env.VIRTUAL_SPORTS !== "off";

/* ---------- Budget de crédits : un réservoir qui se remplit au fil du mois ---------- */
class Bucket {
  tokens: number;
  readonly cap: number;
  private last = Date.now();
  constructor(
    private readonly perMs: number,
    minCap: number,
  ) {
    this.cap = Math.max(minCap, perMs * 86_400_000);
    this.tokens = this.cap;
  }
  private refill() {
    const now = Date.now();
    this.tokens = Math.min(this.cap, this.tokens + (now - this.last) * this.perMs);
    this.last = now;
  }
  can(cost: number) {
    this.refill();
    return this.tokens >= cost;
  }
  spend(cost: number) {
    this.tokens -= cost;
  }
}
const perMs = MONTHLY_CREDITS / (30 * 86_400_000);
const shares = LIVE
  ? { upcoming: 0.45, live: 0.35, extra: 0.2 }
  : ENGINE
    ? { upcoming: 0.5, live: 0.3, extra: 0.2 }
    : { upcoming: 0.7, live: 0, extra: 0.3 };
const buckets = {
  upcoming: new Bucket(perMs * shares.upcoming, MARKETS.length * regions + 2),
  live: new Bucket(perMs * shares.live, ENGINE ? 4 : MARKETS.length * regions + 1),
  extra: new Bucket(perMs * shares.extra, 12 * regions),
};

/** Coût réel d'un appel, lu dans les en-têtes de la réponse. */
async function metered<T>(bucket: Bucket, estimate: number, call: () => Promise<T>): Promise<T> {
  const before = quota.spent;
  bucket.spend(estimate);
  try {
    return await call();
  } finally {
    const actual = quota.spent - before;
    if (actual) bucket.spend(actual - estimate);
  }
}
/** Réserve de sécurité : en dessous, seuls les résultats sont encore demandés. */
const lowOnCredits = () => quota.remaining !== null && quota.remaining < 25;

/* ---------- État du flux ---------- */
let sports: string[] = ALL_SPORTS ? [] : SPORTS_SETTING.split(",").map((s) => s.trim()).filter(Boolean);
let sportsAt = 0;
const lastOdds = new Map<string, number>();
const lastLive = new Map<string, number>();
let lastResults = 0;
const extraQueue = new Map<string, { sportKey: string; live: boolean }>();
const extraInFlight = new Set<string>();
const oddsCost = () => MARKETS.length * regions;

function settle() {
  const settled = settleBets();
  if (settled) console.log(`[sports] ${settled} ticket(s) réglé(s)`);
}

async function refreshSportsList() {
  if (!ALL_SPORTS || Date.now() - sportsAt < 12 * 3_600_000) return;
  sportsAt = Date.now();
  const list = await listSports(KEY!);
  sports = list.map((s) => s.key);
  console.log(`[sports] ${sports.length} compétitions disponibles chez The Odds API`);
}

async function refreshOdds(sport: string, bucket: Bucket) {
  const events = await metered(bucket, oddsCost(), () => fetchOdds(KEY!, sport, MARKETS));
  upsertEvents(events);
  lastOdds.set(sport, Date.now());
  return events.length;
}

/** Direct : cotes en cours de match et scores des compétitions qui ont un match commencé. */
async function liveStep() {
  if (!LIVE || lowOnCredits()) return;
  const now = Date.now();
  for (const sport of feedKeysLive()) {
    if (now - (lastLive.get(sport) ?? 0) < LIVE_EVERY_MS) continue;
    if (!buckets.live.can(oddsCost() + 1)) return;
    lastLive.set(sport, now);
    await refreshOdds(sport, buckets.live);
    applyScores(await metered(buckets.live, 1, () => fetchScores(KEY!, sport)));
    settle();
  }
}

/** Moteur maison : scores des compétitions en cours, puis recalcul immédiat des cotes. */
async function engineStep() {
  if (!ENGINE || lowOnCredits()) return;
  const now = Date.now();
  for (const sport of engineFeedKeys(now)) {
    if (now - (lastLive.get(sport) ?? 0) < ENGINE_EVERY_MS) continue;
    if (!buckets.live.can(1)) return;
    lastLive.set(sport, now);
    const scores = await metered(buckets.live, 1, () => fetchScores(KEY!, sport));
    applyLiveStates(scores);
    tickEngine();
    settle();
  }
}

/** Matchs à venir : la compétition la moins récemment mise à jour d'abord. */
async function upcomingStep() {
  if (lowOnCredits()) return;
  const now = Date.now();
  const due = sports
    .map((s) => [s, lastOdds.get(s) ?? 0] as const)
    .filter(([, at]) => now - at >= MIN_REFRESH_MS)
    .sort((a, b) => a[1] - b[1]);
  for (const [sport] of due.slice(0, 2)) {
    if (!buckets.upcoming.can(oddsCost())) return;
    const n = await refreshOdds(sport, buckets.upcoming);
    if (n) console.log(`[sports] ${sport} : ${n} match(s), crédits restants : ${quota.remaining ?? "?"}`);
  }
}

async function resultsStep() {
  if (Date.now() - lastResults < SCORES_EVERY_MS) return;
  lastResults = Date.now();
  for (const sport of feedKeysAwaitingResults(MATCH_MIN_MS)) {
    if (!buckets.upcoming.can(2) && !lowOnCredits()) break;
    applyResults(await metered(buckets.upcoming, 2, () => fetchResults(KEY!, sport)));
  }
  settle();
}

async function extraStep() {
  for (const [id, { sportKey }] of extraQueue) {
    extraQueue.delete(id);
    const cost = (3 + extraMarketsFor(sportKey).length) * regions;
    if (lowOnCredits() || !buckets.extra.can(cost)) continue;
    extraInFlight.add(id);
    try {
      const selections = await metered(buckets.extra, cost, () => fetchEventOdds(KEY!, sportKey, id));
      if (selections) storeDeepMarkets(id, selections);
    } finally {
      extraInFlight.delete(id);
    }
  }
}

function every(ms: number, task: () => Promise<void> | void, label: string) {
  let running = false;
  const run = async () => {
    if (running) return;
    running = true;
    try {
      await task();
    } catch (e) {
      console.error(`[sports] ${label} échoué :`, e instanceof Error ? e.message : e);
    } finally {
      running = false;
    }
  };
  run();
  setInterval(run, ms);
}

export function startSportsSync() {
  if (KEY) {
    feedConfig.live = LIVE;
    feedConfig.engine = ENGINE;
    feedConfig.liveMaxAgeMs = Math.max(2 * (ENGINE ? ENGINE_EVERY_MS : LIVE_EVERY_MS) + 30_000, 90_000);
    if (ENGINE) {
      // Avant-match : le moteur complète la fiche de chaque vrai match avec tous ses marchés.
      feedHooks.beforeDetail = (id) => enginePrematch(id);
      every(ENGINE_TICK_MS, () => void tickEngine(), "moteur de cotes");
    }
    feedConfig.deepMaxAgeMs = EXTRA_EVERY_MS * 2;
    if (EXTRA)
      feedHooks.onEventViewed = (e) => {
        if (!e.feed_key || extraInFlight.has(e.id)) return;
        const maxAge = e.live ? LIVE_EVERY_MS : EXTRA_EVERY_MS;
        if (e.deep_at && Date.now() - e.deep_at < maxAge) return;
        extraQueue.set(e.id, { sportKey: e.feed_key, live: e.live });
      };
    every(
      5_000,
      async () => {
        await refreshSportsList();
        await liveStep();
        await engineStep();
        await extraStep();
        await upcomingStep();
        await resultsStep();
      },
      "flux réel",
    );
    console.log(
      `[sports] flux réel : ${ALL_SPORTS ? "toutes les compétitions" : sports.join(", ")} ; marchés ${["h2h", ...MARKETS.filter((m) => m !== "h2h")].join(", ")}` +
        `${EXTRA ? " + marchés supplémentaires sur la fiche match" : ""} ; direct ${LIVE ? `cotes des bookmakers (toutes les ${LIVE_EVERY_MS / 1000} s)` : ENGINE ? `moteur maison (scores toutes les ${ENGINE_EVERY_MS / 1000} s)` : "désactivé"} ; budget ${MONTHLY_CREDITS.toLocaleString("fr-FR")} crédits/mois`,
    );
  }
  if (virtualOn) {
    // Avec un flux réel, les compétitions virtuelles sont signalées comme telles.
    const label = KEY ? (l: string) => `${l} (virtuel)` : (l: string) => l;
    every(
      VIRTUAL_TICK_MS,
      () => {
        if (tickVirtual(label)) settle();
      },
      "virtuels",
    );
    console.log(`[sports] matchs virtuels en direct (un match dure ${env.DEMO_MATCH_MINUTES ?? 10} min)`);
  }
}
