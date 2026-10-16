import { describe, expect, test } from "bun:test";
import { grade, priceOf } from "../src/sports/markets";

const ev = (h: number, a: number, detail: object = {}, status = "finished") => ({ status, home_score: h, away_score: a, detail });

describe("règlement des pronostics", () => {
  test("résultat, double chance, remboursé si nul", () => {
    expect(grade("home", ev(2, 1))).toBe("won");
    expect(grade("draw", ev(2, 1))).toBe("lost");
    expect(grade("dc:X2", ev(1, 1))).toBe("won");
    expect(grade("dc:12", ev(1, 1))).toBe("lost");
    expect(grade("dnb:home", ev(1, 1))).toBe("void");
    expect(grade("dnb:away", ev(0, 3))).toBe("won");
  });

  test("totaux, handicaps, les deux équipes marquent", () => {
    expect(grade("ou:2.5:over", ev(2, 1))).toBe("won");
    expect(grade("ou:2.5:under", ev(2, 1))).toBe("lost");
    expect(grade("ou:3:over", ev(2, 1))).toBe("void"); // ligne entière : remboursé à égalité
    expect(grade("th:1.5:over", ev(2, 0))).toBe("won");
    expect(grade("ta:0.5:under", ev(2, 0))).toBe("won");
    expect(grade("ah:-1.5:home", ev(2, 1))).toBe("lost");
    expect(grade("ah:-1.5:away", ev(2, 1))).toBe("won");
    expect(grade("ah:1.5:home", ev(0, 1))).toBe("won");
    expect(grade("btts:yes", ev(1, 1))).toBe("won");
    expect(grade("btts:no", ev(3, 0))).toBe("won");
  });

  test("score exact, écart, parité", () => {
    expect(grade("cs:2-1", ev(2, 1))).toBe("won");
    expect(grade("cs:1-2", ev(2, 1))).toBe("lost");
    expect(grade("cs:other:4", ev(5, 0))).toBe("won");
    expect(grade("cs:other:4", ev(4, 4))).toBe("lost");
    expect(grade("mg:h:1:5", ev(101, 98))).toBe("won");
    expect(grade("mg:a:21:999", ev(80, 110))).toBe("won");
    expect(grade("mg:d", ev(12, 12))).toBe("won");
    expect(grade("oe:odd", ev(2, 1))).toBe("won");
  });

  test("marchés qui s'appuient sur le détail du match", () => {
    expect(grade("ht:draw", ev(2, 1, { ht: [0, 0] }))).toBe("won");
    expect(grade("ht:home", ev(2, 1, {}))).toBe("void"); // pas de score à la mi-temps : remboursé
    expect(grade("q1:away", ev(100, 90, { q: [[20, 25]] }))).toBe("won");
    expect(grade("s1:away", ev(2, 1, { sets: [[4, 6], [6, 3], [6, 2]] }))).toBe("won");
    expect(grade("games:21.5:over", ev(2, 1, { games: 27 }))).toBe("won");
    expect(grade("fin:yes", ev(1, 0, { method: "fin", round: 2 }))).toBe("won");
    expect(grade("mt:home:dec", ev(1, 0, { method: "fin", round: 2 }))).toBe("lost");
    expect(grade("rd:2", ev(0, 1, { method: "fin", round: 2 }))).toBe("won");
    expect(grade("rd:3", ev(0, 1, { method: "dec", round: 3 }))).toBe("lost");
  });

  test("un match annulé rembourse tout", () => {
    expect(grade("home", ev(0, 0, {}, "cancelled"))).toBe("void");
    expect(grade("cs:1-0", ev(0, 0, {}, "cancelled"))).toBe("void");
  });

  test("cotes : marge appliquée, pronostics improbables ou quasi certains fermés", () => {
    expect(priceOf("home", 0.5)).toBe(1.9);
    expect(priceOf("cs:1-0", 0.1)).toBe(9.09);
    expect(priceOf("home", 0.001)).toBeNull();
    expect(priceOf("home", 0.99)).toBeNull();
  });
});
