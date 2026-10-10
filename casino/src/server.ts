import { join, normalize } from "node:path";
import { login, logout, register, sessionCookie, userFrom, type User } from "./auth";
import "./db";
import {
  doubleBlackjack,
  getBlackjack,
  hitBlackjack,
  standBlackjack,
  startBlackjack,
} from "./games/blackjack";
import { spinRoulette } from "./games/roulette";
import { spinSlots } from "./games/slots";
import { HttpError } from "./http";
import { listEvents, myBets, placeBet, recentResults } from "./sports/betting";
import { feedMode, startSportsSync } from "./sports/sync";
import { claimDailyBonus, DAILY_BONUS, leaderboard, listTransactions, nextBonusAt } from "./wallet";

const PUBLIC = join(import.meta.dir, "..", "public");

type Ctx = { req: Request; user: User; body: any };

function api(handler: (ctx: Ctx) => unknown, { auth = true } = {}) {
  return async (req: Request) => {
    try {
      let body: any = {};
      if (req.method === "POST") {
        // Exiger du JSON bloque les formulaires cross-site (protection CSRF).
        if (!req.headers.get("content-type")?.startsWith("application/json"))
          throw new HttpError(415, "JSON attendu");
        body = await req.json().catch(() => ({}));
      }
      const user = userFrom(req);
      if (auth && !user) throw new HttpError(401, "Connecte-toi d'abord");
      const result = await handler({ req, user: user!, body });
      return result instanceof Response ? result : Response.json(result);
    } catch (e) {
      if (e instanceof HttpError) return Response.json({ error: e.message }, { status: e.status });
      console.error(e);
      return Response.json({ error: "Erreur serveur" }, { status: 500 });
    }
  };
}

const withSession = (token: string | null) =>
  Response.json({ ok: true }, { headers: { "Set-Cookie": sessionCookie(token) } });

const server = Bun.serve({
  port: Number(process.env.PORT ?? 3000),
  routes: {
    "/api/register": { POST: api(async ({ body }) => withSession(await register(body.username, body.password)), { auth: false }) },
    "/api/login": { POST: api(async ({ body }) => withSession(await login(body.username, body.password)), { auth: false }) },
    "/api/logout": { POST: api(({ req }) => (logout(req), withSession(null)), { auth: false }) },
    "/api/me": {
      GET: api(({ user }) => ({
        username: user.username,
        balance: user.balance,
        nextBonusAt: nextBonusAt(user.last_bonus_at),
        dailyBonus: DAILY_BONUS,
        feed: feedMode,
      })),
    },
    "/api/bonus": { POST: api(({ user }) => ({ balance: claimDailyBonus(user.id) })) },
    "/api/transactions": { GET: api(({ user }) => listTransactions(user.id)) },
    "/api/leaderboard": { GET: api(() => leaderboard()) },

    "/api/roulette/spin": { POST: api(({ user, body }) => spinRoulette(user.id, body.bets)) },
    "/api/slots/spin": { POST: api(({ user, body }) => spinSlots(user.id, body.bet)) },
    "/api/blackjack": { GET: api(({ user }) => getBlackjack(user.id)) },
    "/api/blackjack/start": { POST: api(({ user, body }) => startBlackjack(user.id, body.bet)) },
    "/api/blackjack/hit": { POST: api(({ user }) => hitBlackjack(user.id)) },
    "/api/blackjack/stand": { POST: api(({ user }) => standBlackjack(user.id)) },
    "/api/blackjack/double": { POST: api(({ user }) => doubleBlackjack(user.id)) },

    "/api/sports/events": { GET: api(() => ({ events: listEvents(), results: recentResults() })) },
    "/api/sports/bets": {
      GET: api(({ user }) => myBets(user.id)),
      POST: api(({ user, body }) => placeBet(user.id, body.legs, body.stake)),
    },
  },
  async fetch(req) {
    const { pathname } = new URL(req.url);
    if (pathname.startsWith("/api/")) return Response.json({ error: "Introuvable" }, { status: 404 });
    const path = normalize(join(PUBLIC, pathname === "/" ? "index.html" : pathname));
    const file = Bun.file(path);
    if (path.startsWith(PUBLIC) && (await file.exists())) return new Response(file);
    return new Response(Bun.file(join(PUBLIC, "index.html")));
  },
});

startSportsSync();
console.log(`Casino prêt sur http://localhost:${server.port}`);
