// Football du monde (API-Football, clé gratuite) : lecture des réponses, classement maison,
// calendrier, direct avec la minute, budget de requêtes. Le réseau est simulé.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "pilotcasino-world-"));
process.env.DB_PATH = join(dir, "world.sqlite");
let af: typeof import("../src/sports/apifootball");
let rt: typeof import("../src/sports/ratings");
let wf: typeof import("../src/sports/worldfeed");
let b: typeof import("../src/sports/betting");
let en: typeof import("../src/sports/engine");
let db: typeof import("../src/db").db;
let userId = 0;

const DAY = 86_400_000;
const cfg = { daily: 100, minGames: 4, bootstrapDays: 2 };

/** Un match au format de l'API (champs documentés de /fixtures). */
function fx(o: {
  id: number;
  at: number;
  status?: string;
  elapsed?: number | null;
  league?: number;
  round?: string;
  home: [number, string];
  away: [number, string];
  goals?: [number | null, number | null];
  ft?: [number | null, number | null];
  events?: unknown[];
}) {
  return {
    fixture: { id: o.id, date: new Date(o.at).toISOString(), timestamp: Math.floor(o.at / 1000), status: { long: "", short: o.status ?? "NS", elapsed: o.elapsed ?? null, extra: null } },
    league: { id: o.league ?? 61, name: "Ligue 1", country: "France", season: 2026, round: o.round ?? "Regular Season - 10" },
    teams: { home: { id: o.home[0], name: o.home[1] }, away: { id: o.away[0], name: o.away[1] } },
    goals: { home: o.goals?.[0] ?? null, away: o.goals?.[1] ?? null },
    score: { halftime: { home: null, away: null }, fulltime: { home: o.ft?.[0] ?? null, away: o.ft?.[1] ?? null }, extratime: { home: null, away: null }, penalty: { home: null, away: null } },
    ...(o.events ? { events: o.events } : {}),
  };
}
const body = (response: unknown[]) => ({ get: "fixtures", parameters: {}, errors: [], results: response.length, paging: { current: 1, total: 1 }, response });

const TEAMS: [number, string][] = [
  [1, "Paris Saint Germain"],
  [2, "Marseille"],
  [3, "Lyon"],
  [4, "Monaco"],
  [5, "Lille"],
  [6, "Lens"],
];
/** Cinq journées de championnat : le PSG gagne largement, Lens perd tout. */
function season(start: number) {
  const out: ReturnType<typeof fx>[] = [];
  let id = 1000;
  for (let day = 0; day < 5; day++)
    for (let i = 0; i < 3; i++) {
      const h = TEAMS[(i + day) % 6]!;
      const a = TEAMS[(5 - i + day) % 6]!;
      const strength = (t: number) => 7 - t;
      const gh = Math.max(0, Math.round((strength(h[0]) - strength(a[0])) / 2) + 1);
      const ga = Math.max(0, Math.round((strength(a[0]) - strength(h[0])) / 2));
      out.push(fx({ id: id++, at: start + day * DAY, status: "FT", home: h, away: a, goals: [gh, ga], ft: [gh, ga] }));
    }
  return out;
}

beforeAll(async () => {
  af = await import("../src/sports/apifootball");
  rt = await import("../src/sports/ratings");
  wf = await import("../src/sports/worldfeed");
  b = await import("../src/sports/betting");
  en = await import("../src/sports/engine");
  db = (await import("../src/db")).db;
  const { register } = await import("../src/auth");
  await register("monde", "password123");
  userId = (db.query("SELECT id FROM users WHERE username = 'monde'").get() as { id: number }).id;
  b.feedConfig.engine = true;
});
afterAll(() => rmSync(dir, { recursive: true, force: true }));

describe("lecture des réponses API-Football", () => {
  test("matchs, minute, score réglementaire et cartons rouges", () => {
    const [f] = af.parseFixtures(
      body([
        fx({
          id: 7,
          at: Date.UTC(2026, 9, 17, 19),
          status: "2H",
          elapsed: 67,
          home: [1, "Paris Saint Germain"],
          away: [2, "Marseille"],
          goals: [2, 1],
          events: [{ type: "Card", detail: "Red Card", team: { id: 2 } }, { type: "Card", detail: "Yellow Card", team: { id: 1 } }],
        }),
      ]),
    );
    expect(f).toMatchObject({ id: 7, status: "2H", elapsed: 67, goals: [2, 1], red: [0, 1], leagueId: 61, round: "Regular Season - 10" });
    expect(f!.startsAt).toBe(Date.UTC(2026, 9, 17, 19));
  });
  test("erreurs renvoyées dans le corps (offre, quota, clé)", () => {
    expect(af.bodyError({ errors: [] })).toBeNull();
    expect(af.bodyError({ errors: { plan: "Free plans do not have access to this season." } })).toContain("plan");
  });
  test("rapprochement des noms d'équipes entre fournisseurs", () => {
    expect(af.nameSimilarity("Olympique de Marseille", "Marseille")).toBe(1);
    expect(af.nameSimilarity("Paris Saint-Germain", "Paris Saint Germain")).toBe(1);
    expect(af.nameSimilarity("Manchester United", "Manchester City")).toBe(0.5);
    expect(af.nameSimilarity("Lyon", "Lens")).toBe(0);
  });
});

describe("notre classement des équipes", () => {
  test("manches de championnat seulement", () => {
    expect(rt.isLeagueRound("Regular Season - 12")).toBe(true);
    expect(rt.isLeagueRound("Apertura - 3")).toBe(true);
    expect(rt.isLeagueRound("Round of 16")).toBe(false);
    expect(rt.isLeagueRound("Final")).toBe(false);
    expect(rt.isLeagueRound(null)).toBe(false);
  });
  test("une équipe qui gagne largement devient favorite", () => {
    const fresh = { attack: 0, defense: 0, games: 0, league: null };
    let [s, w] = [fresh, fresh];
    for (let i = 0; i < 8; i++) [s, w] = rt.update(s, w, 3, 0);
    const [lh, la] = rt.expectedGoals(s, w);
    expect(lh).toBeGreaterThan(2);
    expect(la).toBeLessThan(0.8);
  });
});

describe("calendrier, cotes maison, direct", () => {
  test("les résultats amorcent le classement ; les matchs à venir sont cotés, pas les coupes", () => {
    const now = Date.now();
    const res = wf.applyCalendar(af.parseFixtures(body(season(now - 10 * DAY))), cfg, now);
    expect(res.learned).toBe(15);
    expect(rt.getRating("af:1")!.games).toBe(5);
    const upcoming = af.parseFixtures(
      body([
        fx({ id: 2001, at: now + 3 * 3_600_000, home: [1, "Paris Saint Germain"], away: [6, "Lens"] }),
        fx({ id: 2002, at: now + 3 * 3_600_000, home: [3, "Lyon"], away: [4, "Monaco"], round: "Round of 32", league: 66 }),
      ]),
    );
    expect(wf.applyCalendar(upcoming, cfg, now).listed).toBe(1);
    const d = b.eventDetail("af-2001");
    expect(d.league).toBe("Ligue 1 - France");
    expect(d.open).toBe(true);
    expect(d.selections.home!).toBeLessThan(1.5);
    expect(d.selections["cs:2-0"]).toBeGreaterThan(1);
    expect(() => b.eventDetail("af-2002")).toThrow();
  });

  test("match déjà couvert par les bookmakers : lié, pas de doublon, cotes des bookmakers conservées", () => {
    const now = Date.now();
    b.upsertEvents([
      {
        id: "odds-1",
        sport: "football",
        league: "Ligue 1 - France",
        home: "Lille OSC",
        away: "Olympique Lyonnais",
        startsAt: now + 5 * 3_600_000,
        feedKey: "soccer_france_ligue_one",
        selections: { home: { price: 2.1, prob: 0.45 }, draw: { price: 3.4, prob: 0.28 }, away: { price: 3.5, prob: 0.27 } },
      },
    ]);
    wf.applyCalendar(af.parseFixtures(body([fx({ id: 2003, at: now + 5 * 3_600_000 + 5 * 60_000, home: [5, "Lille"], away: [3, "Lyon"] })])), cfg, now);
    expect(db.query("SELECT event_id FROM ext_links WHERE ext_id = '2003'").get()).toEqual({ event_id: "odds-1" });
    expect(db.query("SELECT 1 FROM events WHERE id = 'af-2003'").get()).toBeNull();
    expect(b.eventDetail("odds-1").selections.home).toBe(2.1);
  });

  test("direct : minute exacte, pari, prolongation réglée sur le temps réglementaire", () => {
    const now = Date.now();
    db.query("UPDATE events SET starts_at = ? WHERE id = 'af-2001'").run(now - 70 * 60_000);
    const live = af.parseFixtures(
      body([fx({ id: 2001, at: now - 70 * 60_000, status: "2H", elapsed: 55, home: [1, "Paris Saint Germain"], away: [6, "Lens"], goals: [1, 1] })]),
    );
    const { states, seen } = wf.liveStates(live, 25 * 60_000);
    expect(seen).toEqual([2001]);
    en.applyLiveStates(states, now);
    en.tickEngine(now);
    let d = b.eventDetail("af-2001");
    expect(d.clock).toBe("55'");
    expect(d.score).toEqual([1, 1]);
    expect(d.open).toBe(true);
    // Buts déjà marqués avant la première mise à jour : pas de suspension, pas de minute inventée.
    expect(d.suspended).toBe(false);
    expect(d.detail?.timeline ?? []).toEqual([]);
    const bet = b.placeBet(userId, [{ eventId: "af-2001", key: "home", price: d.selections.home }], 100, false);

    // Prolongation : le résultat du temps réglementaire règle les paris.
    const et = af.parseFixtures(
      body([fx({ id: 2001, at: now - 70 * 60_000, status: "ET", elapsed: 95, home: [1, "Paris Saint Germain"], away: [6, "Lens"], goals: [2, 1], ft: [1, 1] })]),
    );
    en.applyLiveStates(wf.liveStates(et, 25 * 60_000).states, now + 1000);
    b.settleBets();
    d = b.eventDetail("af-2001");
    expect(d.status).toBe("finished");
    expect(d.score).toEqual([1, 1]);
    expect(b.myBets(userId).bets.find((x) => x.id === bet.betId)!.status).toBe("lost");
  });

  test("le quota du direct est réparti sur les heures de jeu restantes", () => {
    const noon = Date.UTC(2026, 9, 17, 12);
    // Matchs de 13 h à 21 h : environ 9 h de jeu pour 72 requêtes → une toutes les 7 min 30 environ.
    const kicks = Array.from({ length: 9 }, (_, i) => noon + (i + 1) * 3_600_000);
    const every = wf.liveInterval(80, kicks, noon);
    expect(every).toBeGreaterThan(6 * 60_000);
    expect(every).toBeLessThan(9 * 60_000);
    expect(wf.liveInterval(10, kicks, noon)).toBe(30 * 60_000);
    expect(wf.liveInterval(5000, kicks, noon)).toBe(3 * 60_000);
  });

  test("planificateur : amorçage, calendrier, puis direct pendant les matchs", async () => {
    const now = Date.now();
    const calls: string[] = [];
    const fakeFetch = (async (url: string) => {
      const q = String(url).split("?")[1]!;
      calls.push(q);
      const kickoff = now - 30 * 60_000;
      const response = q.startsWith("live")
        ? [fx({ id: 3001, at: kickoff, status: "1H", elapsed: 31, home: [2, "Marseille"], away: [4, "Monaco"], goals: [0, 0] })]
        : q.includes(new Date(now).toISOString().slice(0, 10))
          ? [fx({ id: 3001, at: kickoff, status: "1H", elapsed: 31, home: [2, "Marseille"], away: [4, "Monaco"], goals: [0, 0] })]
          : [];
      return new Response(JSON.stringify(body(response)), { headers: { "x-ratelimit-requests-remaining": String(100 - calls.length) } });
    }) as unknown as typeof fetch;
    // Le match du jour est déjà en ligne (coté avant le coup d'envoi).
    wf.applyCalendar(af.parseFixtures(body([fx({ id: 3001, at: now + 60_000 * 5, home: [2, "Marseille"], away: [4, "Monaco"] })])), cfg, now);
    db.query("UPDATE events SET starts_at = ? WHERE id = 'af-3001'").run(now - 30 * 60_000);
    const logs: string[] = [];
    const world = wf.startWorldFeed("cle-gratuite", cfg, (m) => logs.push(m), fakeFetch);
    for (let i = 0; i < 6; i++) await world.step();
    expect(calls.filter((q) => q.startsWith("date=")).length).toBeGreaterThanOrEqual(3);
    expect(calls).toContain("live=all");
    expect(logs.some((l) => l.includes("classement"))).toBe(true);
    en.tickEngine();
    expect(b.eventDetail("af-3001").clock).toBe("31'");
  });

  test("offre refusée par le fournisseur : message clair et pause", async () => {
    const logs: string[] = [];
    const refuse = (async () =>
      new Response(JSON.stringify({ errors: { plan: "Free plans do not have access to this season" }, response: [] }))) as unknown as typeof fetch;
    db.query("DELETE FROM kv").run();
    const world = wf.startWorldFeed("cle", cfg, (m) => logs.push(m), refuse);
    await world.step();
    await world.step();
    expect(logs).toEqual([expect.stringContaining("Free plans do not have access")]);
  });
});
