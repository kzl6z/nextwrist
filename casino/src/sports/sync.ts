import { applyResults, settleBets, upsertEvents } from "./betting";
import { demoFixtures, demoResults } from "./demo";
import { fetchOdds, fetchResults } from "./oddsapi";

const KEY = process.env.ODDS_API_KEY;
const SPORTS = (process.env.ODDS_SPORTS ?? "soccer_france_ligue_one,soccer_epl,basketball_nba")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

export const feedMode = KEY ? "the-odds-api" : "demo";

async function sync() {
  if (KEY) {
    upsertEvents(await fetchOdds(KEY, SPORTS));
    applyResults(await fetchResults(KEY, SPORTS));
  } else {
    upsertEvents(demoFixtures());
    applyResults(demoResults());
  }
  const settled = settleBets();
  if (settled) console.log(`[sports] ${settled} ticket(s) réglé(s)`);
}

export function startSportsSync() {
  const everyMs = (KEY ? 15 * 60 : 20) * 1000;
  const run = () => sync().catch((e) => console.error("[sports] synchro échouée :", e));
  run();
  setInterval(run, everyMs);
  console.log(`[sports] flux : ${feedMode}, synchro toutes les ${everyMs / 1000}s`);
}
