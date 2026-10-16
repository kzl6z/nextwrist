// Boîte à outils commune aux modèles de sports virtuels : types, cotation à partir
// de lois de score, lignes de marchés.
import { scorePredicate, type Detail } from "./markets";
import type { Dist } from "./prob";

export type SportId =
  | "football"
  | "basketball"
  | "tennis"
  | "rugby"
  | "hockey"
  | "mma"
  | "handball"
  | "volleyball"
  | "tabletennis"
  | "badminton"
  | "darts"
  | "snooker"
  | "baseball"
  | "americanfootball"
  | "esports"
  | "boxing";

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

export const half = (x: number) => Math.round(x - 0.5) + 0.5;
export const minute = (t: number) => `${Math.max(1, Math.ceil(t))}'`;
export const result3 = (prefix: string) => [`${prefix}home`, `${prefix}draw`, `${prefix}away`];

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

export function resultProbs(H: Dist, A: Dist, prefix: string, out: Map<string, number>) {
  const r = scoreProbs(H, A, ["home", "draw", "away"]);
  for (const k of ["home", "draw", "away"]) out.set(prefix + k, r.get(k)!);
}

/** Résultat déjà connu (période terminée) : 1 pour l'issue réalisée, 0 sinon. */
export function decided(out: Map<string, number>, prefix: string, h: number, a: number, draw = true) {
  out.set(`${prefix}home`, h > a ? 1 : 0);
  out.set(`${prefix}away`, a > h ? 1 : 0);
  if (draw) out.set(`${prefix}draw`, h === a ? 1 : 0);
}

export const lineKeys = (m: string, lines: number[] = [], sides = ["over", "under"]) =>
  lines.flatMap((L) => sides.map((s) => `${m}:${L}:${s}`));

