// Tests de bout en bout : un vrai serveur sur une base temporaire.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "pilotcasino-"));
const DB = join(dir, "test.sqlite");
const PORT = 3900 + Math.floor(Math.random() * 90);
const BASE = `http://localhost:${PORT}/api`;
let server: ReturnType<typeof Bun.spawn>;

class Client {
  cookie = "";
  async call(path: string, body?: unknown) {
    const res = await fetch(`${BASE}/${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? { cookie: this.cookie } : { "Content-Type": "application/json", cookie: this.cookie },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const set = res.headers.get("set-cookie");
    if (set) this.cookie = set.split(";")[0]!;
    return { status: res.status, data: (await res.json()) as any };
  }
}

async function newPlayer() {
  const c = new Client();
  const r = await c.call("register", { username: `t${Math.floor(Math.random() * 1e9)}`, password: "password123" });
  expect(r.status).toBe(200);
  return c;
}

/** Le solde doit toujours être égal à la somme du grand livre. */
function ledgerMatches() {
  const db = new Database(DB, { readonly: true });
  const rows = db
    .query(
      `SELECT u.balance, COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.user_id = u.id), 0) AS ledger FROM users u`,
    )
    .all() as { balance: number; ledger: number }[];
  db.close();
  return rows.every((r) => r.balance === r.ledger && r.balance >= 0);
}

beforeAll(async () => {
  server = Bun.spawn(["bun", "src/server.ts"], {
    cwd: join(import.meta.dir, ".."),
    env: { ...process.env, DB_PATH: DB, PORT: String(PORT), DEMO_MATCH_MINUTES: "0.2", ODDS_API_KEY: "" },
    stdout: "ignore",
    stderr: "inherit",
  });
  for (let i = 0; i < 50; i++) {
    try {
      await fetch(`${BASE}/me`);
      break;
    } catch {
      await Bun.sleep(100);
    }
  }
  await Bun.sleep(3500); // premier pas du moteur des matchs virtuels
});

afterAll(() => {
  server?.kill();
  rmSync(dir, { recursive: true, force: true });
});

describe("paris sportifs", () => {
  test("calendrier : six sports, des matchs en direct, des dizaines de marchés", async () => {
    const c = await newPlayer();
    const { data } = await c.call("sports/events");
    const sports = new Set([...data.events, ...data.live].map((e: any) => e.sport));
    expect([...sports].sort()).toEqual(["basketball", "football", "hockey", "mma", "rugby", "tennis"]);
    expect(data.live.length).toBeGreaterThan(0);
    const foot = data.events.find((e: any) => e.sport === "football");
    expect(foot.markets).toBeGreaterThan(40);
    const detail = (await c.call(`sports/event/${foot.id}`)).data;
    expect(Object.keys(detail.selections)).toContain("btts:yes");
  });

  test("pari en direct, variation de cote, cash out", async () => {
    const c = await newPlayer();
    const { data } = await c.call("sports/events");
    const ev = data.live.find((e: any) => e.open && !e.suspended && e.odds.home);
    const wrong = await c.call("sports/bets", { legs: [{ eventId: ev.id, key: "home", price: 999 }], stake: 100 });
    expect(wrong.status).toBe(409);
    const ok = await c.call("sports/bets", { legs: [{ eventId: ev.id, key: "home", price: 999 }], stake: 100, acceptChanges: true });
    expect(ok.status).toBe(200);
    expect(ok.data.balance).toBe(900);
    const bets = (await c.call("sports/bets")).data.bets;
    const quote = bets[0].cashout;
    if (quote) {
      const tooHigh = await c.call("sports/cashout", { betId: bets[0].id, value: quote * 10 });
      expect(tooHigh.status).toBe(409);
      const done = await c.call("sports/cashout", { betId: bets[0].id, value: 1 });
      expect(done.status).toBe(200);
      expect(done.data.balance).toBe(900 + done.data.value);
      const again = await c.call("sports/cashout", { betId: bets[0].id, value: 1 });
      expect(again.status).toBe(400);
    }
    expect(ledgerMatches()).toBe(true);
  });

  test("règles du ticket", async () => {
    const c = await newPlayer();
    const { data } = await c.call("sports/events");
    const [a, b] = data.events;
    const leg = (e: any, key = "home") => ({ eventId: e.id, key, price: e.odds[key] });
    expect((await c.call("sports/bets", { legs: [leg(a), leg(a, "away")], stake: 10 })).status).toBe(400);
    expect((await c.call("sports/bets", { legs: [leg(a)], stake: 5000 })).status).toBe(400);
    expect((await c.call("sports/bets", { legs: [{ eventId: a.id, key: "nope", price: 2 }], stake: 10 })).status).toBe(404);
    expect((await c.call("sports/bets", { legs: [], stake: 10 })).status).toBe(400);
    const combo = await c.call("sports/bets", { legs: [leg(a), leg(b)], stake: 10 });
    expect(combo.status).toBe(200);
    expect(combo.data.totalOdds).toBeCloseTo(a.odds.home * b.odds.home, 1);
  });

  test("les paris sont réglés automatiquement en fin de match", async () => {
    const c = await newPlayer();
    const { data } = await c.call("sports/events");
    let placed = 0;
    for (const e of data.live.filter((x: any) => x.open)) {
      const d = (await c.call(`sports/event/${e.id}`)).data;
      for (const [key, price] of Object.entries(d.selections).filter(([, p]) => p !== null).slice(0, 4)) {
        const r = await c.call("sports/bets", { legs: [{ eventId: e.id, key, price }], stake: 5, acceptChanges: true });
        if (r.status === 200) placed++;
      }
    }
    expect(placed).toBeGreaterThan(3);
    // Un match virtuel dure 12 s dans ce test.
    let open = placed;
    for (let i = 0; i < 40 && open > 0; i++) {
      await Bun.sleep(1000);
      open = (await c.call("sports/bets")).data.bets.filter((b: any) => b.status === "open").length;
    }
    expect(open).toBe(0);
    const bets = (await c.call("sports/bets")).data.bets;
    for (const b of bets) {
      if (b.status === "won") expect(b.payout).toBe(Math.floor((b.stake * Math.round(b.total_odds * 100)) / 100));
      if (b.status === "lost") expect(b.payout).toBe(0);
    }
    expect(ledgerMatches()).toBe(true);
  }, 60_000);
});

describe("jeux de casino", () => {
  test("chaque jeu à tirage unique accepte une mise valide et refuse les invalides", async () => {
    const c = await newPlayer();
    const calls: [string, object][] = [
      ["dice", { bet: 10, target: 50, over: true }],
      ["limbo", { bet: 10, target: 2 }],
      ["plinko", { bet: 10, rows: 16, risk: "high" }],
      ["wheel", { bet: 10, risk: "low" }],
      ["keno", { bet: 10, picks: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] }],
      ["baccarat", { bets: { banker: 10, tie: 5 } }],
      ["slots/spin", { bet: 10 }],
      ["roulette/spin", { bets: [{ type: "red", amount: 10 }] }],
    ];
    for (const [path, body] of calls) {
      const r = await c.call(path, body);
      expect([path, r.status]).toEqual([path, 200]);
      expect(typeof r.data.balance).toBe("number");
    }
    const bad: [string, object][] = [
      ["dice", { bet: 10, target: 99 }],
      ["limbo", { bet: 10, target: 1 }],
      ["plinko", { bet: 10, rows: 9, risk: "high" }],
      ["wheel", { bet: 10, risk: "extreme" }],
      ["keno", { bet: 10, picks: [1, 1] }],
      ["keno", { bet: 10, picks: [0] }],
      ["baccarat", { bets: {} }],
      ["dice", { bet: 0, target: 50 }],
      ["dice", { bet: 999_999, target: 50 }],
    ];
    for (const [path, body] of bad) expect([path, (await c.call(path, body)).status]).toEqual([path, 400]);
    expect(ledgerMatches()).toBe(true);
  });

  test("jeux en plusieurs étapes : une partie à la fois, encaissement contrôlé", async () => {
    const c = await newPlayer();
    // Mines
    expect((await c.call("mines/start", { bet: 10, mines: 3 })).status).toBe(200);
    expect((await c.call("mines/start", { bet: 10, mines: 3 })).status).toBe(409);
    expect((await c.call("mines/cashout", {})).status).toBe(400);
    const reveal = await c.call("mines/reveal", { cell: 0 });
    expect(reveal.data.game.bombs === undefined).toBe(reveal.data.game.status === "playing");
    if (reveal.data.game.status === "playing") expect((await c.call("mines/cashout", {})).data.game.payout).toBe(11);
    // Hi-Lo
    const h = await c.call("hilo/start", { bet: 10 });
    expect((await c.call("hilo/cashout", {})).status).toBe(400);
    expect((await c.call("hilo/guess", { dir: "skip" })).data.game.status).toBe("playing");
    const dir = h.data.game.odds.hi.chance >= 0.5 ? "hi" : "lo";
    const g = await c.call("hilo/guess", { dir });
    if (g.data.game.status === "playing") expect((await c.call("hilo/cashout", {})).data.game.status).toBe("won");
    // Tower
    await c.call("tower/start", { bet: 10, difficulty: "easy" });
    expect((await c.call("tower/pick", { col: 9 })).status).toBe(400);
    const t = await c.call("tower/pick", { col: 0 });
    expect(t.data.game.traps === undefined).toBe(t.data.game.status === "playing");
    // Pile ou face
    const cf = await c.call("coinflip/start", { bet: 10, side: "heads" });
    expect(["playing", "lost"]).toContain(cf.data.game.status);
    // Video poker
    const vp = await c.call("videopoker/deal", { bet: 10 });
    expect(vp.data.game.hand).toHaveLength(5);
    const drawn = await c.call("videopoker/draw", { holds: [true, true, true, true, true] });
    expect(drawn.data.game.hand).toEqual(vp.data.game.hand);
    // Blackjack et crash
    expect((await c.call("blackjack/start", { bet: 10 })).status).toBe(200);
    expect((await c.call("crash/start", { bet: 10, autoCashout: 1.5 })).status).toBe(200);
    expect(ledgerMatches()).toBe(true);
    const feed = await c.call("casino/history/videopoker");
    expect(feed.data).toHaveLength(1);
  });
});
