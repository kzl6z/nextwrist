import { applyResults, feedKeysAwaitingResults, settleBets, upsertEvents } from "./betting";
import { demoFixtures, demoResults } from "./demo";
import { fetchOdds, fetchResults, quota } from "./oddsapi";

const KEY = process.env.ODDS_API_KEY;
const SPORTS = (process.env.ODDS_SPORTS ?? "soccer_france_ligue_one,soccer_epl,soccer_uefa_champs_league")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
/** Intervalle de mise à jour des cotes (flux réel). */
const ODDS_EVERY_MS = Number(process.env.ODDS_SYNC_MINUTES ?? 360) * 60_000;
/** Intervalle de recherche des résultats, seulement si des matchs sont en attente. */
const SCORES_EVERY_MS = Number(process.env.SCORES_SYNC_MINUTES ?? 120) * 60_000;
/** Un match n'est pas cherché dans les résultats avant cette durée après son coup d'envoi. */
const MATCH_MIN_MS = 2 * 60 * 60_000;

export const feedMode = KEY ? "the-odds-api" : "demo";

function settle() {
  const settled = settleBets();
  if (settled) console.log(`[sports] ${settled} ticket(s) réglé(s)`);
}

async function syncOdds() {
  for (const sport of SPORTS) {
    const events = await fetchOdds(KEY!, sport);
    upsertEvents(events);
    console.log(`[sports] ${sport} : ${events.length} match(s), crédits restants : ${quota.remaining ?? "?"}`);
  }
}

async function syncScores() {
  for (const sport of feedKeysAwaitingResults(MATCH_MIN_MS)) applyResults(await fetchResults(KEY!, sport));
  settle();
}

function every(ms: number, task: () => Promise<void> | void, label: string) {
  const run = async () => {
    try {
      await task();
    } catch (e) {
      console.error(`[sports] ${label} échoué :`, e instanceof Error ? e.message : e);
    }
  };
  run();
  setInterval(run, ms);
}

export function startSportsSync() {
  if (KEY) {
    every(ODDS_EVERY_MS, syncOdds, "cotes");
    every(SCORES_EVERY_MS, syncScores, "résultats");
    console.log(
      `[sports] flux réel (${SPORTS.join(", ")}), cotes toutes les ${ODDS_EVERY_MS / 60_000} min, résultats toutes les ${SCORES_EVERY_MS / 60_000} min`,
    );
  } else {
    every(
      20_000,
      () => {
        upsertEvents(demoFixtures());
        applyResults(demoResults());
        settle();
      },
      "démo",
    );
    console.log("[sports] flux démo (aucune ODDS_API_KEY)");
  }
}
