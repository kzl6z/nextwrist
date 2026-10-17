/* Fruit Frenzy : machine à sous trois rouleaux */
import { mult, $, $$, api, fmt, fmtDec, onSpace, readStake, setBalance, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { SLOT_SYMBOLS } from "../icons.js";

const SYMS = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎"];
const NAMES = { "🍒": "Cerise", "🍋": "Citron", "🍊": "Orange", "🍇": "Raisin", "🔔": "Cloche", "💎": "Diamant" };
const PAYS = [
  ["💎", 500],
  ["🔔", 100],
  ["🍇", 50],
  ["🍊", 25],
  ["🍋", 15],
  ["🍒", 8],
];
const sl = { bet: 10, last: ["🍒", "💎", "🍋"], spinning: false };
const symHtml = (s) => `<div class="sym" aria-label="${NAMES[s]}">${SLOT_SYMBOLS[s]}</div>`;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "slots",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("sl-bet", sl.bet)}</div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="sl-spin">Lancer les rouleaux</button>
      <p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="slots-machine" id="machine">
        <div class="reels" id="reels">
          ${sl.last.map((s) => `<div class="reel"><div class="strip">${symHtml(s)}</div></div>`).join("")}
          <div class="payline"></div>
        </div>
        <div class="result-line" id="sl-result"></div>
        <div class="paytable slots-pays">
          ${PAYS.map(([s, m]) => `<div class="pay-row"><span class="pay-syms">${symHtml(s)}${symHtml(s)}${symHtml(s)}</span><b>×${m}</b></div>`).join("")}
          <div class="pay-row"><span class="pay-syms">${symHtml("🍒")}${symHtml("🍒")}</span><b>×0,5</b></div>
        </div>
      </div>`,
    rules: `<p>Aligne trois symboles identiques sur la ligne centrale pour gagner ta mise multipliée selon la table. Deux cerises remboursent la moitié de la mise.</p>`,
  });
  $("#sl-bet").addEventListener("input", (e) => (sl.bet = e.target.value));
  $("#sl-spin").addEventListener("click", spin);
  onSpace(spin);
}

function spinReel(reel, final, height, duration) {
  return new Promise((resolve) => {
    const strip = reel.querySelector(".strip");
    // Symboles de défilement décoratifs : le résultat vient du serveur.
    const filler = Array.from({ length: 14 + Math.round(duration / 120) }, () => SYMS[Math.floor(Math.random() * SYMS.length)]);
    const current = sl.last[[...reel.parentNode.children].indexOf(reel)] ?? final;
    const seq = [current, ...filler, final];
    strip.style.transition = "none";
    strip.style.transform = "translateY(0)";
    strip.innerHTML = seq.map(symHtml).join("");
    void strip.offsetHeight;
    reel.classList.add("spinning");
    strip.style.transition = `transform ${duration}ms cubic-bezier(.12,.8,.22,1)`;
    strip.style.transform = `translateY(-${(seq.length - 1) * height}px)`;
    setTimeout(() => reel.classList.remove("spinning"), duration - 250);
    setTimeout(() => {
      strip.style.transition = "none";
      strip.style.transform = "translateY(0)";
      strip.innerHTML = symHtml(final);
      resolve();
    }, duration + 40);
  });
}

async function spin() {
  if (sl.spinning) return;
  const bet = readStake("sl-bet");
  if (!bet) return;
  sl.spinning = true;
  $("#sl-spin").disabled = true;
  const res = $("#sl-result");
  banner(res, "");
  $$("#reels .reel").forEach((r) => r.classList.remove("win"));
  try {
    const r = await api("slots/spin", { bet });
    setBalance(r.balance - r.win);
    const reels = $$("#reels .reel");
    const height = reels[0].querySelector(".sym").offsetHeight;
    await Promise.all(reels.map((reel, i) => spinReel(reel, r.reels[i], height, 1000 + i * 380)));
    sl.last = r.reels;
    setBalance(r.balance);
    if (state.page !== "slots") return;
    refreshHistory("slots");
    if (r.win > 0) {
      banner(res, `<b>+${fmt(r.win)}</b> jetons, ${mult(r.multiplier)}`, "win");
      const triple = r.reels.every((s) => s === r.reels[0]);
      reels.forEach((reel, i) => (triple || r.reels[i] === "🍒") && reel.classList.add("win"));
      if (r.multiplier >= 25) flare();
    } else banner(res, "Pas de combinaison gagnante", "lose");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    sl.spinning = false;
    if (state.page === "slots") $("#sl-spin").disabled = false;
  }
}

gamePage("slots", render);
