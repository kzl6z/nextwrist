// Calcule le taux de redistribution (RTP) théorique de la machine à sous.
import { SYMBOLS, slotMultiplier } from "../src/games/slots";

const total = SYMBOLS.reduce((s, [, w]) => s + w, 0);
let rtp = 0;
for (const [a, wa] of SYMBOLS)
  for (const [b, wb] of SYMBOLS)
    for (const [c, wc] of SYMBOLS) rtp += ((wa * wb * wc) / total ** 3) * slotMultiplier([a, b, c]);
console.log(`Machine à sous : RTP ${(rtp * 100).toFixed(2)} %`);
console.log(`Roulette européenne : RTP ${((36 / 37) * 100).toFixed(2)} %`);

// Crash : simulation d'un joueur qui encaisse toujours à ×2.
import { drawCrashPoint } from "../src/games/crash";
const N = 1_000_000;
let paid = 0;
for (let i = 0; i < N; i++) if (drawCrashPoint() > 2) paid += 2;
console.log(`Crash (encaissement à ×2, ${N.toLocaleString("fr-FR")} manches) : RTP ${((paid / N) * 100).toFixed(2)} %`);
