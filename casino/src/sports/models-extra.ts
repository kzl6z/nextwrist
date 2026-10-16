// Sports virtuels supplémentaires : handball, baseball, football américain,
// sports en sets (volley, tennis de table, badminton, e-sport) et en manches gagnantes
// (fléchettes, snooker). Mêmes principes que models.ts : cotes calculées à tout moment
// du match, et une même clé de pronostic sert à coter et à régler.
import { randomFloat } from "../rng";
import { decided, half, lineKeys, minute, result3, resultProbs, scoreProbs, type Model, type Sim, type SportId } from "./kit";
import { chance, compoundPoints, poisson, samplePoisson, shift } from "./prob";

const bands = (list: [number, number][]) => list.flatMap(([lo, hi]) => [`mg:h:${lo}:${hi}`, `mg:a:${lo}:${hi}`]);
const around = (center: number, offsets: number[]) => offsets.map((x) => center + x);

/* =========================================================
   Handball (2 × 30 min, match nul possible)
   ========================================================= */
const handball: Model = {
  len: 60,
  create(d) {
    const lh = 28.5 * Math.exp(0.09 * d);
    const la = 26.5 * Math.exp(-0.09 * d);
    const total = half(lh + la);
    const hcp = half(-(lh - la));
    return {
      sport: "handball",
      t: 0,
      end: 60,
      h: 0,
      a: 0,
      p: { lh, la },
      lines: {
        ou: around(total, [-6, -3, 0, 3, 6]),
        ah: around(hcp, [-4, -2, 0, 2, 4]),
        th: around(half(lh), [-2, 0, 2]),
        ta: around(half(la), [-2, 0, 2]),
      },
      timeline: [],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    const gh = samplePoisson(s.p.lh! * ((s.t - from) / 60));
    const ga = samplePoisson(s.p.la! * ((s.t - from) / 60));
    s.h += gh;
    s.a += ga;
    if (!s.ht && s.t >= 30) s.ht = [s.h, s.a];
    if (s.t >= s.end) s.done = true;
    return gh + ga > 0;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 60;
    const H = shift(poisson(s.p.lh! * r), s.h);
    const A = shift(poisson(s.p.la! * r), s.a);
    const out = scoreProbs(H, A, [
      ...result3(""),
      "dc:1X",
      "dc:12",
      "dc:X2",
      ...lineKeys("ou", s.lines.ou),
      ...lineKeys("ah", s.lines.ah, ["home", "away"]),
      ...lineKeys("th", s.lines.th),
      ...lineKeys("ta", s.lines.ta),
      ...bands([
        [1, 3],
        [4, 6],
        [7, 9],
        [10, 999],
      ]),
      "mg:d",
      "oe:odd",
      "oe:even",
    ]);
    if (s.ht) decided(out, "ht:", s.ht[0], s.ht[1]);
    else {
      const r1 = Math.max(0, 30 - s.t) / 60;
      resultProbs(shift(poisson(s.p.lh! * r1), s.h), shift(poisson(s.p.la! * r1), s.a), "ht:", out);
    }
    return out;
  },
  clock: (s) => (s.done ? "Terminé" : s.t >= 30 && s.t < 31 ? "Mi-temps" : minute(s.t)),
};

/* =========================================================
   Baseball (9 manches, manches supplémentaires jusqu'à un vainqueur)
   ========================================================= */
const baseball: Model = {
  len: 9,
  create(d) {
    const lh = 4.6 * Math.exp(0.22 * d);
    const la = 4.3 * Math.exp(-0.22 * d);
    const total = half(lh + la);
    return {
      sport: "baseball",
      t: 0,
      end: 9,
      h: 0,
      a: 0,
      p: { lh, la },
      lines: {
        ou: around(total, [-2, -1, 0, 1, 2]),
        ah: [-2.5, -1.5, 1.5, 2.5],
        th: around(half(lh), [-1, 0, 1]),
        ta: around(half(la), [-1, 0, 1]),
      },
      timeline: [],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    let scored = false;
    for (const side of ["home", "away"] as const) {
      const n = samplePoisson((side === "home" ? s.p.lh! : s.p.la!) * ((s.t - from) / 9));
      if (!n) continue;
      const at = from + randomFloat() * (s.t - from);
      if (side === "home") s.h += n;
      else s.a += n;
      s.timeline.push({ t: inning(at), side, kind: "run", pts: n });
      scored = true;
    }
    if (s.t >= s.end) {
      if (s.h === s.a) s.end += 1;
      else s.done = true;
    }
    return scored;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 9;
    const H = shift(poisson(s.p.lh! * r), s.h);
    const A = shift(poisson(s.p.la! * r), s.a);
    return scoreProbs(
      H,
      A,
      [
        "home",
        "away",
        ...lineKeys("ah", s.lines.ah, ["home", "away"]),
        ...lineKeys("ou", s.lines.ou),
        ...lineKeys("th", s.lines.th),
        ...lineKeys("ta", s.lines.ta),
        "oe:odd",
        "oe:even",
      ],
      s.p.lh! / (s.p.lh! + s.p.la!),
    );
  },
  clock: (s) => (s.done ? "Terminé" : inning(s.t)),
};

function inning(t: number) {
  const n = Math.floor(t) + 1;
  return n === 1 ? "1re manche" : `${n}e manche`;
}

/* =========================================================
   Football américain (4 × 15 min, prolongation jusqu'à un vainqueur)
   ========================================================= */
const afDist = (td: number, fg: number, conv: number, r: number, cur: number) => shift(compoundPoints(td * r, 6, conv, 1, fg * r, 3), cur);
const americanfootball: Model = {
  len: 60,
  create(d) {
    const tdh = 2.7 * Math.exp(0.3 * d);
    const tda = 2.3 * Math.exp(-0.3 * d);
    const fg = 1.7;
    const conv = 0.94;
    const eh = tdh * (6 + conv) + fg * 3;
    const ea = tda * (6 + conv) + fg * 3;
    const total = half(eh + ea);
    const hcp = half(-(eh - ea));
    return {
      sport: "americanfootball",
      t: 0,
      end: 60,
      h: 0,
      a: 0,
      p: { tdh, tda, fg, conv },
      lines: {
        ou: around(total, [-7, -3, 0, 3, 7]),
        ah: around(hcp, [-7, -3, 0, 3, 7]),
        th: around(half(eh), [-3, 0, 3]),
        ta: around(half(ea), [-3, 0, 3]),
      },
      timeline: [],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    const k = (s.t - from) / 60;
    let scored = false;
    for (const side of ["home", "away"] as const) {
      const add = (pts: number, kind: string) => {
        const at = from + randomFloat() * (s.t - from);
        if (side === "home") s.h += pts;
        else s.a += pts;
        s.timeline.push({ t: quarterClock(at), side, kind, pts });
        scored = true;
      };
      for (let i = samplePoisson((side === "home" ? s.p.tdh! : s.p.tda!) * k); i > 0; i--) add(chance(s.p.conv!) ? 7 : 6, "td");
      for (let i = samplePoisson(s.p.fg! * k); i > 0; i--) add(3, "fg");
    }
    if (!s.ht && s.t >= 30) s.ht = [s.h, s.a];
    if (s.t >= s.end) {
      if (s.h === s.a) s.end += 10;
      else s.done = true;
    }
    return scored;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 60;
    const H = afDist(s.p.tdh!, s.p.fg!, s.p.conv!, r, s.h);
    const A = afDist(s.p.tda!, s.p.fg!, s.p.conv!, r, s.a);
    const out = scoreProbs(
      H,
      A,
      [
        "home",
        "away",
        ...lineKeys("ah", s.lines.ah, ["home", "away"]),
        ...lineKeys("ou", s.lines.ou),
        ...lineKeys("th", s.lines.th),
        ...lineKeys("ta", s.lines.ta),
        ...bands([
          [1, 6],
          [7, 12],
          [13, 18],
          [19, 999],
        ]),
        "oe:odd",
        "oe:even",
      ],
      s.p.tdh! / (s.p.tdh! + s.p.tda!),
    );
    if (s.ht) decided(out, "ht:", s.ht[0], s.ht[1]);
    else {
      const r1 = Math.max(0, 30 - s.t) / 60;
      resultProbs(afDist(s.p.tdh!, s.p.fg!, s.p.conv!, r1, s.h), afDist(s.p.tda!, s.p.fg!, s.p.conv!, r1, s.a), "ht:", out);
    }
    return out;
  },
  clock(s) {
    if (s.done) return "Terminé";
    return quarterClock(s.t);
  },
};

function quarterClock(t: number) {
  if (t >= 60) return `Prol. ${Math.max(1, Math.ceil(10 - ((t - 60) % 10)))}'`;
  return `Q${Math.min(4, Math.floor(t / 15) + 1)} ${Math.max(1, Math.ceil(15 - (t % 15)))}'`;
}

/* =========================================================
   Sports en sets joués point par point : volley, tennis de table, badminton, e-sport
   ========================================================= */
interface RallyRules {
  sport: SportId;
  setsToWin: number;
  /** Points pour gagner un set (2 points d'écart), et pour le set décisif. */
  target: number;
  lastTarget: number;
  /** Plafond : à ce score, le set est gagné même sans 2 points d'écart (badminton : 30). */
  cap?: number;
  /** Sensibilité de la probabilité de gagner un point au niveau des deux camps. */
  edge: number;
  /** Nombre de points attendu sur un match : cale le rythme sur la durée réelle. */
  len: number;
  unit: string;
}

/** Probabilité de gagner le set depuis le score (a, b) avec une probabilité p par point. */
export function setWin(p: number, a0: number, b0: number, T: number, cap?: number): number {
  const q = 1 - p;
  const deuce = (p * p) / (p * p + q * q);
  const memo = new Map<number, number>();
  const f = (a: number, b: number): number => {
    if (cap !== undefined && a >= cap) return 1;
    if (cap !== undefined && b >= cap) return 0;
    if (a >= T && a - b >= 2) return 1;
    if (b >= T && b - a >= 2) return 0;
    if (cap === undefined && a >= T - 1 && b >= T - 1) {
      if (a === b) return deuce;
      return a > b ? p + q * deuce : p * deuce;
    }
    const key = a * 1000 + b;
    const hit = memo.get(key);
    if (hit !== undefined) return hit;
    const v = p * f(a + 1, b) + q * f(a, b + 1);
    memo.set(key, v);
    return v;
  };
  return f(a0, b0);
}

/** Loi du score final en sets, depuis (sh, sa) avec le set en cours gagné avec la probabilité `cur`. */
function rallyMatch(r: RallyRules, p: number, sh: number, sa: number, cur: number): Map<string, number> {
  const N = r.setsToWin;
  const normal = setWin(p, 0, 0, r.target, r.cap);
  const last = setWin(p, 0, 0, r.lastTarget, r.cap);
  const out = new Map<string, number>();
  const rec = (h: number, a: number, pSet: number, w: number) => {
    if (h === N || a === N) {
      out.set(`${h}-${a}`, (out.get(`${h}-${a}`) ?? 0) + w);
      return;
    }
    const nextP = (nh: number, na: number) => (nh === N - 1 && na === N - 1 ? last : normal);
    rec(h + 1, a, nextP(h + 1, a), w * pSet);
    rec(h, a + 1, nextP(h, a + 1), w * (1 - pSet));
  };
  rec(sh, sa, cur, 1);
  return out;
}

function rallyModel(r: RallyRules): Model {
  const N = r.setsToWin;
  const totals = Array.from({ length: N - 1 }, (_, i) => N + i + 0.5);
  const hcps = Array.from({ length: N - 1 }, (_, i) => i + 1.5);
  return {
    len: r.len,
    create(d) {
      return {
        sport: r.sport,
        t: 0,
        end: 1e9,
        h: 0,
        a: 0,
        p: { p: 0.5 + r.edge * d },
        lines: {},
        timeline: [],
        sets: [],
        cur: [0, 0],
        acc: 0,
      };
    },
    advance(s, dt) {
      s.acc! += dt;
      s.t += dt;
      let changed = false;
      while (s.acc! >= 1 && !s.done) {
        s.acc! -= 1;
        s.cur![chance(s.p.p!) ? 0 : 1]++;
        changed = true;
        const [x, y] = s.cur!;
        const T = s.h === N - 1 && s.a === N - 1 ? r.lastTarget : r.target;
        const over = (x >= T || y >= T) && (Math.abs(x - y) >= 2 || (r.cap !== undefined && Math.max(x, y) >= r.cap));
        if (over) {
          s.sets!.push([x, y]);
          if (x > y) s.h++;
          else s.a++;
          s.timeline.push({ t: `${r.unit} ${s.sets!.length}`, side: x > y ? "home" : "away", kind: "set", pts: 0 });
          s.cur = [0, 0];
          if (s.h === N || s.a === N) s.done = true;
        }
      }
      return changed;
    },
    probs(s) {
      const p = s.p.p!;
      const out = new Map<string, number>();
      if (s.done) {
        out.set("home", s.h > s.a ? 1 : 0);
        out.set("away", s.h > s.a ? 0 : 1);
      }
      const T = s.h === N - 1 && s.a === N - 1 ? r.lastTarget : r.target;
      const cur = s.done ? 0 : setWin(p, s.cur![0], s.cur![1], T, r.cap);
      const dist = s.done ? new Map([[`${s.h}-${s.a}`, 1]]) : rallyMatch(r, p, s.h, s.a, cur);
      // Tous les scores possibles, même ceux devenus impossibles (probabilité 0).
      for (let k = 0; k < N; k++) {
        out.set(`cs:${N}-${k}`, dist.get(`${N}-${k}`) ?? 0);
        out.set(`cs:${k}-${N}`, dist.get(`${k}-${N}`) ?? 0);
      }
      const prob = (pred: (h: number, a: number) => boolean) =>
        [...dist].reduce((sum, [k, v]) => {
          const [h, a] = k.split("-").map(Number) as [number, number];
          return pred(h, a) ? sum + v : sum;
        }, 0);
      out.set("home", prob((h, a) => h > a));
      out.set("away", prob((h, a) => a > h));
      for (const L of totals) {
        out.set(`ou:${L}:over`, prob((h, a) => h + a > L));
        out.set(`ou:${L}:under`, prob((h, a) => h + a < L));
      }
      for (const L of hcps) {
        out.set(`ah:${-L}:home`, prob((h, a) => h - L > a));
        out.set(`ah:${-L}:away`, prob((h, a) => h - L < a));
        out.set(`ah:${L}:home`, prob((h, a) => h + L > a));
        out.set(`ah:${L}:away`, prob((h, a) => h + L < a));
      }
      if (s.sets!.length) {
        const [x, y] = s.sets![0]!;
        out.set("s1:home", x > y ? 1 : 0);
        out.set("s1:away", x > y ? 0 : 1);
      } else {
        out.set("s1:home", cur);
        out.set("s1:away", 1 - cur);
      }
      return out;
    },
    clock: (s) => (s.done ? "Terminé" : `${r.unit} ${s.sets!.length + 1}`),
  };
}

const volleyball = rallyModel({ sport: "volleyball", setsToWin: 3, target: 25, lastTarget: 15, edge: 0.035, len: 180, unit: "Set" });
const tabletennis = rallyModel({ sport: "tabletennis", setsToWin: 3, target: 11, lastTarget: 11, edge: 0.06, len: 80, unit: "Manche" });
const badminton = rallyModel({ sport: "badminton", setsToWin: 2, target: 21, lastTarget: 21, cap: 30, edge: 0.045, len: 95, unit: "Set" });
const esports = rallyModel({ sport: "esports", setsToWin: 2, target: 13, lastTarget: 13, edge: 0.05, len: 58, unit: "Carte" });

/* =========================================================
   Manches gagnantes : fléchettes (legs), snooker (frames)
   ========================================================= */
interface RaceRules {
  sport: SportId;
  target: number;
  edge: number;
  unit: string;
}

/** Loi du score final quand le premier à `N` manches gagne, depuis (h, a). */
function raceDist(p: number, N: number, h: number, a: number): Map<string, number> {
  const out = new Map<string, number>();
  const q = 1 - p;
  const comb = (n: number, k: number) => {
    let c = 1;
    for (let i = 1; i <= k; i++) c = (c * (n - k + i)) / i;
    return c;
  };
  const needH = N - h;
  const needA = N - a;
  // Le domicile gagne la dernière manche après avoir concédé j manches de plus.
  for (let j = 0; j < needA; j++) out.set(`${N}-${a + j}`, comb(needH - 1 + j, j) * p ** needH * q ** j);
  for (let j = 0; j < needH; j++) out.set(`${h + j}-${N}`, comb(needA - 1 + j, j) * q ** needA * p ** j);
  return out;
}

function raceModel(r: RaceRules): Model {
  const N = r.target;
  const mid = N + Math.floor(N / 2);
  const totals = [mid - 1.5, mid - 0.5, mid + 0.5, mid + 1.5].filter((L) => L > N && L < 2 * N - 1);
  return {
    len: N * 1.55,
    create(d) {
      return { sport: r.sport, t: 0, end: 1e9, h: 0, a: 0, p: { p: 0.5 + r.edge * d }, lines: {}, timeline: [], acc: 0 };
    },
    advance(s, dt) {
      s.acc! += dt;
      s.t += dt;
      let changed = false;
      while (s.acc! >= 1 && !s.done) {
        s.acc! -= 1;
        if (chance(s.p.p!)) s.h++;
        else s.a++;
        changed = true;
        if (s.h === N || s.a === N) s.done = true;
      }
      return changed;
    },
    probs(s) {
      const dist = s.done ? new Map([[`${s.h}-${s.a}`, 1]]) : raceDist(s.p.p!, N, s.h, s.a);
      const out = new Map<string, number>();
      for (let k = 0; k < N; k++) {
        out.set(`cs:${N}-${k}`, dist.get(`${N}-${k}`) ?? 0);
        out.set(`cs:${k}-${N}`, dist.get(`${k}-${N}`) ?? 0);
      }
      const prob = (pred: (h: number, a: number) => boolean) =>
        [...dist].reduce((sum, [k, v]) => {
          const [h, a] = k.split("-").map(Number) as [number, number];
          return pred(h, a) ? sum + v : sum;
        }, 0);
      out.set("home", prob((h, a) => h > a));
      out.set("away", prob((h, a) => a > h));
      for (const L of totals) {
        out.set(`ou:${L}:over`, prob((h, a) => h + a > L));
        out.set(`ou:${L}:under`, prob((h, a) => h + a < L));
      }
      for (const L of [1.5, 2.5]) {
        out.set(`ah:${-L}:home`, prob((h, a) => h - L > a));
        out.set(`ah:${-L}:away`, prob((h, a) => h - L < a));
        out.set(`ah:${L}:home`, prob((h, a) => h + L > a));
        out.set(`ah:${L}:away`, prob((h, a) => h + L < a));
      }
      return out;
    },
    clock: (s) => (s.done ? "Terminé" : `${r.unit} ${s.h + s.a + 1}`),
  };
}

const darts = raceModel({ sport: "darts", target: 6, edge: 0.13, unit: "Leg" });
const snooker = raceModel({ sport: "snooker", target: 5, edge: 0.12, unit: "Frame" });

export const EXTRA_MODELS = { handball, baseball, americanfootball, volleyball, tabletennis, badminton, esports, darts, snooker } satisfies Partial<
  Record<SportId, Model>
>;

export type { Sim };
