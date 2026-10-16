// Catalogue des marchés : chaque pronostic est une clé texte qui se décrit elle-même,
// et la même définition sert à coter (probabilité) et à régler (gagné/perdu/remboursé).
//
//   home | draw | away            Résultat (1N2, ou vainqueur si pas de nul)
//   dc:1X | dc:12 | dc:X2         Double chance
//   dnb:home | dnb:away           Remboursé si match nul
//   ou:L:over | ou:L:under        Total (buts, points, sets) plus / moins de L
//   th:L:over|under  ta:L:…       Total de l'équipe à domicile / à l'extérieur
//   ah:L:home | ah:L:away         Handicap L appliqué à l'équipe à domicile
//   btts:yes | btts:no            Les deux équipes marquent
//   cs:H-A | cs:other:M           Score exact (other = un des côtés dépasse M)
//   oe:odd | oe:even              Total pair / impair
//   mg:h:A:B | mg:a:A:B | mg:d    Écart de victoire entre A et B (B = 999 : « et plus »)
//   ht:home|draw|away             Résultat à la mi-temps            (detail.ht)
//   q1:home|draw|away             Résultat du 1er quart-temps       (detail.q[0])
//   s1:home|away                  Vainqueur du 1er set              (detail.sets[0])
//   games:L:over|under            Nombre total de jeux (tennis)     (detail.games)
//   fin:yes | fin:no              Combat terminé avant la limite    (detail.method)
//   mt:home:fin|dec  mt:away:…    Vainqueur + méthode               (detail.method)
//   rd:N                          Fin du combat au round N          (detail.round)

export type Result = "won" | "lost" | "void";

export interface Detail {
  ht?: [number, number];
  q?: [number, number][];
  sets?: [number, number][];
  games?: number;
  method?: "fin" | "dec";
  round?: number;
  timeline?: { t: string; side: "home" | "away"; kind: string; pts?: number }[];
  [k: string]: unknown;
}

const cmp = (h: number, a: number, o: string): boolean | null =>
  o === "home" ? h > a : o === "away" ? a > h : o === "draw" ? h === a : null;

/** Prédicat sur le score final, ou null si la clé ne dépend pas que du score. */
export function scorePredicate(key: string): ((h: number, a: number) => boolean) | null {
  const [m, x, y, z] = key.split(":");
  switch (m) {
    case "home":
      return (h, a) => h > a;
    case "away":
      return (h, a) => a > h;
    case "draw":
      return (h, a) => h === a;
    case "dc":
      return x === "1X" ? (h, a) => h >= a : x === "12" ? (h, a) => h !== a : (h, a) => h <= a;
    case "ou":
    case "th":
    case "ta": {
      const L = Number(x);
      const total = m === "ou" ? (h: number, a: number) => h + a : m === "th" ? (h: number) => h : (_: number, a: number) => a;
      return y === "over" ? (h, a) => total(h, a) > L : (h, a) => total(h, a) < L;
    }
    case "ah": {
      const L = Number(x);
      return y === "home" ? (h, a) => h + L > a : (h, a) => h + L < a;
    }
    case "btts":
      return x === "yes" ? (h, a) => h > 0 && a > 0 : (h, a) => h === 0 || a === 0;
    case "cs": {
      if (x === "other") {
        const M = Number(y);
        return (h, a) => h > M || a > M;
      }
      const [sh, sa] = x!.split("-").map(Number);
      return (h, a) => h === sh && a === sa;
    }
    case "oe":
      return x === "odd" ? (h, a) => (h + a) % 2 === 1 : (h, a) => (h + a) % 2 === 0;
    case "mg": {
      if (x === "d") return (h, a) => h === a;
      const lo = Number(y);
      const hi = Number(z);
      return x === "h" ? (h, a) => h - a >= lo && h - a <= hi : (h, a) => a - h >= lo && a - h <= hi;
    }
    default:
      return null;
  }
}

/** Le pronostic peut-il être remboursé sur ce score (égalité exacte) ? */
function isPush(key: string, h: number, a: number): boolean {
  const [m, x] = key.split(":");
  if (m === "dnb") return h === a;
  if (m === "ah") return h + Number(x) === a;
  if (m === "ou") return h + a === Number(x);
  if (m === "th") return h === Number(x);
  if (m === "ta") return a === Number(x);
  return false;
}

export function grade(
  key: string,
  ev: { status: string; home_score: number | null; away_score: number | null; detail?: Detail | null },
): Result {
  if (ev.status === "cancelled") return "void";
  const h = ev.home_score ?? 0;
  const a = ev.away_score ?? 0;
  const d = ev.detail ?? {};
  const [m, x, y] = key.split(":");

  if (m === "dnb") return h === a ? "void" : cmp(h, a, x!) ? "won" : "lost";
  if (isPush(key, h, a)) return "void";

  const pred = scorePredicate(key);
  if (pred) return pred(h, a) ? "won" : "lost";

  const pair = (v: unknown): [number, number] | null =>
    Array.isArray(v) && v.length === 2 && v.every(Number.isFinite) ? (v as [number, number]) : null;
  switch (m) {
    case "ht": {
      const p = pair(d.ht);
      return p ? (cmp(p[0], p[1], x!) ? "won" : "lost") : "void";
    }
    case "q1": {
      const p = pair(d.q?.[0]);
      return p ? (cmp(p[0], p[1], x!) ? "won" : "lost") : "void";
    }
    case "s1": {
      const p = pair(d.sets?.[0]);
      return p ? (cmp(p[0], p[1], x!) ? "won" : "lost") : "void";
    }
    case "games": {
      if (!Number.isFinite(d.games)) return "void";
      const L = Number(x);
      if (d.games === L) return "void";
      return (y === "over" ? d.games! > L : d.games! < L) ? "won" : "lost";
    }
    case "fin":
      if (!d.method) return "void";
      return (x === "yes") === (d.method === "fin") ? "won" : "lost";
    case "mt":
      if (!d.method) return "void";
      return cmp(h, a, x!) && d.method === y ? "won" : "lost";
    case "rd":
      if (!d.method) return "void";
      return d.method === "fin" && d.round === Number(x) ? "won" : "lost";
  }
  return "void";
}

/** Marge appliquée selon le type de marché (les marchés exotiques sont plus margés). */
export function marginOf(key: string): number {
  const m = key.split(":")[0]!;
  return ["cs", "mg", "mt", "rd", "games"].includes(m) ? 1.1 : 1.055;
}

/** Probabilité → cote décimale, ou null si le pronostic n'est pas proposé. */
export function priceOf(key: string, p: number): number | null {
  if (!(p >= 0.004) || p > 0.965) return null;
  const raw = 1 / (p * marginOf(key));
  const price = Math.round(Math.min(250, Math.max(1.01, raw)) * 100) / 100;
  return price;
}

/** Clé du marché principal affiché dans les listes, selon le sport. */
export const MAIN_KEYS = ["home", "draw", "away"];
