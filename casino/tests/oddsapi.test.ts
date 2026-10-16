// Lecture du flux The Odds API (réponse simulée, aucun appel réseau).
import { afterEach, expect, test } from "bun:test";
import { fetchOdds } from "../src/sports/oddsapi";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

test("cotes moyennes, marchés dérivés et ligne la plus proposée", async () => {
  const sample = [
    {
      id: "ev1",
      sport_key: "soccer_france_ligue_one",
      sport_title: "Ligue 1 - France",
      commence_time: new Date(Date.now() + 86_400_000).toISOString(),
      home_team: "Paris Saint Germain",
      away_team: "Marseille",
      bookmakers: [
        {
          markets: [
            { key: "h2h", outcomes: [{ name: "Paris Saint Germain", price: 1.5 }, { name: "Marseille", price: 6 }, { name: "Draw", price: 4.4 }] },
            { key: "totals", outcomes: [{ name: "Over", price: 1.8, point: 2.5 }, { name: "Under", price: 2, point: 2.5 }] },
            { key: "spreads", outcomes: [{ name: "Paris Saint Germain", price: 1.9, point: -1.5 }, { name: "Marseille", price: 1.9, point: 1.5 }] },
          ],
        },
        {
          markets: [
            { key: "h2h", outcomes: [{ name: "Paris Saint Germain", price: 1.6 }, { name: "Marseille", price: 5.6 }, { name: "Draw", price: 4.2 }] },
            { key: "totals", outcomes: [{ name: "Over", price: 1.9, point: 2.5 }, { name: "Under", price: 1.9, point: 2.5 }] },
          ],
        },
        { markets: [{ key: "totals", outcomes: [{ name: "Over", price: 2.4, point: 3.5 }, { name: "Under", price: 1.5, point: 3.5 }] }] },
      ],
    },
  ];
  globalThis.fetch = (async () => new Response(JSON.stringify(sample), { headers: { "x-requests-remaining": "480" } })) as any;
  const [ev] = await fetchOdds("cle", "soccer_france_ligue_one", ["h2h", "totals", "spreads"]);
  expect(ev!.sport).toBe("football");
  expect(ev!.selections.home!.price).toBe(1.55);
  expect(ev!.selections.draw!.price).toBe(4.3);
  const p = ev!.selections;
  expect(p.home!.prob + p.draw!.prob + p.away!.prob).toBeCloseTo(1, 6);
  expect(p["dc:1X"]!.prob).toBeCloseTo(p.home!.prob + p.draw!.prob, 6);
  // La ligne 2,5 est proposée par deux bookmakers sur trois : c'est elle qui est retenue.
  expect(p["ou:2.5:over"]!.price).toBe(1.85);
  expect(p["ou:3.5:over"]).toBeUndefined();
  expect(p["ah:-1.5:home"]!.price).toBe(1.9);
  expect(p["ah:-1.5:away"]!.price).toBe(1.9);
});
