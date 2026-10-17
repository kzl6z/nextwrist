// Moteur de cotes maison : calage sur l'avant-match, horloge estimée, direct piloté par le score.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "pilotcasino-engine-"));
process.env.DB_PATH = join(dir, "engine.sqlite");
let b: typeof import("../src/sports/betting");
let en: typeof import("../src/sports/engine");
let MODELS: typeof import("../src/sports/models").MODELS;
let db: typeof import("../src/db").db;
let userId = 0;

beforeAll(async () => {
  b = await import("../src/sports/betting");
  en = await import("../src/sports/engine");
  MODELS = (await import("../src/sports/models")).MODELS;
  db = (await import("../src/db")).db;
  const { register } = await import("../src/auth");
  await register("moteur", "password123");
  userId = (db.query("SELECT id FROM users WHERE username = 'moteur'").get() as { id: number }).id;
  b.feedConfig.engine = true;
  b.feedConfig.live = false;
  b.feedConfig.liveMaxAgeMs = 150_000;
});
afterAll(() => rmSync(dir, { recursive: true, force: true }));

const sel = (probs: Record<string, number>) =>
  Object.fromEntries(Object.entries(probs).map(([k, p]) => [k, { price: Math.round((0.95 / p) * 100) / 100, prob: p }]));

describe("calage sur les cotes d'avant-match", () => {
  test("football : 1N2 et total reproduits", () => {
    const target = new Map([
      ["home", 0.52],
      ["draw", 0.26],
      ["away", 0.22],
      ["ou:2.5:over", 0.56],
      ["ou:2.5:under", 0.44],
    ]);
    const sim = en.calibrate("football", target)!;
    const p = MODELS.football.probs(sim);
    expect(p.get("home")! / (p.get("home")! + p.get("away")!)).toBeCloseTo(0.52 / 0.74, 3);
    expect(p.get("ou:2.5:over")!).toBeCloseTo(0.56, 3);
    expect(p.get("draw")!).toBeGreaterThan(0.2);
    expect(p.get("draw")!).toBeLessThan(0.32);
  });

  test("basket : favori et total des bookmakers, ligne reprise telle quelle", () => {
    const sim = en.calibrate("basketball", new Map([["home", 0.7], ["away", 0.3], ["ou:228.5:over", 0.5], ["ou:228.5:under", 0.5]]))!;
    const p = MODELS.basketball.probs(sim);
    expect(p.get("home")!).toBeCloseTo(0.7, 2);
    expect(p.get("ou:228.5:over")!).toBeCloseTo(0.5, 2);
    expect(sim.lines.ou).toContain(228.5);
    // Les autres lignes suivent le nouveau total.
    expect(Math.min(...sim.lines.ou!)).toBeGreaterThan(210);
  });

  test("hockey sans nul sur le marché réel : vainqueur prolongation comprise", () => {
    const sim = en.calibrate("hockey", new Map([["home", 0.6], ["away", 0.4]]))!;
    const probs = en.engineProbs({ ...sim, twoWay: true, fitAt: 0, own: [] });
    expect(probs.has("draw")).toBe(false);
    expect([...probs.keys()].some((k) => k.startsWith("dc:"))).toBe(false);
    expect(probs.get("home")! + probs.get("away")!).toBeCloseTo(1, 6);
    expect(probs.get("home")!).toBeCloseTo(0.6, 2);
  });

  test("seuls les pronostics réglables avec le score final sont proposés", () => {
    const sim = en.calibrate("football", new Map([["home", 0.4], ["draw", 0.3], ["away", 0.3]]))!;
    const keys = [...en.engineProbs({ ...sim, twoWay: false, fitAt: 0, own: [] }).keys()];
    expect(keys.some((k) => k.startsWith("ht:"))).toBe(false);
    expect(keys).toContain("cs:1-1");
    expect(keys).toContain("btts:yes");
  });
});

describe("horloge estimée", () => {
  test("football : mi-temps, deuxième période, temps additionnel", () => {
    expect(en.estimateProgress("football", null, 20).progress).toBeCloseTo(20 / 94, 5);
    expect(en.estimateProgress("football", null, 55)).toEqual({ progress: 0.5, pause: "Mi-temps" });
    expect(en.estimateProgress("football", null, 70).progress).toBeCloseTo((1 + 8 / 47) / 2, 5);
    expect(en.estimateProgress("football", null, 200).progress).toBe(1);
  });
  test("hockey : pauses entre les périodes ; NBA : quatre quart-temps", () => {
    expect(en.estimateProgress("hockey", null, 45).pause).toBe("Pause");
    expect(en.estimateProgress("basketball", "basketball_nba", 72).pause).toBe("Mi-temps");
    expect(en.estimateProgress("basketball", "basketball_nba", 32).pause).toBe("Pause");
  });
});

describe("direct piloté par le score", () => {
  const event = (id: string, startsAt: number) => ({
    id,
    sport: "football",
    league: "Premier League - England",
    home: "Arsenal",
    away: "Chelsea",
    startsAt,
    feedKey: "soccer_epl",
    selections: sel({ home: 0.5, draw: 0.27, away: 0.23, "ou:2.5:over": 0.55, "ou:2.5:under": 0.45 }),
  });

  test("avant-match : la fiche est complétée par le moteur sans toucher aux cotes des bookmakers", () => {
    b.upsertEvents([event("e1", Date.now() + 3_600_000)]);
    b.feedHooks.beforeDetail = (id) => en.enginePrematch(id);
    const d = b.eventDetail("e1");
    expect(d.selections.home).toBe(1.9);
    expect(d.selections["cs:2-1"]).toBeGreaterThan(5);
    expect(d.selections["btts:yes"]).toBeGreaterThan(1);
    expect(Object.values(d.selections).filter(Boolean).length).toBeGreaterThan(40);
  });

  test("but, suspension, nouvelles cotes, cash out et règlement", () => {
    const t0 = Date.now() - 30 * 60_000;
    b.upsertEvents([event("e2", Date.now() + 3_600_000)]);
    db.query("UPDATE events SET starts_at = ? WHERE id = 'e2'").run(t0);
    // Coup d'envoi : le moteur prend la main, horloge estimée.
    en.applyLiveStates([{ id: "e2", homeScore: 0, awayScore: 0, completed: false }]);
    en.tickEngine();
    let d = b.eventDetail("e2");
    expect(d.live).toBe(true);
    expect(d.engine).toBe(true);
    expect(d.open).toBe(true);
    expect(d.clock).toBe("≈ 29'");
    const homeBefore = d.selections.home!;
    const bet = b.placeBet(userId, [{ eventId: "e2", key: "home", price: homeBefore }], 100, false);

    // Arsenal marque : marchés suspendus, cote en baisse, but inscrit dans le fil du match.
    en.applyLiveStates([{ id: "e2", homeScore: 1, awayScore: 0, completed: false }]);
    en.tickEngine();
    d = b.eventDetail("e2");
    expect(d.suspended).toBe(true);
    expect(d.score).toEqual([1, 0]);
    expect(d.selections.home!).toBeLessThan(homeBefore);
    expect(d.selections["cs:0-0"]).toBeNull();
    expect(d.detail?.timeline?.at(-1)).toMatchObject({ side: "home", kind: "goal" });
    expect(() => b.placeBet(userId, [{ eventId: "e2", key: "away", price: d.selections.away }], 10, true)).toThrow();

    // Après la suspension, le cash out reflète le but.
    db.query("UPDATE events SET suspended_until = NULL WHERE id = 'e2'").run();
    const mine = b.myBets(userId).bets.find((x) => x.id === bet.betId)!;
    expect(mine.cashout).toBeGreaterThan(100);

    // Carton rouge transmis par la source : l'équipe réduite à dix voit sa cote monter.
    const homeNow = b.eventDetail("e2").selections.home!;
    en.applyLiveStates([{ id: "e2", homeScore: 1, awayScore: 0, completed: false, red: [1, 0] }]);
    en.tickEngine();
    expect(b.eventDetail("e2").selections.home!).toBeGreaterThan(homeNow);

    // Source muette : les paris se ferment.
    db.query("UPDATE events SET odds_at = ? WHERE id = 'e2'").run(Date.now() - 10 * 60_000);
    expect(b.eventDetail("e2").open).toBe(false);

    // Fin du match.
    en.applyLiveStates([{ id: "e2", homeScore: 2, awayScore: 0, completed: true }]);
    expect(b.settleBets()).toBeGreaterThan(0);
    const settled = b.myBets(userId).bets.find((x) => x.id === bet.betId)!;
    expect(settled.status).toBe("won");
  });

  test("sport que le moteur ne sait pas coter en direct : reste fermé", () => {
    b.upsertEvents([{ ...event("e3", Date.now() + 3_600_000), sport: "tennis", feedKey: "tennis_atp_paris" }]);
    db.query("UPDATE events SET starts_at = ? WHERE id = 'e3'").run(Date.now() - 10 * 60_000);
    en.applyLiveStates([{ id: "e3", homeScore: 1, awayScore: 0, completed: false }]);
    en.tickEngine();
    expect(b.eventDetail("e3").open).toBe(false);
  });
});
