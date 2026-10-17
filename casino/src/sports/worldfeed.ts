// Football du monde entier avec la clé gratuite d'API-Football (100 requêtes par jour).
//
//  - Calendrier : une requête donne tous les matchs d'une journée, partout dans le monde.
//  - Cotes d'avant-match : notre classement des équipes (ratings.ts), appris sur les résultats.
//    Les matchs déjà couverts par les bookmakers (The Odds API) gardent leurs cotes ; API-Football
//    leur apporte alors la minute de jeu exacte.
//  - Direct : une requête donne le score et la minute de tous les matchs en cours. Le quota est
//    réparti sur les heures où des matchs se jouent ; entre deux mises à jour, le moteur fait
//    tourner l'horloge, et un pari pris avant un but pas encore remonté est remboursé (engine.ts).
import { db } from "../db";
import { AF_FINISHED, AF_LIVE, AF_UPCOMING, AF_VOID, AfClient, AfError, nameSimilarity, type AfFixture } from "./apifootball";
import { applyLiveStates, ratedSim, writeRatedOdds, type LiveState } from "./engine";
import { learn, rateFixture } from "./ratings";

const DAY = 86_400_000;
const dayKey = (t: number) => new Date(t).toISOString().slice(0, 10);

export interface WorldConfig {
  /** Requêtes autorisées par jour (offre gratuite : 100). */
  daily: number;
  /** Matchs joués par équipe avant de la coter avec notre classement. */
  minGames: number;
  /** Jours de résultats passés chargés au premier lancement pour amorcer le classement. */
  bootstrapDays: number;
}

export const worldConfig = (env = process.env): WorldConfig => ({
  daily: Math.max(20, Number(env.APIFOOTBALL_DAILY ?? 100)),
  minGames: Math.max(1, Number(env.APIFOOTBALL_MIN_GAMES ?? 4)),
  bootstrapDays: Math.min(60, Math.max(0, Number(env.APIFOOTBALL_BOOTSTRAP_DAYS ?? 28))),
});

/* ---------- Petits réglages persistants ---------- */
const kvGet = (k: string) => (db.query("SELECT v FROM kv WHERE k = ?").get(k) as { v: string } | null)?.v ?? null;
const kvSet = (k: string, v: string) =>
  db.query("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v").run(k, v);

/* =========================================================
   Traitement des réponses (sans réseau : testable)
   ========================================================= */
const eventIdOf = (fixtureId: number) =>
  (db.query("SELECT event_id FROM ext_links WHERE provider = 'af' AND ext_id = ?").get(String(fixtureId)) as { event_id: string } | null)
    ?.event_id ?? null;

const leagueName = (f: AfFixture) => (f.country && f.country !== "World" ? `${f.league} - ${f.country}` : f.league);
const teamKey = (id: number) => `af:${id}`;
const leagueKey = (f: AfFixture) => `af:${f.leagueId}`;

/** Un match des bookmakers correspond-il à ce match API-Football ? (heure ±20 min, noms proches) */
function findBookmakerEvent(f: AfFixture): string | null {
  const rows = db
    .query(
      `SELECT id, home, away FROM events WHERE virtual = 0 AND sport = 'football' AND id NOT LIKE 'af-%'
       AND starts_at BETWEEN ? AND ?`,
    )
    .all(f.startsAt - 20 * 60_000, f.startsAt + 20 * 60_000) as { id: string; home: string; away: string }[];
  let best: { id: string; score: number } | null = null;
  for (const r of rows) {
    const sh = nameSimilarity(r.home, f.home);
    const sa = nameSimilarity(r.away, f.away);
    if (sh < 0.5 || sa < 0.5 || sh + sa < 1.2) continue;
    if (!best || sh + sa > best.score) best = { id: r.id, score: sh + sa };
  }
  return best?.id ?? null;
}

const link = (fixtureId: number, eventId: string) =>
  db.query("INSERT OR REPLACE INTO ext_links (provider, ext_id, event_id) VALUES ('af', ?, ?)").run(String(fixtureId), eventId);

/** Résultat d'un match terminé pour notre classement. */
const played = (f: AfFixture) => ({
  id: `af:${f.id}`,
  playedAt: f.startsAt,
  league: leagueKey(f),
  round: f.round,
  home: { key: teamKey(f.homeId), name: f.home },
  away: { key: teamKey(f.awayId), name: f.away },
  goals: [f.fulltime[0] ?? f.goals[0]!, f.fulltime[1] ?? f.goals[1]!] as [number, number],
});

/**
 * Calendrier d'une journée : apprentissage des résultats, règlement des matchs finis,
 * annulations, et mise en ligne des matchs à venir que l'on sait coter.
 */
export const applyCalendar = db.transaction((fixtures: AfFixture[], cfg: WorldConfig, now = Date.now()) => {
  // 1. Résultats : d'abord le classement, pour que les cotes des matchs à venir en profitent.
  const done = fixtures.filter((f) => AF_FINISHED.has(f.status) && f.goals[0] !== null && f.goals[1] !== null);
  learn(done.map(played));

  const finishes: LiveState[] = [];
  const cancel = db.query(
    "UPDATE events SET status = 'cancelled', updated_at = ? WHERE id = ? AND virtual = 0 AND status IN ('scheduled', 'live')",
  );
  const upsert = db.query(
    `INSERT INTO events (id, sport, league, home, away, starts_at, feed_key, odds_at, updated_at, status)
     VALUES (?1, 'football', ?2, ?3, ?4, ?5, ?6, ?7, ?7, 'scheduled')
     ON CONFLICT(id) DO UPDATE SET starts_at = excluded.starts_at, league = excluded.league, odds_at = excluded.odds_at,
       updated_at = excluded.updated_at WHERE events.status = 'scheduled'`,
  );
  let listed = 0;
  for (const f of fixtures) {
    let eventId = eventIdOf(f.id);
    if (!eventId && (AF_UPCOMING.has(f.status) || AF_LIVE.has(f.status))) {
      eventId = findBookmakerEvent(f);
      if (eventId) link(f.id, eventId);
    }
    if (AF_FINISHED.has(f.status)) {
      if (eventId) finishes.push({ id: eventId, homeScore: played(f).goals[0], awayScore: played(f).goals[1], completed: true });
      continue;
    }
    if (AF_VOID.has(f.status)) {
      if (eventId) cancel.run(now, eventId);
      continue;
    }
    if (!AF_UPCOMING.has(f.status) || f.startsAt < now + 2 * 60_000 || f.startsAt > now + 36 * 3_600_000) continue;
    // Match des bookmakers : il garde ses cotes.
    if (eventId && !eventId.startsWith("af-")) continue;
    const goals = rateFixture(teamKey(f.homeId), teamKey(f.awayId), leagueKey(f), f.round, cfg.minGames);
    if (!goals) continue;
    const id = eventId ?? `af-${f.id}`;
    upsert.run(id, leagueName(f), f.home, f.away, f.startsAt, leagueKey(f), now);
    if (!eventId) link(f.id, id);
    writeRatedOdds(id, ratedSim(goals[0], goals[1], now));
    listed++;
  }
  if (finishes.length) applyLiveStates(finishes, now);
  return { learned: done.length, listed };
});

/** Matchs en cours : score, minute, cartons rouges. */
export function liveStates(fixtures: AfFixture[], ttl: number): { states: LiveState[]; seen: number[] } {
  const states: LiveState[] = [];
  const seen: number[] = [];
  for (const f of fixtures) {
    let eventId = eventIdOf(f.id);
    if (!eventId) {
      eventId = findBookmakerEvent(f);
      if (eventId) link(f.id, eventId);
    }
    if (!eventId || f.goals[0] === null || f.goals[1] === null) continue;
    seen.push(f.id);
    // Prolongation, tirs au but : le temps réglementaire est fini, les paris se règlent dessus.
    if (["ET", "BT", "P"].includes(f.status) && f.fulltime[0] !== null && f.fulltime[1] !== null) {
      states.push({ id: eventId, homeScore: f.fulltime[0], awayScore: f.fulltime[1]!, completed: true });
      continue;
    }
    // Match interrompu : pas de mise à jour, les paris se ferment d'eux-mêmes.
    if (f.status === "SUSP" || f.status === "INT") continue;
    states.push({
      id: eventId,
      homeScore: f.goals[0],
      awayScore: f.goals[1]!,
      completed: false,
      minute: f.status === "HT" ? 45 : (f.elapsed ?? undefined),
      period: f.status === "1H" ? 1 : f.status === "2H" ? 2 : undefined,
      paused: f.status === "HT",
      red: f.red ?? undefined,
      ttl,
    });
  }
  return { states, seen };
}

/* =========================================================
   Planification des requêtes sur la journée
   ========================================================= */
/**
 * Intervalle entre deux mises à jour du direct (ms) : les requêtes restantes sont réparties sur
 * le temps pendant lequel des matchs du calendrier seront encore en cours aujourd'hui.
 */
export function liveInterval(remaining: number, kickoffs: number[], now: number, reserve = 8): number {
  const endOfDay = Math.floor(now / DAY) * DAY + DAY;
  // Fenêtres de jeu restantes (coup d'envoi → fin probable), fusionnées.
  const spans = kickoffs
    .map((k) => [Math.max(k, now), Math.min(k + 115 * 60_000, endOfDay)] as const)
    .filter(([a, b]) => b > a)
    .sort((x, y) => x[0] - y[0]);
  let busy = 0;
  let cur: [number, number] | null = null;
  for (const [a, b] of spans) {
    if (cur && a <= cur[1]) cur[1] = Math.max(cur[1], b);
    else {
      if (cur) busy += cur[1] - cur[0];
      cur = [a, b];
    }
  }
  if (cur) busy += cur[1] - cur[0];
  const calls = Math.max(1, remaining - reserve);
  return Math.min(30 * 60_000, Math.max(3 * 60_000, busy / calls));
}

/** Coups d'envoi du jour connus (pour répartir le quota). */
function todaysKickoffs(now: number): number[] {
  const start = Math.floor(now / DAY) * DAY;
  return (
    db
      .query(
        `SELECT DISTINCT e.starts_at FROM events e JOIN ext_links l ON l.event_id = e.id AND l.provider = 'af'
         WHERE e.starts_at BETWEEN ? AND ? AND e.status IN ('scheduled', 'live')`,
      )
      .all(start - 3 * 3_600_000, start + DAY) as { starts_at: number }[]
  ).map((r) => r.starts_at);
}

/** Matchs suivis en direct qui ont disparu de la liste « en cours » (probablement terminés). */
const vanished = new Set<number>();

export function startWorldFeed(key: string, cfg = worldConfig(), log = console.log, fetcher: typeof fetch = fetch) {
  const client = new AfClient(key, fetcher);
  let used = 0;
  let usedDay = dayKey(Date.now());
  let disabledUntil = 0;
  let lastLive = 0;
  let liveIds = new Set<number>();
  /** Matchs du jour vus en cours ou à venir (pour savoir quand interroger le direct). */
  let fixturesToday: AfFixture[] = [];

  const remaining = () => {
    const today = dayKey(Date.now());
    if (today !== usedDay) {
      usedDay = today;
      used = 0;
      client.remaining = null;
    }
    return client.remaining ?? cfg.daily - used;
  };
  const call = async (query: string) => {
    used++;
    return client.fixtures(query);
  };
  const due = (k: string, everyMs: number) => Date.now() - Number(kvGet(k) ?? 0) >= everyMs;

  async function step() {
    const now = Date.now();
    if (now < disabledUntil || remaining() <= 2) return;
    try {
      // 1. Amorçage du classement : résultats des semaines passées, quelques jours à la fois.
      const boot = Number(kvGet("af:bootstrap") ?? 0);
      if (boot < cfg.bootstrapDays && remaining() > 40) {
        const day = dayKey(now - (boot + 1) * DAY);
        const res = applyCalendar(await call(`date=${day}&timezone=UTC`), cfg, now);
        kvSet("af:bootstrap", String(boot + 1));
        // Classement amorcé : le calendrier du jour est rechargé tout de suite pour en profiter.
        if (boot + 1 >= cfg.bootstrapDays) kvSet("af:today", "0");
        log(`[monde] classement : ${res.learned} résultat(s) du ${day} appris`);
        return;
      }
      // 2. Calendrier du jour (toutes les 2 h), du lendemain (une fois par jour), de la veille (matchs finis après minuit).
      if (due("af:today", 2 * 3_600_000)) {
        kvSet("af:today", String(now));
        fixturesToday = await call(`date=${dayKey(now)}&timezone=UTC`);
        const res = applyCalendar(fixturesToday, cfg, now);
        log(`[monde] ${fixturesToday.length} match(s) aujourd'hui, ${res.listed} coté(s) par notre classement, ${remaining()} requête(s) restante(s)`);
        return;
      }
      if (due("af:tomorrow", DAY) && new Date(now).getUTCHours() >= 6) {
        kvSet("af:tomorrow", String(now));
        const res = applyCalendar(await call(`date=${dayKey(now + DAY)}&timezone=UTC`), cfg, now);
        log(`[monde] demain : ${res.listed} match(s) coté(s)`);
        return;
      }
      if (due("af:yesterday", DAY) && new Date(now).getUTCHours() >= 2) {
        kvSet("af:yesterday", String(now));
        applyCalendar(await call(`date=${dayKey(now - DAY)}&timezone=UTC`), cfg, now);
        return;
      }
      // 3. Direct : seulement quand des matchs suivis se jouent.
      const kickoffs = todaysKickoffs(now);
      const playing = kickoffs.some((k) => k <= now && now < k + 125 * 60_000);
      if (!playing) return;
      const interval = liveInterval(remaining(), kickoffs, now);
      if (now - lastLive < interval) return;
      lastLive = now;
      const fixtures = await call("live=all");
      const { states, seen } = liveStates(fixtures, Math.round(interval * 2.2 + 60_000));
      applyLiveStates(states, now);
      const current = new Set(seen);
      for (const id of liveIds) if (!current.has(id)) vanished.add(id);
      liveIds = current;
      // Matchs finis entre deux passages : on va chercher leur résultat (20 par requête).
      if (vanished.size && remaining() > 12) {
        const ids = [...vanished].slice(0, 20);
        ids.forEach((id) => vanished.delete(id));
        applyCalendar(await call(`ids=${ids.join("-")}`), cfg, now);
      }
    } catch (e) {
      if (e instanceof AfError) {
        // Clé invalide, quota atteint ou saison non couverte par l'offre gratuite : pause d'une heure.
        disabledUntil = Date.now() + 3_600_000;
        log(`[monde] API-Football refuse la requête : ${e.message}`);
      } else throw e;
    }
  }
  return { step, fixturesToday: () => fixturesToday };
}
