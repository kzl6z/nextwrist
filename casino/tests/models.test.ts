import { describe, expect, test } from "bun:test";
import { grade } from "../src/sports/markets";
import { detailOf, MODELS, type SportId } from "../src/sports/models";

const SPORTS = Object.keys(MODELS) as SportId[];

describe("modèles des sports virtuels", () => {
  for (const sport of SPORTS) {
    test(`${sport} : probabilités cohérentes avant le match`, () => {
      const m = MODELS[sport];
      for (const d of [-1, -0.4, 0, 0.5, 1]) {
        const p = m.probs(m.create(d));
        const has = (k: string) => p.has(k);
        const res = (has("draw") ? ["home", "draw", "away"] : ["home", "away"]).reduce((s, k) => s + p.get(k)!, 0);
        expect(res).toBeCloseTo(1, 6);
        // Chaque paire plus/moins somme à 1.
        for (const [k, v] of p) {
          if (k.endsWith(":over")) expect(v + p.get(k.replace(":over", ":under"))!).toBeCloseTo(1, 6);
          if (k.startsWith("ah:") && k.endsWith(":home")) expect(v + p.get(k.replace(":home", ":away"))!).toBeCloseTo(1, 6);
          expect(v).toBeGreaterThanOrEqual(-1e-9);
          expect(v).toBeLessThanOrEqual(1 + 1e-9);
        }
        const cs = [...p].filter(([k]) => k.startsWith("cs:")).reduce((s, [, v]) => s + v, 0);
        if (cs) expect(cs).toBeCloseTo(1, 6);
        const mg = [...p].filter(([k]) => k.startsWith("mg:")).reduce((s, [, v]) => s + v, 0);
        if (mg) expect(mg).toBeCloseTo(1, 4);
      }
    });

    test(`${sport} : un match joué jusqu'au bout donne des probabilités 0/1 conformes au règlement`, () => {
      const m = MODELS[sport];
      for (let run = 0; run < 40; run++) {
        const s = m.create(Math.random() * 2 - 1);
        let guard = 0;
        while (!s.done && guard++ < 10_000) m.advance(s, m.len / 200);
        expect(s.done).toBe(true);
        const p = m.probs(s);
        const ev = { status: "finished", home_score: s.h, away_score: s.a, detail: detailOf(s) };
        for (const [k, v] of p) {
          const g = grade(k, ev);
          if (g === "void") continue;
          expect([k, Math.round(v * 1e6) / 1e6]).toEqual([k, g === "won" ? 1 : 0]);
        }
      }
    });
  }
});
