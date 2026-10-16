// Outils de probabilité pour coter les matchs (lois discrètes sur un score).
import { randomFloat } from "../rng";

/** Loi discrète : p[i] = P(X = lo + i). */
export interface Dist {
  lo: number;
  p: Float64Array;
}

const LOG_FACT: number[] = [0];
function logFact(n: number): number {
  for (let i = LOG_FACT.length; i <= n; i++) LOG_FACT[i] = LOG_FACT[i - 1]! + Math.log(i);
  return LOG_FACT[n]!;
}

export const point = (v = 0): Dist => ({ lo: v, p: Float64Array.of(1) });

/** Loi de Poisson tronquée là où la masse devient négligeable. */
export function poisson(lambda: number): Dist {
  if (!(lambda > 1e-9)) return point(0);
  const sd = Math.sqrt(lambda);
  const lo = Math.max(0, Math.floor(lambda - 8 * sd - 2));
  const hi = Math.ceil(lambda + 8 * sd + 6);
  const p = new Float64Array(hi - lo + 1);
  let total = 0;
  for (let k = lo; k <= hi; k++) {
    const v = Math.exp(k * Math.log(lambda) - lambda - logFact(k));
    p[k - lo] = v;
    total += v;
  }
  for (let i = 0; i < p.length; i++) p[i]! /= total;
  return trim({ lo, p });
}

/** Retire les queues de probabilité négligeable. */
export function trim(d: Dist, eps = 1e-12): Dist {
  let a = 0;
  let b = d.p.length - 1;
  while (a < b && d.p[a]! < eps) a++;
  while (b > a && d.p[b]! < eps) b--;
  return { lo: d.lo + a, p: d.p.slice(a, b + 1) };
}

export const shift = (d: Dist, n: number): Dist => ({ lo: d.lo + n, p: d.p });

/** Loi de la somme de deux variables indépendantes. */
export function convolve(a: Dist, b: Dist): Dist {
  const p = new Float64Array(a.p.length + b.p.length - 1);
  for (let i = 0; i < a.p.length; i++) {
    const x = a.p[i]!;
    if (x < 1e-14) continue;
    for (let j = 0; j < b.p.length; j++) p[i + j]! += x * b.p[j]!;
  }
  return trim({ lo: a.lo + b.lo, p });
}

/** Loi de k × X (X à valeurs entières). */
export function scale(d: Dist, k: number): Dist {
  const p = new Float64Array((d.lo + d.p.length - 1) * k - d.lo * k + 1);
  for (let i = 0; i < d.p.length; i++) p[i * k] = d.p[i]!;
  return { lo: d.lo * k, p };
}

/**
 * Points marqués au rugby sur la durée restante : essais (5 pts, transformés
 * à 2 pts avec la probabilité `conv`) et pénalités (3 pts), chacun poissonnien.
 */
export function rugbyPoints(tries: number, pens: number, conv: number): Dist {
  const T = poisson(tries);
  const maxT = T.lo + T.p.length - 1;
  const p = new Float64Array(maxT * 7 + 1);
  for (let i = 0; i < T.p.length; i++) {
    const t = T.lo + i;
    const pt = T.p[i]!;
    if (pt < 1e-14) continue;
    // Binomiale(t, conv) pour les transformations.
    let c = Math.pow(1 - conv, t);
    for (let k = 0; k <= t; k++) {
      p[5 * t + 2 * k]! += pt * c;
      c = k < t ? (c * (t - k) * conv) / ((k + 1) * (1 - conv)) : 0;
    }
  }
  return convolve(trim({ lo: 0, p }), scale(poisson(pens), 3));
}

/** Tirage poissonnien (pour de petites espérances, comme un pas de simulation). */
export function samplePoisson(lambda: number): number {
  if (!(lambda > 0)) return 0;
  if (lambda > 30) {
    // Approximation normale pour les grandes espérances.
    const u = Math.max(1e-12, randomFloat());
    const v = randomFloat();
    const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    return Math.max(0, Math.round(lambda + z * Math.sqrt(lambda)));
  }
  const limit = Math.exp(-lambda);
  let k = 0;
  let prod = randomFloat();
  while (prod > limit) {
    k++;
    prod *= randomFloat();
  }
  return k;
}

export const chance = (p: number) => randomFloat() < p;
