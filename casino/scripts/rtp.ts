// Calcule le taux de redistribution (RTP) de chaque jeu : exact quand c'est possible,
// sinon par simulation. Lancer avec : bun run check:rtp
import { drawCrashPoint } from "../src/games/crash";
import { drawLimbo, KENO, PLINKO, WHEEL } from "../src/games/instant";
import { SYMBOLS, slotMultiplier } from "../src/games/slots";
import { minesMultiplier, TOWER, towerMultiplier } from "../src/games/steps";
import { BACCARAT_PAYS, dealBaccarat } from "../src/games/tables";
import { newDeck } from "../src/games/common";

const pct = (x: number) => `${(x * 100).toFixed(2).replace(".", ",")} %`;
const line = (name: string, value: string) => console.log(`${name.padEnd(34)} ${value}`);
const comb = (n: number, k: number) => {
  let r = 1;
  for (let i = 1; i <= k; i++) r = (r * (n - k + i)) / i;
  return r;
};

// Machine à sous (exact)
const total = SYMBOLS.reduce((s, [, w]) => s + w, 0);
let slots = 0;
for (const [a, wa] of SYMBOLS)
  for (const [b, wb] of SYMBOLS) for (const [c, wc] of SYMBOLS) slots += ((wa * wb * wc) / total ** 3) * slotMultiplier([a, b, c]);
line("Machine à sous", pct(slots));
line("Roulette européenne", pct(36 / 37));

// Dice et Limbo : 99 % par construction ; contrôle de Limbo par simulation.
line("Dice (toute cible)", pct(0.99));
const N = 1_000_000;
let limbo = 0;
for (let i = 0; i < N; i++) if (drawLimbo() >= 3) limbo += 3;
line("Limbo (cible ×3, simulation)", pct(limbo / N));
let crash = 0;
for (let i = 0; i < N; i++) if (drawCrashPoint() > 2) crash += 2;
line("Crash (encaissement à ×2, simulation)", pct(crash / N));

// Plinko (exact, loi binomiale)
for (const rows of Object.keys(PLINKO).map(Number))
  for (const [risk, table] of Object.entries(PLINKO[rows]!)) {
    const rtp = table.reduce((s, m, k) => s + (comb(rows, k) / 2 ** rows) * m, 0);
    line(`Plinko ${rows} rangées, risque ${risk}`, pct(rtp));
  }

// Roue (exact)
for (const [risk, seg] of Object.entries(WHEEL)) line(`Roue, risque ${risk}`, pct(seg.reduce((s, m) => s + m, 0) / seg.length));

// Keno (exact, loi hypergéométrique : 10 numéros tirés sur 40)
for (const [n, table] of Object.entries(KENO)) {
  const picks = Number(n);
  const rtp = table.reduce((s, m, k) => s + ((comb(picks, k) * comb(40 - picks, 10 - k)) / comb(40, 10)) * m, 0);
  line(`Keno, ${picks} numéro(s)`, pct(rtp));
}

// Mines et Tower : encaisser après k étapes (exact)
for (const mines of [1, 3, 5, 10, 24]) {
  let survive = 1;
  for (let i = 0; i < 2 && i < 25 - mines; i++) survive *= (25 - mines - i) / (25 - i);
  line(`Mines, ${mines} mine(s), 2 cases`, pct(survive * minesMultiplier(mines, Math.min(2, 25 - mines))));
}
for (const [d, { cols, traps }] of Object.entries(TOWER))
  line(`Tower ${d}, 3 étages`, pct(((cols - traps) / cols) ** 3 * towerMultiplier(d, 3)));
line("Hi-Lo (tout encaissement)", pct(0.99));
line("Pile ou face (tout encaissement)", pct(0.98));

// Baccarat (simulation)
const B = 300_000;
const ret = { player: 0, banker: 0, tie: 0 };
for (let i = 0; i < B; i++) {
  const r = dealBaccarat(newDeck(8));
  for (const k of ["player", "banker", "tie"] as const) ret[k] += BACCARAT_PAYS[k][r.winner];
}
line("Baccarat joueur (simulation)", pct(ret.player / B));
line("Baccarat banquier (simulation)", pct(ret.banker / B));
line("Baccarat égalité (simulation)", pct(ret.tie / B));
line("Video poker 9/6 (jeu optimal, théorique)", pct(0.9954));
