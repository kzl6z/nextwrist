import { db } from "../db";
import { HttpError } from "../http";
import { randomFloat } from "../rng";
import { applyTx, getBalance, parseStake } from "../wallet";

// Le multiplicateur part de 1.00 et croît en exp(GROWTH × ms) (×2 en ~11,5 s).
// Le point de crash est tiré au lancement et reste secret jusqu'à la fin :
// P(crash ≥ m) = RTP / m, donc encaisser à n'importe quel m rapporte en moyenne RTP.
export const GROWTH = 0.00006;
const RTP = 0.97;
const MAX_MULTIPLIER = 1000;

interface Round {
  id: number;
  user_id: number;
  bet: number;
  crash_point: number;
  auto_cashout: number | null;
  started_at: number;
  status: "playing" | "won" | "lost";
  cashout_at: number | null;
  payout: number;
}

export function drawCrashPoint(): number {
  const m = Math.floor((RTP / (1 - randomFloat())) * 100) / 100;
  return Math.min(MAX_MULTIPLIER, Math.max(1, m));
}

const multiplierAt = (elapsedMs: number) => Math.floor(Math.exp(GROWTH * Math.max(0, elapsedMs)) * 100) / 100;
const timeToReach = (m: number) => Math.log(m) / GROWTH;

function current(userId: number): Round | null {
  return db.query("SELECT * FROM crash_rounds WHERE user_id = ? ORDER BY id DESC LIMIT 1").get(userId) as Round | null;
}

function finish(round: Round, status: "won" | "lost", at: number | null) {
  round.status = status;
  round.cashout_at = at;
  round.payout = status === "won" ? Math.floor(round.bet * at!) : 0;
  db.query("UPDATE crash_rounds SET status = ?, cashout_at = ?, payout = ? WHERE id = ?").run(
    status,
    at,
    round.payout,
    round.id,
  );
  if (round.payout > 0) applyTx(round.user_id, round.payout, "crash_win", `crash:${round.id}`);
}

/** Termine la manche si le crash ou l'encaissement auto est passé. */
function resolve(round: Round, now: number) {
  if (round.status !== "playing") return;
  const elapsed = now - round.started_at;
  const { auto_cashout: auto, crash_point: crash } = round;
  if (auto && auto < crash && elapsed >= timeToReach(auto)) finish(round, "won", auto);
  else if (elapsed >= timeToReach(crash)) finish(round, "lost", null);
}

function view(round: Round | null, now: number) {
  const playing = round?.status === "playing";
  return {
    round: round && {
      id: round.id,
      bet: round.bet,
      autoCashout: round.auto_cashout,
      status: round.status,
      elapsedMs: now - round.started_at,
      multiplier: playing ? multiplierAt(now - round.started_at) : undefined,
      // Révélé uniquement une fois la manche terminée.
      crashPoint: playing ? undefined : round.crash_point,
      cashoutAt: round.cashout_at,
      payout: round.payout,
    },
    history: (
      db
        .query("SELECT crash_point FROM crash_rounds WHERE status != 'playing' ORDER BY id DESC LIMIT 15")
        .all() as { crash_point: number }[]
    ).map((r) => r.crash_point),
    growth: GROWTH,
  };
}

export const getCrash = db.transaction((userId: number) => {
  const now = Date.now();
  const round = current(userId);
  if (round) resolve(round, now);
  return { ...view(round, now), balance: getBalance(userId) };
});

export const startCrash = db.transaction((userId: number, rawBet: unknown, rawAuto: unknown) => {
  const now = Date.now();
  const prev = current(userId);
  if (prev) resolve(prev, now);
  if (prev?.status === "playing") throw new HttpError(409, "Une manche est déjà en cours");

  const bet = parseStake(rawBet, 10_000);
  let auto: number | null = null;
  if (rawAuto !== undefined && rawAuto !== null && rawAuto !== "") {
    auto = Math.floor(Number(rawAuto) * 100) / 100;
    if (!Number.isFinite(auto) || auto < 1.01 || auto > MAX_MULTIPLIER)
      throw new HttpError(400, `Encaissement auto entre 1.01 et ${MAX_MULTIPLIER}`);
  }
  applyTx(userId, -bet, "crash_bet");
  const round = db
    .query(
      "INSERT INTO crash_rounds (user_id, bet, crash_point, auto_cashout, started_at) VALUES (?, ?, ?, ?, ?) RETURNING *",
    )
    .get(userId, bet, drawCrashPoint(), auto, now) as Round;
  return { ...view(round, now), balance: getBalance(userId) };
});

export const cashoutCrash = db.transaction((userId: number) => {
  const now = Date.now();
  const round = current(userId);
  if (!round || round.status !== "playing") throw new HttpError(400, "Aucune manche en cours");
  resolve(round, now);
  // Toujours en jeu => le crash n'est pas atteint, on encaisse au multiplicateur actuel.
  if (round.status === "playing") finish(round, "won", Math.min(multiplierAt(now - round.started_at), round.crash_point));
  return { ...view(round, now), balance: getBalance(userId) };
});
