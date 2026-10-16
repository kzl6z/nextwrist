// Flux réel côté base : direct, fraîcheur des cotes, marchés supplémentaires, règlement.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "pilotcasino-feed-"));
process.env.DB_PATH = join(dir, "feed.sqlite");
let b: typeof import("../src/sports/betting");
let db: typeof import("../src/db").db;
let userId = 0;

const ev = (id: string, startsInMs: number, extra: Record<string, { price: number; prob: number }> = {}) => ({
  id,
  sport: "football",
  league: "Ligue 1 - France",
  home: "Paris Saint Germain",
  away: "Marseille",
  startsAt: Date.now() + startsInMs,
  feedKey: "soccer_france_ligue_one",
  selections: {
    home: { price: 1.6, prob: 0.6 },
    draw: { price: 4, prob: 0.24 },
    away: { price: 5.5, prob: 0.16 },
    ...extra,
  },
});

beforeAll(async () => {
  b = await import("../src/sports/betting");
  db = (await import("../src/db")).db;
  const { register } = await import("../src/auth");
  await register("parieur", "password123");
  userId = (db.query("SELECT id FROM users WHERE username = 'parieur'").get() as { id: number }).id;
});
afterAll(() => rmSync(dir, { recursive: true, force: true }));

describe("flux réel", () => {
  test("match à venir : pariable, marchés supplémentaires conservés à la mise à jour suivante", () => {
    b.upsertEvents([ev("r1", 3_600_000)]);
    b.storeDeepMarkets("r1", { "btts:yes": { price: 1.8, prob: 0.53 }, "btts:no": { price: 1.95, prob: 0.47 } });
    b.upsertEvents([ev("r1", 3_600_000)]);
    const d = b.eventDetail("r1");
    expect(d.open).toBe(true);
    expect(d.selections["btts:yes"]).toBe(1.8);
    const bet = b.placeBet(userId, [{ eventId: "r1", key: "btts:yes", price: 1.8 }], 10, false);
    expect(bet.potentialWin).toBe(18);
  });

  test("sans direct : un match commencé n'est plus pariable", () => {
    b.feedConfig.live = false;
    b.upsertEvents([ev("r2", 3_600_000)]);
    db.query("UPDATE events SET starts_at = ? WHERE id = 'r2'").run(Date.now() - 60_000);
    b.upsertEvents([ev("r2", -60_000)]);
    expect(b.eventDetail("r2").open).toBe(false);
    expect(() => b.placeBet(userId, [{ eventId: "r2", key: "home", price: 1.6 }], 10, true)).toThrow();
  });

  test("avec direct : pariable tant que les cotes sont fraîches, puis fermé", () => {
    b.feedConfig.live = true;
    b.feedConfig.liveMaxAgeMs = 90_000;
    b.upsertEvents([ev("r3", -10 * 60_000)]);
    const live = b.eventDetail("r3");
    expect(live.status).toBe("live");
    expect(live.open).toBe(true);
    const bet = b.placeBet(userId, [{ eventId: "r3", key: "home", price: 1.6 }], 10, false);
    expect(b.myBets(userId).bets.find((x) => x.id === bet.betId)!.cashout).toBeGreaterThan(0);
    db.query("UPDATE events SET odds_at = ? WHERE id = 'r3'").run(Date.now() - 5 * 60_000);
    expect(b.eventDetail("r3").open).toBe(false);
    expect(b.myBets(userId).bets.find((x) => x.id === bet.betId)!.cashout).toBeNull();
  });

  test("scores en direct puis résultat final : les paris sont réglés", () => {
    b.applyScores([{ id: "r3", homeScore: 1, awayScore: 0, completed: false }]);
    expect(b.eventDetail("r3").score).toEqual([1, 0]);
    b.applyScores([{ id: "r3", homeScore: 2, awayScore: 1, completed: true }]);
    expect(b.eventDetail("r3").status).toBe("finished");
    b.settleBets();
    const won = b.myBets(userId).bets.filter((x) => x.status === "won");
    expect(won.length).toBe(1);
  });

  test("listes filtrées et compteurs par sport", () => {
    expect(b.listEvents("football", null).length).toBeGreaterThan(0);
    expect(b.listEvents("tennis", null).length).toBe(0);
    expect(b.eventCounts().some((c) => c.sport === "football")).toBe(true);
  });
});
