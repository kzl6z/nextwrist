// Modèles des sports virtuels : chaque sport sait se coter (probabilités de tous
// ses pronostics, à n'importe quel moment du match) et se jouer pas à pas.
import { randomFloat, randomInt } from "../rng";
import { scorePredicate, type Detail } from "./markets";
import { chance, poisson, rugbyPoints, samplePoisson, shift, type Dist } from "./prob";

export type SportId = "football" | "basketball" | "tennis" | "rugby" | "hockey" | "mma";

export interface Sim {
  sport: SportId;
  /** Temps de jeu écoulé (minutes de jeu ; jeux disputés pour le tennis). */
  t: number;
  /** Fin prévue (minutes de jeu), repoussée par les prolongations au basket. */
  end: number;
  h: number;
  a: number;
  p: Record<string, number>;
  lines: Record<string, number[]>;
  timeline: NonNullable<Detail["timeline"]>;
  ht?: [number, number];
  q?: [number, number][];
  sets?: [number, number][];
  cur?: [number, number];
  games?: number;
  acc?: number;
  method?: "fin" | "dec";
  round?: number;
  done?: boolean;
}

export interface Model {
  /** Durée nominale, en unités de jeu, calée sur la durée réelle d'un match virtuel. */
  len: number;
  create(d: number): Sim;
  advance(s: Sim, dt: number): boolean;
  probs(s: Sim): Map<string, number>;
  clock(s: Sim): string;
}

const half = (x: number) => Math.round(x - 0.5) + 0.5;
const minute = (t: number) => `${Math.max(1, Math.ceil(t))}'`;
const result3 = (prefix: string) => [`${prefix}home`, `${prefix}draw`, `${prefix}away`];

/* ---------- Cotation générique à partir de deux lois de score indépendantes ---------- */

type KeyClass = "diff" | "sum" | "h" | "a" | "joint";
function classOf(key: string): KeyClass {
  const m = key.split(":")[0]!;
  if (["home", "draw", "away", "dc", "ah", "mg"].includes(m)) return "diff";
  if (m === "ou" || m === "oe") return "sum";
  if (m === "th") return "h";
  if (m === "ta") return "a";
  return "joint";
}

/** Probabilités des pronostics qui ne dépendent que du score final. */
export function scoreProbs(H: Dist, A: Dist, keys: string[], tieShare?: number): Map<string, number> {
  const dMin = H.lo - (A.lo + A.p.length - 1);
  const diff = new Float64Array(H.p.length + A.p.length - 1);
  const sum = new Float64Array(H.p.length + A.p.length - 1);
  const joint = keys.filter((k) => classOf(k) === "joint").map((k) => [k, scorePredicate(k)!] as const);
  const jointAcc = new Float64Array(joint.length);
  for (let i = 0; i < H.p.length; i++) {
    const ph = H.p[i]!;
    if (ph < 1e-13) continue;
    const h = H.lo + i;
    for (let j = 0; j < A.p.length; j++) {
      const w = ph * A.p[j]!;
      if (w < 1e-15) continue;
      const a = A.lo + j;
      diff[h - a - dMin]! += w;
      sum[i + j]! += w;
      for (let k = 0; k < joint.length; k++) if (joint[k]![1](h, a)) jointAcc[k]! += w;
    }
  }
  const out = new Map<string, number>();
  joint.forEach(([k], i) => out.set(k, jointAcc[i]!));
  const over = (dist: Float64Array, lo: number, pred: (v: number) => boolean) => {
    let s = 0;
    for (let i = 0; i < dist.length; i++) if (dist[i]! > 0 && pred(lo + i)) s += dist[i]!;
    return s;
  };
  const tie = diff[-dMin] ?? 0;
  for (const k of keys) {
    const cls = classOf(k);
    if (cls === "joint") continue;
    const pred = scorePredicate(k)!;
    let p =
      cls === "diff"
        ? over(diff, dMin, (d) => pred(d, 0))
        : cls === "sum"
          ? over(sum, H.lo + A.lo, (s) => pred(s, 0))
          : cls === "h"
            ? over(H.p, H.lo, (v) => pred(v, 0))
            : over(A.p, A.lo, (v) => pred(0, v));
    // Sans match nul possible (prolongation), l'égalité est répartie entre les deux.
    if (tieShare !== undefined && (k === "home" || k === "away")) p += tie * (k === "home" ? tieShare : 1 - tieShare);
    if (tieShare !== undefined && k.startsWith("mg:") && Number(k.split(":")[2]) <= 1)
      p += tie * (k.startsWith("mg:h") ? tieShare : 1 - tieShare);
    out.set(k, p);
  }
  // Remboursé si nul : probabilité conditionnelle à l'absence de nul.
  if (out.has("draw")) {
    const ph = out.get("home")!;
    const pa = out.get("away")!;
    if (ph + pa > 1e-9) {
      out.set("dnb:home", ph / (ph + pa));
      out.set("dnb:away", pa / (ph + pa));
    }
  }
  return out;
}

function resultProbs(H: Dist, A: Dist, prefix: string, out: Map<string, number>) {
  const r = scoreProbs(H, A, ["home", "draw", "away"]);
  for (const k of ["home", "draw", "away"]) out.set(prefix + k, r.get(k)!);
}

/** Résultat déjà connu (période terminée) : 1 pour l'issue réalisée, 0 sinon. */
function decided(out: Map<string, number>, prefix: string, h: number, a: number, draw = true) {
  out.set(`${prefix}home`, h > a ? 1 : 0);
  out.set(`${prefix}away`, a > h ? 1 : 0);
  if (draw) out.set(`${prefix}draw`, h === a ? 1 : 0);
}

const lineKeys = (m: string, lines: number[] = [], sides = ["over", "under"]) =>
  lines.flatMap((L) => sides.map((s) => `${m}:${L}:${s}`));

/* ---------- Football ---------- */
const football: Model = {
  len: 90,
  create(d) {
    const lh = 1.45 * Math.exp(0.55 * d);
    const la = 1.15 * Math.exp(-0.55 * d);
    return {
      sport: "football",
      t: 0,
      end: 90,
      h: 0,
      a: 0,
      p: { lh, la },
      lines: { ou: [0.5, 1.5, 2.5, 3.5, 4.5, 5.5], th: [0.5, 1.5, 2.5], ta: [0.5, 1.5, 2.5], ah: [-2.5, -1.5, 1.5, 2.5] },
      timeline: [],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    let scored = false;
    for (const side of ["home", "away"] as const) {
      const n = samplePoisson((side === "home" ? s.p.lh! : s.p.la!) * ((s.t - from) / 90));
      for (let i = 0; i < n; i++) {
        const at = from + randomFloat() * (s.t - from);
        if (side === "home") s.h++;
        else s.a++;
        s.timeline.push({ t: minute(at), side, kind: "goal" });
        scored = true;
      }
    }
    if (!s.ht && s.t >= 45) s.ht = [s.h, s.a];
    if (s.t >= s.end) s.done = true;
    return scored;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 90;
    const H = shift(poisson(s.p.lh! * r), s.h);
    const A = shift(poisson(s.p.la! * r), s.a);
    const cs = [];
    for (let i = 0; i <= 4; i++) for (let j = 0; j <= 4; j++) cs.push(`cs:${i}-${j}`);
    const keys = [
      ...result3(""),
      "dc:1X",
      "dc:12",
      "dc:X2",
      ...lineKeys("ou", s.lines.ou),
      ...lineKeys("th", s.lines.th),
      ...lineKeys("ta", s.lines.ta),
      ...lineKeys("ah", s.lines.ah, ["home", "away"]),
      "btts:yes",
      "btts:no",
      ...cs,
      "cs:other:4",
      "oe:odd",
      "oe:even",
    ];
    const out = scoreProbs(H, A, keys);
    if (s.ht) decided(out, "ht:", s.ht[0], s.ht[1]);
    else {
      const r1 = Math.max(0, 45 - s.t) / 90;
      resultProbs(shift(poisson(s.p.lh! * r1), s.h), shift(poisson(s.p.la! * r1), s.a), "ht:", out);
    }
    return out;
  },
  clock: (s) => (s.done ? "Terminé" : s.t >= 45 && s.t < 46 ? "Mi-temps" : minute(s.t)),
};

/* ---------- Hockey (temps réglementaire) ---------- */
const hockey: Model = {
  len: 60,
  create(d) {
    const lh = 3.05 * Math.exp(0.32 * d);
    const la = 2.75 * Math.exp(-0.32 * d);
    return {
      sport: "hockey",
      t: 0,
      end: 60,
      h: 0,
      a: 0,
      p: { lh, la },
      lines: { ou: [3.5, 4.5, 5.5, 6.5, 7.5], th: [1.5, 2.5, 3.5], ta: [1.5, 2.5, 3.5], ah: [-2.5, -1.5, 1.5, 2.5] },
      timeline: [],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    let scored = false;
    for (const side of ["home", "away"] as const) {
      const n = samplePoisson((side === "home" ? s.p.lh! : s.p.la!) * ((s.t - from) / 60));
      for (let i = 0; i < n; i++) {
        const at = from + randomFloat() * (s.t - from);
        if (side === "home") s.h++;
        else s.a++;
        s.timeline.push({ t: `P${Math.min(3, Math.floor(at / 20) + 1)} ${minute(at % 20 || 20)}`, side, kind: "goal" });
        scored = true;
      }
    }
    if (s.t >= s.end) s.done = true;
    return scored;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 60;
    const H = shift(poisson(s.p.lh! * r), s.h);
    const A = shift(poisson(s.p.la! * r), s.a);
    return scoreProbs(H, A, [
      ...result3(""),
      "dc:1X",
      "dc:12",
      "dc:X2",
      ...lineKeys("ou", s.lines.ou),
      ...lineKeys("th", s.lines.th),
      ...lineKeys("ta", s.lines.ta),
      ...lineKeys("ah", s.lines.ah, ["home", "away"]),
      "btts:yes",
      "btts:no",
      "oe:odd",
      "oe:even",
    ]);
  },
  clock: (s) => (s.done ? "Terminé" : `P${Math.min(3, Math.floor(s.t / 20) + 1)} ${minute(s.t % 20 || (s.t ? 20 : 0))}`),
};

/* ---------- Basketball (prolongations jusqu'à un vainqueur) ---------- */
const MARGIN_BANDS: [number, number][] = [
  [1, 5],
  [6, 10],
  [11, 15],
  [16, 20],
  [21, 999],
];
const basketball: Model = {
  len: 48,
  create(d) {
    const lh = 113 + 7 * d;
    const la = 110 - 7 * d;
    const total = half(lh + la);
    const hcp = half(-(lh - la));
    return {
      sport: "basketball",
      t: 0,
      end: 48,
      h: 0,
      a: 0,
      p: { lh, la },
      lines: {
        ou: [-10, -5, 0, 5, 10].map((x) => total + x),
        ah: [-6, -3, 0, 3, 6].map((x) => hcp + x),
        th: [-5, 0, 5].map((x) => half(lh) + x),
        ta: [-5, 0, 5].map((x) => half(la) + x),
      },
      timeline: [],
      q: [[0, 0]],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    const q = Math.min(Math.floor(from / 12), 3) + (from >= 48 ? Math.floor((from - 48) / 5) + 1 : 0);
    while (s.q!.length <= q) s.q!.push([0, 0]);
    const ph = samplePoisson((s.p.lh! / 48) * (s.t - from));
    const pa = samplePoisson((s.p.la! / 48) * (s.t - from));
    s.h += ph;
    s.a += pa;
    s.q![q]![0] += ph;
    s.q![q]![1] += pa;
    if (s.t >= s.end) {
      if (s.h === s.a) s.end += 5;
      else s.done = true;
    }
    return ph + pa > 0;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 48;
    const H = shift(poisson(s.p.lh! * r), s.h);
    const A = shift(poisson(s.p.la! * r), s.a);
    const mg = MARGIN_BANDS.flatMap(([lo, hi]) => [`mg:h:${lo}:${hi}`, `mg:a:${lo}:${hi}`]);
    const out = scoreProbs(
      H,
      A,
      [
        "home",
        "away",
        ...lineKeys("ou", s.lines.ou),
        ...lineKeys("ah", s.lines.ah, ["home", "away"]),
        ...lineKeys("th", s.lines.th),
        ...lineKeys("ta", s.lines.ta),
        ...mg,
        "oe:odd",
        "oe:even",
      ],
      s.p.lh! / (s.p.lh! + s.p.la!),
    );
    if (s.t >= 12) decided(out, "q1:", s.q![0]![0], s.q![0]![1]);
    else {
      const r1 = (12 - s.t) / 48;
      resultProbs(shift(poisson(s.p.lh! * r1), s.q![0]![0]), shift(poisson(s.p.la! * r1), s.q![0]![1]), "q1:", out);
    }
    return out;
  },
  clock(s) {
    if (s.done) return "Terminé";
    if (s.t >= 48) return `Prol. ${Math.max(1, Math.ceil(s.end - s.t))}'`;
    return `Q${Math.min(4, Math.floor(s.t / 12) + 1)} ${Math.max(1, Math.ceil(12 - (s.t % 12)))}'`;
  },
};

/* ---------- Rugby ---------- */
const RUGBY_BANDS: [number, number][] = [
  [1, 7],
  [8, 14],
  [15, 999],
];
const rugbyDist = (tries: number, pens: number, conv: number, r: number, cur: number) =>
  shift(rugbyPoints(tries * r, pens * r, conv), cur);
const rugby: Model = {
  len: 80,
  create(d) {
    const th = 2.7 * Math.exp(0.38 * d);
    const ta = 2.2 * Math.exp(-0.38 * d);
    const pens = 2.3;
    const conv = 0.75;
    const eh = th * (5 + 2 * conv) + pens * 3;
    const ea = ta * (5 + 2 * conv) + pens * 3;
    const total = half(eh + ea);
    const hcp = half(-(eh - ea));
    return {
      sport: "rugby",
      t: 0,
      end: 80,
      h: 0,
      a: 0,
      p: { th, ta, pens, conv },
      lines: {
        ou: [-14, -7, 0, 7, 14].map((x) => total + x),
        ah: [-10, -5, 0, 5, 10].map((x) => hcp + x),
        th: [half(eh)],
        ta: [half(ea)],
      },
      timeline: [],
    };
  },
  advance(s, dt) {
    const from = s.t;
    s.t = Math.min(s.end, s.t + dt);
    const k = (s.t - from) / 80;
    let scored = false;
    for (const side of ["home", "away"] as const) {
      const tries = samplePoisson((side === "home" ? s.p.th! : s.p.ta!) * k);
      const pens = samplePoisson(s.p.pens! * k);
      const add = (pts: number, kind: string) => {
        const at = from + randomFloat() * (s.t - from);
        if (side === "home") s.h += pts;
        else s.a += pts;
        s.timeline.push({ t: minute(at), side, kind, pts });
        scored = true;
      };
      for (let i = 0; i < tries; i++) add(chance(s.p.conv!) ? 7 : 5, "try");
      for (let i = 0; i < pens; i++) add(3, "pen");
    }
    if (!s.ht && s.t >= 40) s.ht = [s.h, s.a];
    if (s.t >= s.end) s.done = true;
    return scored;
  },
  probs(s) {
    const r = Math.max(0, s.end - s.t) / 80;
    const H = rugbyDist(s.p.th!, s.p.pens!, s.p.conv!, r, s.h);
    const A = rugbyDist(s.p.ta!, s.p.pens!, s.p.conv!, r, s.a);
    const mg = [...RUGBY_BANDS.flatMap(([lo, hi]) => [`mg:h:${lo}:${hi}`, `mg:a:${lo}:${hi}`]), "mg:d"];
    const out = scoreProbs(H, A, [
      ...result3(""),
      "dc:1X",
      "dc:12",
      "dc:X2",
      ...lineKeys("ou", s.lines.ou),
      ...lineKeys("ah", s.lines.ah, ["home", "away"]),
      ...lineKeys("th", s.lines.th),
      ...lineKeys("ta", s.lines.ta),
      ...mg,
    ]);
    if (s.ht) decided(out, "ht:", s.ht[0], s.ht[1]);
    else {
      const r1 = Math.max(0, 40 - s.t) / 80;
      resultProbs(rugbyDist(s.p.th!, s.p.pens!, s.p.conv!, r1, s.h), rugbyDist(s.p.ta!, s.p.pens!, s.p.conv!, r1, s.a), "ht:", out);
    }
    return out;
  },
  clock: (s) => (s.done ? "Terminé" : s.t >= 40 && s.t < 41 ? "Mi-temps" : minute(s.t)),
};

/* ---------- Tennis (2 sets gagnants, jeu décisif à 6-6) ---------- */
type SetDist = { h: Float64Array; a: Float64Array };
function setDist(g: number, a0: number, b0: number): SetDist {
  const memo = new Map<number, SetDist>();
  const rec = (a: number, b: number): SetDist => {
    const key = a * 16 + b;
    const hit = memo.get(key);
    if (hit) return hit;
    const res: SetDist = { h: new Float64Array(14), a: new Float64Array(14) };
    if ((a >= 6 && a - b >= 2) || a === 7) res.h[0] = 1;
    else if ((b >= 6 && b - a >= 2) || b === 7) res.a[0] = 1;
    else {
      const win = rec(a + 1, b);
      const lose = rec(a, b + 1);
      for (let k = 0; k < 13; k++) {
        res.h[k + 1] = g * win.h[k]! + (1 - g) * lose.h[k]!;
        res.a[k + 1] = g * win.a[k]! + (1 - g) * lose.a[k]!;
      }
    }
    memo.set(key, res);
    return res;
  };
  return rec(a0, b0);
}

/** Loi jointe (score en sets, jeux restants) jusqu'à la fin du match. */
function matchDist(g: number, sh: number, sa: number, cur: [number, number]): Map<string, Float64Array> {
  const out = new Map<string, Float64Array>();
  const rec = (sh: number, sa: number, cur: [number, number], weight: Float64Array, offset: number) => {
    if (sh === 2 || sa === 2) {
      const key = `${sh}-${sa}`;
      const arr = out.get(key) ?? new Float64Array(64);
      for (let i = 0; i < weight.length && i + offset < 64; i++) arr[i + offset]! += weight[i]!;
      out.set(key, arr);
      return;
    }
    const d = setDist(g, cur[0], cur[1]);
    for (const [side, dist] of [
      ["h", d.h],
      ["a", d.a],
    ] as const) {
      // Convolution du poids courant avec les jeux de ce set.
      const next = new Float64Array(weight.length + 14);
      for (let i = 0; i < weight.length; i++) {
        if (!weight[i]) continue;
        for (let k = 0; k < 14; k++) next[i + k]! += weight[i]! * dist[k]!;
      }
      if (side === "h") rec(sh + 1, sa, [0, 0], next, offset);
      else rec(sh, sa + 1, [0, 0], next, offset);
    }
  };
  rec(sh, sa, cur, Float64Array.of(1), 0);
  return out;
}

const tennis: Model = {
  len: 24,
  create(d) {
    return {
      sport: "tennis",
      t: 0,
      end: 99,
      h: 0,
      a: 0,
      p: { g: 0.5 + 0.075 * d },
      lines: { games: [19.5, 21.5, 23.5, 25.5] },
      timeline: [],
      sets: [],
      cur: [0, 0],
      games: 0,
      acc: 0,
    };
  },
  advance(s, dt) {
    s.acc! += dt;
    s.t += dt;
    let changed = false;
    while (s.acc! >= 1 && !s.done) {
      s.acc! -= 1;
      const homeWins = chance(s.p.g!);
      s.cur![homeWins ? 0 : 1]++;
      s.games!++;
      changed = true;
      const [x, y] = s.cur!;
      const setOver = (x >= 6 && x - y >= 2) || (y >= 6 && y - x >= 2) || x === 7 || y === 7;
      if (setOver) {
        s.sets!.push([x, y]);
        if (x > y) s.h++;
        else s.a++;
        s.timeline.push({ t: `Set ${s.sets!.length}`, side: x > y ? "home" : "away", kind: "set", pts: 0 });
        s.cur = [0, 0];
        if (s.h === 2 || s.a === 2) s.done = true;
      }
    }
    return changed;
  },
  probs(s) {
    const g = s.p.g!;
    const dist = matchDist(g, s.h, s.a, s.cur!);
    const out = new Map<string, number>();
    const total = (k: string) => (dist.get(k) ?? new Float64Array(0)).reduce((x: number, y: number) => x + y, 0);
    const cs = ["2-0", "2-1", "1-2", "0-2"];
    for (const k of cs) out.set(`cs:${k}`, total(k));
    const pHome = total("2-0") + total("2-1");
    out.set("home", pHome);
    out.set("away", 1 - pHome);
    out.set("ou:2.5:over", total("2-1") + total("1-2"));
    out.set("ou:2.5:under", total("2-0") + total("0-2"));
    out.set("ah:-1.5:home", total("2-0"));
    out.set("ah:-1.5:away", 1 - total("2-0"));
    out.set("ah:1.5:home", 1 - total("0-2"));
    out.set("ah:1.5:away", total("0-2"));
    // Nombre total de jeux.
    const all = new Float64Array(64);
    for (const arr of dist.values()) for (let i = 0; i < 64; i++) all[i]! += arr[i]!;
    for (const L of s.lines.games ?? []) {
      let over = 0;
      for (let i = 0; i < 64; i++) if (s.games! + i > L) over += all[i]!;
      out.set(`games:${L}:over`, over);
      out.set(`games:${L}:under`, 1 - over);
    }
    if (s.sets!.length) {
      const [x, y] = s.sets![0]!;
      out.set("s1:home", x > y ? 1 : 0);
      out.set("s1:away", x > y ? 0 : 1);
    } else {
      const d = setDist(g, s.cur![0], s.cur![1]);
      const p = d.h.reduce((x, y) => x + y, 0);
      out.set("s1:home", p);
      out.set("s1:away", 1 - p);
    }
    return out;
  },
  clock: (s) => (s.done ? "Terminé" : `Set ${s.sets!.length + 1}`),
};

/* ---------- MMA (3 rounds de 5 minutes) ---------- */
const mma: Model = {
  len: 15,
  create(d) {
    return {
      sport: "mma",
      t: 0,
      end: 15,
      h: 0,
      a: 0,
      p: {
        fh: 0.032 * Math.exp(0.55 * d),
        fa: 0.032 * Math.exp(-0.55 * d),
        dec: Math.min(0.9, Math.max(0.1, 0.5 + 0.32 * d)),
      },
      lines: {},
      timeline: [],
    };
  },
  advance(s, dt) {
    if (s.done) return false;
    const step = Math.min(dt, s.end - s.t);
    const H = s.p.fh! + s.p.fa!;
    if (chance(1 - Math.exp(-H * step))) {
      const at = s.t + randomFloat() * step;
      const homeWins = chance(s.p.fh! / H);
      s.t = at;
      s.round = Math.min(3, Math.floor(at / 5) + 1);
      s.method = "fin";
      s.done = true;
      if (homeWins) s.h = 1;
      else s.a = 1;
      const kinds = ["KO", "TKO", "Soumission"];
      s.timeline.push({ t: `R${s.round} ${mmss(at % 5)}`, side: homeWins ? "home" : "away", kind: kinds[randomInt(3)]! });
      return true;
    }
    s.t += step;
    if (s.t >= s.end) {
      const homeWins = chance(s.p.dec!);
      s.round = 3;
      s.method = "dec";
      s.done = true;
      if (homeWins) s.h = 1;
      else s.a = 1;
      s.timeline.push({ t: "Décision", side: homeWins ? "home" : "away", kind: "Décision" });
      return true;
    }
    return false;
  },
  probs(s) {
    const out = new Map<string, number>();
    if (s.done) {
      out.set("home", s.h);
      out.set("away", s.a);
      return out;
    }
    const H = s.p.fh! + s.p.fa!;
    const surv = (t: number) => Math.exp(-H * Math.max(0, t - s.t));
    const pFin = 1 - surv(15);
    const hf = (s.p.fh! / H) * pFin;
    const af = (s.p.fa! / H) * pFin;
    const dec = 1 - pFin;
    out.set("home", hf + dec * s.p.dec!);
    out.set("away", af + dec * (1 - s.p.dec!));
    out.set("fin:yes", pFin);
    out.set("fin:no", dec);
    out.set("mt:home:fin", hf);
    out.set("mt:home:dec", dec * s.p.dec!);
    out.set("mt:away:fin", af);
    out.set("mt:away:dec", dec * (1 - s.p.dec!));
    for (const r of [1, 2, 3]) out.set(`rd:${r}`, surv((r - 1) * 5) - surv(r * 5));
    return out;
  },
  clock(s) {
    if (s.done) return "Terminé";
    const round = Math.min(3, Math.floor(s.t / 5) + 1);
    return `R${round} ${mmss(s.t - (round - 1) * 5)}`;
  },
};

function mmss(minutes: number) {
  const sec = Math.floor(minutes * 60);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

export const MODELS: Record<SportId, Model> = { football, basketball, tennis, rugby, hockey, mma };

/** Détails publics d'un match (frise, mi-temps, sets…) pour l'affichage et le règlement. */
export function detailOf(s: Sim): Detail {
  return {
    timeline: s.timeline,
    ht: s.ht,
    q: s.q,
    sets: s.sets,
    cur: s.sport === "tennis" && !s.done ? s.cur : undefined,
    games: s.sport === "tennis" ? s.games : undefined,
    method: s.method,
    round: s.round,
  };
}
