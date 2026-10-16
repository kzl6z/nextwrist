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
import { bigWins, myRounds } from "./games/common";
import { cashoutCrash, getCrash, startCrash } from "./games/crash";
import { casinoConfig, playDice, playKeno, playLimbo, playPlinko, playWheel } from "./games/instant";
import { spinRoulette } from "./games/roulette";
import { spinSlots } from "./games/slots";
import {
  cashoutCoin,
  cashoutHilo,
  cashoutMines,
  cashoutTower,
  flipCoin,
  getCoin,
  getHilo,
  getMines,
  getTower,
  guessHilo,
  pickTower,
  revealMines,
  startCoin,
  startHilo,
  startMines,
  startTower,
} from "./games/steps";
import { dealPoker, drawPoker, getPoker, playBaccarat, POKER_PAYS } from "./games/tables";
import {
  getRace,
  moreConfig,
  playChest,
  playDarts,
  playDiamonds,
  playDragonTiger,
  playRace,
  playScratch,
  playSicbo,
  playSlot5,
} from "./games/more";
import {
  cashoutBalloon,
  cashoutCrossing,
  cashoutPenalty,
  cashoutRps,
  dealThreeCard,
  decideThreeCard,
  getBalloon,
  getCrossing,
  getPenalty,
  getRps,
  getThreeCard,
  moreStepsConfig,
  playRps,
  pumpBalloon,
  shootPenalty,
  startBalloon,
  startCrossing,
  startPenalty,
  startRps,
  stepCrossing,
} from "./games/more-steps";
import { HttpError } from "./http";
import { cashOut, eventCounts, eventDetail, listEvents, liveEvents, myBets, placeBet, recentResults } from "./sports/betting";
import { feedMode, startSportsSync, virtualOn } from "./sports/sync";
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
      if (e instanceof HttpError) return Response.json({ error: e.message, ...e.data }, { status: e.status });
      console.error(e);
      return Response.json({ error: "Erreur serveur" }, { status: 500 });
    }
  };
}

const withSession = (token: string | null) =>
  Response.json({ ok: true }, { headers: { "Set-Cookie": sessionCookie(token) } });

const GAMES = new Set([
  "crash", "roulette", "slots", "blackjack", "dice", "limbo", "plinko", "wheel", "keno",
  "mines", "hilo", "tower", "coinflip", "baccarat", "videopoker",
  "dragontiger", "sicbo", "diamonds", "scratch", "darts", "chest", "race", "slot5",
  "threecard", "crossing", "balloon", "penalty", "rps",
]);

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
        virtual: virtualOn,
      })),
    },
    "/api/bonus": { POST: api(({ user }) => ({ balance: claimDailyBonus(user.id) })) },
    "/api/transactions": { GET: api(({ user }) => listTransactions(user.id)) },
    "/api/leaderboard": { GET: api(() => leaderboard()) },

    /* ---------- Casino ---------- */
    "/api/casino/config": { GET: api(() => ({ ...casinoConfig(), poker: POKER_PAYS, ...moreConfig(), ...moreStepsConfig() })) },
    "/api/casino/feed": { GET: api(() => bigWins()) },
    "/api/casino/history/:game": {
      GET: api(({ req, user }) => {
        const game = (req as any).params.game;
        if (!GAMES.has(game)) throw new HttpError(404, "Jeu inconnu");
        return myRounds(user.id, game);
      }),
    },

    "/api/roulette/spin": { POST: api(({ user, body }) => spinRoulette(user.id, body.bets)) },
    "/api/slots/spin": { POST: api(({ user, body }) => spinSlots(user.id, body.bet)) },
    "/api/blackjack": { GET: api(({ user }) => getBlackjack(user.id)) },
    "/api/blackjack/start": { POST: api(({ user, body }) => startBlackjack(user.id, body.bet)) },
    "/api/blackjack/hit": { POST: api(({ user }) => hitBlackjack(user.id)) },
    "/api/blackjack/stand": { POST: api(({ user }) => standBlackjack(user.id)) },
    "/api/blackjack/double": { POST: api(({ user }) => doubleBlackjack(user.id)) },

    "/api/crash": { GET: api(({ user }) => getCrash(user.id)) },
    "/api/crash/start": { POST: api(({ user, body }) => startCrash(user.id, body.bet, body.autoCashout)) },
    "/api/crash/cashout": { POST: api(({ user }) => cashoutCrash(user.id)) },

    "/api/dice": { POST: api(({ user, body }) => playDice(user.id, body.bet, body.target, body.over)) },
    "/api/limbo": { POST: api(({ user, body }) => playLimbo(user.id, body.bet, body.target)) },
    "/api/plinko": { POST: api(({ user, body }) => playPlinko(user.id, body.bet, body.rows, body.risk)) },
    "/api/wheel": { POST: api(({ user, body }) => playWheel(user.id, body.bet, body.risk)) },
    "/api/keno": { POST: api(({ user, body }) => playKeno(user.id, body.bet, body.picks)) },
    "/api/baccarat": { POST: api(({ user, body }) => playBaccarat(user.id, body.bets)) },

    "/api/mines": { GET: api(({ user }) => getMines(user.id)) },
    "/api/mines/start": { POST: api(({ user, body }) => startMines(user.id, body.bet, body.mines)) },
    "/api/mines/reveal": { POST: api(({ user, body }) => revealMines(user.id, body.cell)) },
    "/api/mines/cashout": { POST: api(({ user }) => cashoutMines(user.id)) },

    "/api/hilo": { GET: api(({ user }) => getHilo(user.id)) },
    "/api/hilo/start": { POST: api(({ user, body }) => startHilo(user.id, body.bet)) },
    "/api/hilo/guess": { POST: api(({ user, body }) => guessHilo(user.id, body.dir)) },
    "/api/hilo/cashout": { POST: api(({ user }) => cashoutHilo(user.id)) },

    "/api/tower": { GET: api(({ user }) => getTower(user.id)) },
    "/api/tower/start": { POST: api(({ user, body }) => startTower(user.id, body.bet, body.difficulty)) },
    "/api/tower/pick": { POST: api(({ user, body }) => pickTower(user.id, body.col)) },
    "/api/tower/cashout": { POST: api(({ user }) => cashoutTower(user.id)) },

    "/api/dragontiger": { POST: api(({ user, body }) => playDragonTiger(user.id, body.bets)) },
    "/api/sicbo": { POST: api(({ user, body }) => playSicbo(user.id, body.bets)) },
    "/api/diamonds": { POST: api(({ user, body }) => playDiamonds(user.id, body.bet)) },
    "/api/scratch": { POST: api(({ user, body }) => playScratch(user.id, body.bet)) },
    "/api/darts": { POST: api(({ user, body }) => playDarts(user.id, body.bet, body.risk)) },
    "/api/chest": { POST: api(({ user, body }) => playChest(user.id, body.bet, body.risk)) },
    "/api/slot5": { POST: api(({ user, body }) => playSlot5(user.id, body.bet)) },
    "/api/race": { GET: api(({ user }) => getRace(user.id)) },
    "/api/race/bet": { POST: api(({ user, body }) => playRace(user.id, body.bet, body.horse, body.type)) },

    "/api/threecard": { GET: api(({ user }) => getThreeCard(user.id)) },
    "/api/threecard/deal": { POST: api(({ user, body }) => dealThreeCard(user.id, body.ante, body.pairPlus)) },
    "/api/threecard/decide": { POST: api(({ user, body }) => decideThreeCard(user.id, body.action)) },

    "/api/crossing": { GET: api(({ user }) => getCrossing(user.id)) },
    "/api/crossing/start": { POST: api(({ user, body }) => startCrossing(user.id, body.bet, body.mode)) },
    "/api/crossing/step": { POST: api(({ user }) => stepCrossing(user.id)) },
    "/api/crossing/cashout": { POST: api(({ user }) => cashoutCrossing(user.id)) },

    "/api/balloon": { GET: api(({ user }) => getBalloon(user.id)) },
    "/api/balloon/start": { POST: api(({ user, body }) => startBalloon(user.id, body.bet, body.mode)) },
    "/api/balloon/pump": { POST: api(({ user }) => pumpBalloon(user.id)) },
    "/api/balloon/cashout": { POST: api(({ user }) => cashoutBalloon(user.id)) },

    "/api/penalty": { GET: api(({ user }) => getPenalty(user.id)) },
    "/api/penalty/start": { POST: api(({ user, body }) => startPenalty(user.id, body.bet, body.mode)) },
    "/api/penalty/shoot": { POST: api(({ user, body }) => shootPenalty(user.id, body.zone)) },
    "/api/penalty/cashout": { POST: api(({ user }) => cashoutPenalty(user.id)) },

    "/api/rps": { GET: api(({ user }) => getRps(user.id)) },
    "/api/rps/start": { POST: api(({ user, body }) => startRps(user.id, body.bet, body.move)) },
    "/api/rps/play": { POST: api(({ user, body }) => playRps(user.id, body.move)) },
    "/api/rps/cashout": { POST: api(({ user }) => cashoutRps(user.id)) },

    "/api/coinflip": { GET: api(({ user }) => getCoin(user.id)) },
    "/api/coinflip/start": { POST: api(({ user, body }) => startCoin(user.id, body.bet, body.side)) },
    "/api/coinflip/flip": { POST: api(({ user, body }) => flipCoin(user.id, body.side)) },
    "/api/coinflip/cashout": { POST: api(({ user }) => cashoutCoin(user.id)) },

    "/api/videopoker": { GET: api(({ user }) => getPoker(user.id)) },
    "/api/videopoker/deal": { POST: api(({ user, body }) => dealPoker(user.id, body.bet)) },
    "/api/videopoker/draw": { POST: api(({ user, body }) => drawPoker(user.id, body.holds)) },

    /* ---------- Paris sportifs ---------- */
    "/api/sports/events": {
      GET: api(({ req }) => {
        const q = new URL(req.url).searchParams;
        return {
          events: listEvents(q.get("sport"), q.get("league")),
          live: liveEvents(),
          results: recentResults(),
          counts: eventCounts(),
        };
      }),
    },
    "/api/sports/live": { GET: api(() => ({ live: liveEvents() })) },
    "/api/sports/event/:id": { GET: api(({ req }) => eventDetail((req as any).params.id)) },
    "/api/sports/bets": {
      GET: api(({ user }) => myBets(user.id)),
      POST: api(({ user, body }) => placeBet(user.id, body.legs, body.stake, body.acceptChanges)),
    },
    "/api/sports/cashout": { POST: api(({ user, body }) => cashOut(user.id, body.betId, body.value)) },
  },
  async fetch(req) {
    const { pathname } = new URL(req.url);
    if (pathname.startsWith("/api/")) return Response.json({ error: "Introuvable" }, { status: 404 });
    const path = normalize(join(PUBLIC, pathname === "/" ? "index.html" : pathname));
    const file = Bun.file(path);
    // Le navigateur revérifie les fichiers à chaque chargement : une mise à jour s'affiche tout de suite.
    const headers = { "Cache-Control": "no-cache" };
    if (path.startsWith(PUBLIC) && (await file.exists())) return new Response(file, { headers });
    return new Response(Bun.file(join(PUBLIC, "index.html")), { headers });
  },
});

startSportsSync();
console.log(`Casino prêt sur http://localhost:${server.port}`);
