// Moteur de cotes maison pour les vrais matchs.
//
// Avant le match, les cotes des bookmakers servent à caler nos modèles (force de chaque équipe,
// niveau de marque attendu). Pendant le match, chaque nouvel état reçu de la source de direct
// (score, et si elle les fournit : minute, cartons rouges) est injecté dans le modèle, qui
// recalcule tous les marchés. Sans minute fournie, l'horloge est estimée depuis le coup d'envoi.
//
// La source de direct est indépendante du moteur : il suffit de lui passer des `LiveState`.
import { db } from "../db";
import { half } from "./kit";
import { priceOf, scorePredicate } from "./markets";
import { MODELS, type Sim, type SportId } from "./models";

/** Sports dont le score suffit à décrire l'état du match (le moteur sait les coter en direct). */
export const ENGINE_SPORTS = new Set<SportId>(["football", "hockey", "basketball", "handball", "rugby", "americanfootball", "baseball"]);

/** Marchés suspendus après un changement de score (la source a toujours un peu de retard). */
const SUSPEND_MS = 20_000;
/** Marge supplémentaire des cotes en direct calculées par le moteur. */
const LIVE_EXTRA_MARGIN = 1.02;
/** Sports où chaque point est inscrit dans le fil du match. */
const TIMELINE_SPORTS = new Set<SportId>(["football", "hockey"]);

/** État d'un vrai match transmis par la source de direct. */
export interface LiveState {
  id: string;
  homeScore: number;
  awayScore: number;
  completed: boolean;
  /** Avancement du match entre 0 et 1, si la source le connaît (sinon estimé). */
  progress?: number;
  /** Libellé d'horloge fourni par la source (ex. « 67' », « Mi-temps »). */
  clock?: string;
  /** Cartons rouges (football), si la source les fournit. */
  red?: [number, number];
  /** Football : minute de jeu donnée par la source, période (1 ou 2) et mi-temps en cours. */
  minute?: number;
  period?: 1 | 2;
  paused?: boolean;
  /** Durée de validité de cette mise à jour (ms) quand la source passe moins souvent que d'habitude. */
  ttl?: number;
}

export interface EngineSim extends Sim {
  /** Pas de match nul sur le marché réel (prolongation comprise) : hockey, basket… */
  twoWay: boolean;
  /** Date des cotes bookmakers ayant servi au calage. */
  fitAt: number;
  /** Pronostics ajoutés par le moteur (à ne pas reprendre comme cibles d'un nouveau calage). */
  own: string[];
  red?: [number, number];
  /** Le match a commencé : le calage d'avant-match est figé. */
  live?: boolean;
  /** Cotes d'avant-match tirées de notre classement des équipes (pas de calage sur des bookmakers). */
  rated?: boolean;
  /** Avancement et horloge fournis par la source, quand elle en donne. */
  srcProgress?: number;
  srcClock?: string;
  srcMinute?: number;
  srcPeriod?: 1 | 2;
  srcPaused?: boolean;
  srcAt?: number;
}

/* =========================================================
   Calage sur les cotes d'avant-match
   ========================================================= */
/** Paramètres de rythme de marque, mis à l'échelle pour caler le total attendu. */
const RATES: Partial<Record<SportId, string[]>> = {
  football: ["lh", "la"],
  hockey: ["lh", "la"],
  basketball: ["lh", "la"],
  handball: ["lh", "la"],
  baseball: ["lh", "la"],
  rugby: ["th", "ta", "pens"],
  americanfootball: ["tdh", "tda", "fg"],
};

/** Points attendus de chaque équipe sur un match complet. */
function expected(sport: SportId, p: Record<string, number>): [number, number] {
  if (sport === "rugby") return [p.th! * (5 + 2 * p.conv!) + p.pens! * 3, p.ta! * (5 + 2 * p.conv!) + p.pens! * 3];
  if (sport === "americanfootball") return [p.tdh! * (6 + p.conv!) + p.fg! * 3, p.tda! * (6 + p.conv!) + p.fg! * 3];
  return [p.lh!, p.la!];
}

/** Sports dont les lignes de marché suivent le total attendu (les autres ont des lignes fixes). */
const SHIFT_LINES = new Set<SportId>(["basketball", "handball", "rugby", "americanfootball", "baseball"]);

function build(sport: SportId, d: number, k: number): Sim {
  const model = MODELS[sport];
  const base = model.create(d);
  const s = model.create(d);
  for (const r of RATES[sport] ?? []) s.p[r]! *= k;
  if (SHIFT_LINES.has(sport)) {
    const [bh, ba] = expected(sport, base.p);
    const [eh, ea] = expected(sport, s.p);
    const shift = (lines: number[] | undefined, by: number) => lines?.map((L) => L + by);
    s.lines.ou = shift(s.lines.ou, half(eh + ea) - half(bh + ba))!;
    s.lines.th = shift(s.lines.th, half(eh) - half(bh))!;
    s.lines.ta = shift(s.lines.ta, half(ea) - half(ba))!;
    if (sport !== "baseball") s.lines.ah = shift(s.lines.ah, half(ea - eh) - half(ba - bh))!;
  }
  return s;
}

/** Recherche par dichotomie de x tel que f(x) = 0 (f croissante). */
function solve(f: (x: number) => number, lo: number, hi: number, iters = 24) {
  for (let i = 0; i < iters; i++) {
    const mid = (lo + hi) / 2;
    if (f(mid) < 0) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

/**
 * Cale le modèle du sport sur des probabilités d'avant-match (sans marge) :
 * part du favori sur le vainqueur, puis total principal s'il est connu.
 */
export function calibrate(sport: SportId, probs: Map<string, number>): Sim | null {
  const model = MODELS[sport];
  const pH = probs.get("home");
  const pA = probs.get("away");
  if (!model || !RATES[sport] || !pH || !pA) return null;
  const share = pH / (pH + pA);
  // Ligne de total la plus équilibrée chez les bookmakers.
  let total: { L: number; p: number } | null = null;
  for (const [key, p] of probs) {
    const [m, L, side] = key.split(":");
    if (m !== "ou" || side !== "over") continue;
    if (!total || Math.abs(p - 0.5) < Math.abs(total.p - 0.5)) total = { L: Number(L), p };
  }
  const homeShare = (s: Sim) => {
    const o = model.probs(s);
    const h = o.get("home") ?? 0;
    const a = o.get("away") ?? 0;
    return h / (h + a || 1);
  };
  const over = (s: Sim) => {
    s.lines.ou = [...new Set([...(s.lines.ou ?? []), total!.L])];
    return model.probs(s).get(`ou:${total!.L}:over`) ?? 0;
  };
  let d = 0;
  let k = 1;
  for (let round = 0; round < (total ? 3 : 1); round++) {
    d = solve((x) => homeShare(build(sport, x, k)) - share, -6, 6);
    if (total) k = solve((y) => over(build(sport, d, y)) - total!.p, 0.25, 4);
  }
  const sim = build(sport, d, k);
  // Les lignes des bookmakers sont reprises telles quelles.
  for (const key of probs.keys()) {
    const [m, L] = key.split(":");
    if (["ou", "ah", "th", "ta"].includes(m!) && sim.lines[m!]) {
      const v = Number(L);
      if (Number.isFinite(v) && !sim.lines[m!]!.includes(v)) sim.lines[m!]!.push(v);
    }
  }
  for (const m of Object.keys(sim.lines)) sim.lines[m]!.sort((a, b) => a - b);
  return sim;
}

/* =========================================================
   Cotation
   ========================================================= */
/** Pronostics réglables avec le seul score final (les seuls proposés sur un vrai match). */
const settleable = (key: string) => key.startsWith("dnb:") || scorePredicate(key) !== null;
const DRAW_KEYS = (key: string) => key === "draw" || key.startsWith("dc:") || key.startsWith("dnb:") || key.startsWith("cs:") || key === "mg:d";

/** Probabilités de tous les pronostics d'un vrai match dans l'état courant. */
export function engineProbs(sim: EngineSim): Map<string, number> {
  const s: Sim = { ...sim, p: { ...sim.p }, lines: sim.lines };
  // Carton rouge : l'équipe réduite marque moins, l'autre davantage, pour le temps restant.
  if (sim.sport === "football" && sim.red) {
    const [rh, ra] = sim.red;
    s.p.lh! *= 0.7 ** rh * 1.18 ** ra;
    s.p.la! *= 0.7 ** ra * 1.18 ** rh;
  }
  const raw = MODELS[sim.sport].probs(s);
  const out = new Map<string, number>();
  for (const [k, p] of raw) if (settleable(k)) out.set(k, p);
  if (sim.twoWay && out.has("draw")) {
    // Marché réel sans nul (prolongation, tirs au but) : l'égalité est partagée selon la force.
    const h = out.get("home")!;
    const a = out.get("away")!;
    const dr = out.get("draw")!;
    const q = h / (h + a || 1);
    out.set("home", h + dr * q);
    out.set("away", a + dr * (1 - q));
    for (const k of [...out.keys()]) if (DRAW_KEYS(k)) out.delete(k);
  }
  return out;
}

/* =========================================================
   Horloge estimée (quand la source ne donne que le score)
   ========================================================= */
/**
 * Durées réelles typiques : [durée d'une mi-temps ou d'une période en minutes réelles,
 * nombre de périodes, pause entre périodes, pause à la mi-temps].
 */
function timing(sport: SportId, feedKey: string | null): { part: number; parts: number; pause: number; ht: number } {
  switch (sport) {
    case "football":
      return { part: 47, parts: 2, pause: 0, ht: 15 };
    case "hockey":
      return { part: 37, parts: 3, pause: 18, ht: 18 };
    case "basketball":
      return feedKey?.includes("nba")
        ? { part: 31, parts: 4, pause: 3, ht: 15 }
        : { part: 26, parts: 4, pause: 2, ht: 15 };
    case "handball":
      return { part: 34, parts: 2, pause: 0, ht: 12 };
    case "rugby":
      return { part: 47, parts: 2, pause: 0, ht: 12 };
    case "americanfootball":
      return { part: 42, parts: 4, pause: 3, ht: 14 };
    case "baseball":
      return { part: 165, parts: 1, pause: 0, ht: 0 };
    default:
      return { part: 60, parts: 1, pause: 0, ht: 0 };
  }
}

/** Avancement estimé (0 à 1) d'un match commencé depuis `elapsed` minutes, et pause en cours. */
export function estimateProgress(sport: SportId, feedKey: string | null, elapsed: number): { progress: number; pause: string | null } {
  const { part, parts, pause, ht } = timing(sport, feedKey);
  let rest = Math.max(0, elapsed);
  for (let i = 0; i < parts; i++) {
    if (rest < part) return { progress: (i + rest / part) / parts, pause: null };
    rest -= part;
    if (i === parts - 1) break;
    const p = parts > 2 && i === parts / 2 - 1 ? ht : parts === 2 ? ht : pause;
    if (rest < p) return { progress: (i + 1) / parts, pause: parts === 2 || (parts === 4 && i === 1) ? "Mi-temps" : "Pause" };
    rest -= p;
  }
  return { progress: 1, pause: null };
}

/** Avancement maximum tant que la source n'a pas annoncé la fin (temps additionnel, prolongations). */
const MAX_PROGRESS = 0.975;

/** Avancement du match et horloge affichée, d'après la source si elle donne la minute, sinon estimés. */
export function liveClock(sim: EngineSim, startsAt: number, feedKey: string | null, now: number): { progress: number; label: string } {
  // Minute fournie par la source : elle continue de tourner entre deux mises à jour.
  if (sim.sport === "football" && sim.srcMinute !== undefined && sim.srcAt !== undefined) {
    if (sim.srcPaused) return { progress: 0.5, label: "Mi-temps" };
    const drift = (now - sim.srcAt) / 60_000;
    const m = sim.srcMinute + drift;
    const period = sim.srcPeriod ?? (sim.srcMinute > 45 ? 2 : 1);
    const progress = period === 1 ? Math.min(0.5, m / 90) : Math.min(MAX_PROGRESS, Math.max(0.5, m / 90));
    const approx = drift > 1.5 ? "≈ " : "";
    if (period === 1 && m > 45) return { progress, label: "45'+" };
    if (period === 2 && m > 90) return { progress, label: "90'+" };
    return { progress, label: `${approx}${Math.max(1, Math.floor(m))}'` };
  }
  const est = estimateProgress(sim.sport, feedKey, (now - startsAt) / 60_000);
  const progress = Math.min(MAX_PROGRESS, sim.srcProgress ?? est.progress);
  if (sim.srcClock) return { progress, label: sim.srcClock };
  if (est.pause) return { progress, label: est.pause };
  // Au-delà de la durée habituelle : temps additionnel ou prolongation, la source dira quand c'est fini.
  if (est.progress >= 1) return { progress, label: sim.sport === "football" ? "≈ 90'+" : sim.sport === "rugby" ? "≈ 80'+" : "Dernières minutes" };
  const t = Math.max(sim.t, progress * MODELS[sim.sport].len);
  return { progress, label: `≈ ${MODELS[sim.sport].clock({ ...sim, t, done: false })}` };
}

/* =========================================================
   Mise à jour des matchs en base
   ========================================================= */
const upsertSel = () =>
  db.query(
    `INSERT INTO selections (event_id, key, price, prob) VALUES (?, ?, ?, ?)
     ON CONFLICT(event_id, key) DO UPDATE SET price = excluded.price, prob = excluded.prob`,
  );

/** Probabilités d'avant-match publiées par les bookmakers pour ce match. */
function bookmakerProbs(eventId: string, own: string[] = []): Map<string, number> {
  const skip = new Set(own);
  const rows = db
    .query("SELECT key, prob FROM selections WHERE event_id = ? AND price IS NOT NULL AND prob IS NOT NULL")
    .all(eventId) as { key: string; prob: number }[];
  return new Map(rows.filter((r) => !skip.has(r.key)).map((r) => [r.key, r.prob]));
}

function fit(eventId: string, sport: SportId, oddsAt: number, previous: EngineSim | null): EngineSim | null {
  const probs = bookmakerProbs(eventId, previous?.own);
  const sim = calibrate(sport, probs);
  if (!sim) return null;
  return { ...sim, twoWay: !probs.has("draw"), fitAt: oddsAt, own: [] };
}

interface Row {
  id: string;
  sport: SportId;
  feed_key: string | null;
  starts_at: number;
  status: string;
  home_score: number | null;
  away_score: number | null;
  sim: string | null;
  odds_at: number | null;
  detail: string | null;
  suspended_until: number | null;
}

/**
 * Avant-match : complète un vrai match avec tous les marchés du modèle (score exact, les deux
 * équipes marquent, lignes de total et de handicap…), sans toucher aux cotes des bookmakers.
 */
export const enginePrematch = db.transaction((eventId: string) => {
  const row = db
    .query("SELECT id, sport, feed_key, starts_at, status, sim, odds_at FROM events WHERE id = ? AND virtual = 0")
    .get(eventId) as Row | null;
  if (!row || row.status !== "scheduled" || row.starts_at <= Date.now() || !ENGINE_SPORTS.has(row.sport)) return;
  const prev = row.sim ? (JSON.parse(row.sim) as EngineSim) : null;
  if (prev && prev.fitAt >= (row.odds_at ?? 0)) return;
  const sim = fit(row.id, row.sport, row.odds_at ?? Date.now(), prev);
  if (!sim) return;
  const taken = new Set(bookmakerProbs(row.id, prev?.own).keys());
  const set = upsertSel();
  for (const [key, p] of engineProbs(sim)) {
    if (taken.has(key)) continue;
    const price = priceOf(key, p);
    if (price === null) continue;
    set.run(row.id, key, price, p);
    sim.own.push(key);
  }
  db.query("UPDATE events SET sim = ? WHERE id = ?").run(JSON.stringify(sim), row.id);
});

/**
 * Reçoit l'état des vrais matchs depuis la source de direct (score, horloge, cartons).
 *
 * La source a toujours un peu de retard. Quand elle annonce un nouveau score, les paris pris
 * depuis sa mise à jour précédente l'ont été sur une information peut-être dépassée (le but avait
 * peut-être déjà eu lieu) : ces sélections sont remboursées.
 */
export const applyLiveStates = db.transaction((states: LiveState[], now = Date.now()) => {
  const fresh = db.query(
    `UPDATE events SET odds_at = ?, home_score = ?, away_score = ?, status = 'live', live_ttl = ?, updated_at = ?
     WHERE id = ? AND virtual = 0 AND status IN ('scheduled', 'live') AND starts_at <= ?`,
  );
  const finish = db.query(
    `UPDATE events SET status = 'finished', home_score = ?, away_score = ?, clock = 'Terminé', updated_at = ?
     WHERE id = ? AND virtual = 0 AND status IN ('scheduled', 'live')`,
  );
  const close = db.query("UPDATE selections SET price = NULL WHERE event_id = ?");
  const getRow = db.query("SELECT sim, sport, home_score, away_score, odds_at, status FROM events WHERE id = ? AND virtual = 0");
  const setSim = db.query("UPDATE events SET sim = ? WHERE id = ?");
  const voidSince = db.query(
    "UPDATE bet_legs SET result = 'void' WHERE event_id = ? AND result = 'pending' AND seen_at IS NOT NULL AND seen_at >= ?",
  );
  for (const s of states) {
    if (s.completed) {
      finish.run(s.homeScore, s.awayScore, now, s.id);
      close.run(s.id);
      continue;
    }
    const row = getRow.get(s.id) as {
      sim: string | null;
      sport: SportId;
      home_score: number | null;
      away_score: number | null;
      odds_at: number | null;
      status: string;
    } | null;
    if (!row || !ENGINE_SPORTS.has(row.sport) || !["scheduled", "live"].includes(row.status)) continue;
    let h = s.homeScore;
    let a = s.awayScore;
    const known = row.status === "live" && row.home_score !== null && row.away_score !== null;
    // Deux sources peuvent se croiser : un score ne recule pas (sauf fin de match, réglée à part).
    if (known && h + a < row.home_score! + row.away_score!) {
      h = row.home_score!;
      a = row.away_score!;
    }
    if (known && (h !== row.home_score || a !== row.away_score) && row.odds_at !== null) voidSince.run(s.id, row.odds_at);
    fresh.run(now, h, a, s.ttl ?? null, now, s.id, now);
    // Informations facultatives de la source, gardées pour le prochain pas du moteur.
    const sim = row.sim ? (JSON.parse(row.sim) as EngineSim) : fit(s.id, row.sport, row.odds_at ?? 0, null);
    if (sim) {
      if (s.progress !== undefined) sim.srcProgress = s.progress;
      if (s.clock) sim.srcClock = s.clock;
      if (s.red) sim.red = s.red;
      if (s.minute !== undefined) {
        sim.srcMinute = s.minute;
        sim.srcPeriod = s.period;
        sim.srcPaused = !!s.paused;
        sim.srcAt = now;
      }
      setSim.run(JSON.stringify(sim), s.id);
    }
  }
});

/** Un pas du moteur : recalcule les cotes de tous les vrais matchs en cours. Renvoie le nombre de matchs cotés. */
export const tickEngine = db.transaction((now = Date.now()): number => {
  const rows = db
    .query(
      `SELECT id, sport, feed_key, starts_at, status, home_score, away_score, sim, odds_at, detail, suspended_until
       FROM events WHERE virtual = 0 AND status IN ('scheduled', 'live') AND starts_at <= ? AND starts_at > ?`,
    )
    .all(now, now - 6 * 3_600_000) as Row[];
  const update = db.query(
    `UPDATE events SET status = 'live', clock = ?, sim = ?, detail = ?, suspended_until = ?, updated_at = ? WHERE id = ?`,
  );
  const closeOne = db.query("UPDATE selections SET price = NULL WHERE event_id = ? AND key = ?");
  const set = upsertSel();
  let priced = 0;
  for (const row of rows) {
    if (!ENGINE_SPORTS.has(row.sport)) continue;
    let sim = row.sim ? (JSON.parse(row.sim) as EngineSim) : null;
    if (!sim || (!sim.live && !sim.rated && sim.fitAt < (row.odds_at ?? 0))) {
      // Coup d'envoi : dernier calage sur les cotes d'avant-match (on garde ce que la source a déjà dit).
      const prev = sim;
      sim = fit(row.id, row.sport, row.odds_at ?? row.starts_at, sim);
      if (!sim) continue;
      if (prev)
        for (const k of ["red", "srcProgress", "srcClock", "srcMinute", "srcPeriod", "srcPaused", "srcAt"] as const)
          (sim as any)[k] = prev[k];
    }
    // Première mise à jour du match : les buts déjà marqués ont eu lieu à une minute inconnue.
    const firstTick = !sim.live;
    sim.live = true;
    const model = MODELS[row.sport];
    const clock = liveClock(sim, row.starts_at, row.feed_key, now);
    sim.t = Math.max(sim.t, clock.progress * model.len);
    const h = row.home_score ?? 0;
    const a = row.away_score ?? 0;
    const detail = row.detail ? JSON.parse(row.detail) : { timeline: [] };
    const scored = !firstTick && (h !== sim.h || a !== sim.a);
    if (scored && TIMELINE_SPORTS.has(row.sport)) {
      const label = clock.label.startsWith("≈") || /^\d/.test(clock.label) ? clock.label : `≈ ${clock.label}`;
      for (let i = sim.h; i < h; i++) detail.timeline.push({ t: label, side: "home", kind: "goal" });
      for (let i = sim.a; i < a; i++) detail.timeline.push({ t: label, side: "away", kind: "goal" });
    }
    sim.h = h;
    sim.a = a;
    const suspended = scored ? now + SUSPEND_MS : row.suspended_until;
    update.run(clock.label, JSON.stringify(sim), JSON.stringify(detail), suspended, now, row.id);
    // Toutes les cotes du match sont désormais celles du moteur.
    const probs = engineProbs(sim);
    const keep = new Set(probs.keys());
    const stale = db.query("SELECT key FROM selections WHERE event_id = ? AND price IS NOT NULL").all(row.id) as { key: string }[];
    for (const { key } of stale) if (!keep.has(key)) closeOne.run(row.id, key);
    for (const [key, raw] of probs) {
      const p = Math.min(1, Math.max(0, raw));
      set.run(row.id, key, priceOf(key, Math.min(0.999, p * LIVE_EXTRA_MARGIN)), p);
    }
    priced++;
  }
  return priced;
});

/** Compétitions ayant un vrai match en cours que le moteur sait coter. */
export function engineFeedKeys(now = Date.now()): string[] {
  const sports = [...ENGINE_SPORTS];
  return (
    db
      .query(
        `SELECT DISTINCT feed_key FROM events
         WHERE virtual = 0 AND feed_key IS NOT NULL AND feed_key NOT LIKE 'af:%'
         AND status IN ('scheduled', 'live') AND starts_at <= ? AND starts_at > ?
         AND sport IN (${sports.map(() => "?").join(",")})`,
      )
      .all(now, now - 6 * 3_600_000, ...sports) as { feed_key: string }[]
  ).map((r) => r.feed_key);
}

/* =========================================================
   Cotes maison d'avant-match (notre classement des équipes)
   ========================================================= */
/** Marge des cotes calculées sans bookmaker : un peu plus large, notre classement est moins sûr. */
const RATED_MARGIN = 1.04;

/** Modèle de football réglé directement sur des buts attendus. */
export function ratedSim(lh: number, la: number, now = Date.now()): EngineSim {
  const sim = MODELS.football.create(0);
  sim.p.lh = lh;
  sim.p.la = la;
  return { ...sim, twoWay: false, fitAt: now, own: [], rated: true };
}

/** Écrit les cotes d'avant-match d'un match coté par notre classement (tous les marchés du modèle). */
export const writeRatedOdds = db.transaction((eventId: string, sim: EngineSim) => {
  const set = upsertSel();
  db.query("UPDATE selections SET price = NULL WHERE event_id = ?").run(eventId);
  for (const [key, p] of engineProbs(sim)) set.run(eventId, key, priceOf(key, Math.min(0.999, p * RATED_MARGIN)), p);
  db.query("UPDATE events SET sim = ? WHERE id = ?").run(JSON.stringify(sim), eventId);
});
