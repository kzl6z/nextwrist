// Calcule le taux de redistribution (RTP) de chaque jeu : exact quand c'est possible,
// sinon par simulation. Lancer avec : bun run check:rtp
import { drawCrashPoint } from "../src/games/crash";
import { drawLimbo, KENO, PLINKO, WHEEL } from "../src/games/instant";
import { SYMBOLS, slotMultiplier } from "../src/games/slots";
import { minesMultiplier, TOWER, towerMultiplier } from "../src/games/steps";
import { BACCARAT_PAYS, dealBaccarat } from "../src/games/tables";
import { newDeck } from "../src/games/common";
import {
  CHESTS,
  DARTS,
  DIAMOND_COLORS,
  DIAMOND_PAYS,
  diamondHand,
  DT_PAYS,
  newRace,
  placeProb,
  SCRATCH_PRIZES,
  SICBO_TOTALS,
  sicboPay,
  SLOT5_SCATTER,
  SLOT5_WEIGHTS,
  slot5LinePay,
} from "../src/games/more";
import {
  ANTE_BONUS,
  BALLOON,
  balloonMultiplier,
  CROSSING,
  crossMultiplier,
  PAIR_PLUS,
  PENALTY,
  penaltyMultiplier,
  rpsMultiplier,
  tcpCompare,
  tcpEvaluate,
  tcpQualifies,
} from "../src/games/more-steps";

const pct = (x: number) => `${(x * 100).toFixed(2).replace(".", ",")} %`;
const line = (name: string, value: string) => console.log(`${name.padEnd(46)} ${value}`);
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

/* ---------- Deuxième série de jeux ---------- */
console.log("");

// Dragon Tiger (exact, sabot de 8 jeux)
const pTie = 31 / 415;
for (const k of ["dragon", "tie"] as const) {
  const rtp = ((1 - pTie) / 2) * (DT_PAYS[k].dragon + DT_PAYS[k].tiger) + pTie * DT_PAYS[k].tie;
  line(`Dragon Tiger, ${k === "dragon" ? "dragon ou tigre" : "égalité"}`, pct(rtp));
}

// Sic Bo (exact, 216 combinaisons)
const sicbo = (type: string, value?: number) => {
  let s = 0;
  for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) for (let c = 1; c <= 6; c++) s += sicboPay(type, value, [a, b, c]);
  return s / 216;
};
line("Sic Bo, petit / grand / pair / impair", pct(sicbo("small")));
const totals = Object.keys(SICBO_TOTALS).map((t) => sicbo("total", Number(t)));
line("Sic Bo, total précis", `${pct(Math.min(...totals))} à ${pct(Math.max(...totals))}`);
line("Sic Bo, double / triple précis / tout triple", `${pct(sicbo("double", 1))} / ${pct(sicbo("triple", 1))} / ${pct(sicbo("anytriple"))}`);
line("Sic Bo, numéro simple", pct(sicbo("single", 1)));

// Diamonds (exact)
let diamonds = 0;
const nd = DIAMOND_COLORS ** 5;
for (let i = 0; i < nd; i++) {
  const gems = Array.from({ length: 5 }, (_, k) => Math.floor(i / DIAMOND_COLORS ** k) % DIAMOND_COLORS);
  diamonds += DIAMOND_PAYS.find(([h]) => h === diamondHand(gems))![2];
}
line("Diamonds", pct(diamonds / nd));

// Ticket à gratter (exact)
line("Ticket à gratter", pct(SCRATCH_PRIZES.reduce((s, [, m, p]) => s + m * p, 0)));

// Fléchettes et Coffres (exact)
const weighted = (t: [number, number][]) => t.reduce((s, [m, w]) => s + m * w, 0) / t.reduce((s, [, w]) => s + w, 0);
for (const [risk, t] of Object.entries(DARTS)) line(`Fléchettes, risque ${risk}`, pct(weighted(t)));
for (const [risk, t] of Object.entries(CHESTS)) line(`Coffres, risque ${risk}`, pct(weighted(t)));

// Course hippique (exact sur 2 000 courses tirées au hasard)
let win = 0;
let place = 0;
let bets = 0;
for (let i = 0; i < 2000; i++) {
  const card = newRace();
  const p = card.horses.map((h) => h.p);
  card.horses.forEach((h, k) => {
    win += h.p * h.win;
    place += placeProb(p, k) * h.place;
    bets++;
  });
}
line("Course hippique, gagnant", pct(win / bets));
line("Course hippique, placé", pct(place / bets));

// Nuit dorée, 5 rouleaux (exact)
const tw = SLOT5_WEIGHTS.reduce((s, [, w]) => s + w, 0);
const ns = SLOT5_WEIGHTS.length;
let lines5 = 0;
for (let a = 0; a < ns ** 5; a++) {
  let x = a;
  let prob = 1;
  const symbols: string[] = [];
  for (let r = 0; r < 5; r++) {
    const [sym, w] = SLOT5_WEIGHTS[x % ns]!;
    x = Math.floor(x / ns);
    symbols.push(sym);
    prob *= w / tw;
  }
  lines5 += prob * slot5LinePay(symbols).pay;
}
const ps = SLOT5_WEIGHTS.find(([sym]) => sym === "S")![1] / tw;
let scatter = 0;
for (let k = 3; k <= 15; k++) scatter += comb(15, k) * ps ** k * (1 - ps) ** (15 - k) * (SLOT5_SCATTER[Math.min(5, k)] ?? 0);
line("Machine à sous Nuit dorée", pct(lines5 + scatter));

// Three Card Poker : Pair Plus exact, Ante/Play par simulation (stratégie Dame-6-4)
const deck52 = newDeck().sort();
let pp = 0;
let hands = 0;
for (let i = 0; i < 52; i++)
  for (let j = i + 1; j < 52; j++)
    for (let k = j + 1; k < 52; k++) {
      const h = tcpEvaluate([deck52[i]!, deck52[j]!, deck52[k]!]).hand;
      pp += PAIR_PLUS[h] ? PAIR_PLUS[h]! + 1 : 0;
      hands++;
    }
line("Three Card Poker, Pair Plus", pct(pp / hands));
const T = 400_000;
let staked = 0;
let returned = 0;
const Q64 = [0, 12, 6, 4];
for (let i = 0; i < T; i++) {
  const d = newDeck();
  const p = tcpEvaluate([d.pop()!, d.pop()!, d.pop()!]);
  const q = tcpEvaluate([d.pop()!, d.pop()!, d.pop()!]);
  staked += 1;
  if (tcpCompare(p.score, Q64) < 0) continue; // se coucher
  staked += 1;
  returned += ANTE_BONUS[p.hand] ?? 0;
  if (!tcpQualifies(q.score)) returned += 3;
  else {
    const c = tcpCompare(p.score, q.score);
    returned += c > 0 ? 4 : c === 0 ? 2 : 0;
  }
}
line("Three Card Poker, Ante + Play (simulation)", pct(returned / staked));

// Jeux « avance ou encaisse » : encaisser après 3 étapes (exact)
for (const [mode, { p }] of Object.entries(CROSSING)) line(`Traversée ${mode}, 3 voies`, pct(p ** 3 * crossMultiplier(mode, 3)));
for (const [mode, m] of Object.entries(BALLOON)) {
  let survive = 1;
  for (let i = 0; i < 3; i++) survive *= (25 - m - i) / (25 - i);
  line(`Ballon ${mode}, 3 coups de pompe`, pct(survive * balloonMultiplier(mode, 3)));
}
for (const [mode, { keepers }] of Object.entries(PENALTY))
  line(`Penalty ${mode}, 3 buts`, pct(((5 - keepers) / 5) ** 3 * penaltyMultiplier(mode, 3)));
line("Pierre-feuille-ciseaux, 3 victoires", pct(0.5 ** 3 * rpsMultiplier(3)));
