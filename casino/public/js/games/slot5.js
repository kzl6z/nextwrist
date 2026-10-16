/* Nuit dorée : machine à sous 5 rouleaux, 3 rangées, 10 lignes */
import { $, $$, api, fmt, mult, onSpace, readStake, setBalance, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { SLOT5_SYMBOLS } from "../icons.js";

const SYMS = ["10", "J", "Q", "K", "A", "bell", "crown", "gem", "W", "S"];
const PAYS = {
  W: [250, 1250, 5000],
  gem: [120, 500, 2000],
  crown: [75, 300, 1000],
  bell: [50, 200, 600],
  A: [25, 80, 250],
  K: [20, 60, 180],
  Q: [16, 45, 140],
  J: [15, 35, 110],
  10: [15, 30, 100],
};
const LINES = [
  [1, 1, 1, 1, 1],
  [0, 0, 0, 0, 0],
  [2, 2, 2, 2, 2],
  [0, 1, 2, 1, 0],
  [2, 1, 0, 1, 2],
  [0, 0, 1, 2, 2],
  [2, 2, 1, 0, 0],
  [1, 0, 0, 0, 1],
  [1, 2, 2, 2, 1],
  [0, 1, 1, 1, 0],
];
const LINE_COLORS = ["#e2c88f", "#8cc49a", "#d9776a", "#7fa6d6", "#c39be0", "#e0b070", "#6fc3c0", "#e39ab5", "#b7c46a", "#ece6d6"];
const s5 = { bet: 100, busy: false, grid: [["A", "W", "K"], ["gem", "Q", "S"], ["10", "crown", "J"], ["bell", "A", "Q"], ["K", "J", "gem"]] };
const cellHtml = (s) => `<div class="s5-sym" data-s="${s}">${SLOT5_SYMBOLS[s]}</div>`;
const rand = () => SYMS[Math.floor(Math.random() * SYMS.length)];

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "slot5",
    controls: `
      <div><div class="label">Mise totale (10 lignes)</div>${stakeInput("s5-bet", s5.bet)}</div>
      <div class="info-list" id="s5-info"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="s5-spin">Lancer</button><p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="s5-machine">
        <div class="s5-frame">
          <div class="s5-reels" id="s5-reels">${s5.grid.map((col) => `<div class="s5-reel"><div class="s5-strip">${col.map(cellHtml).join("")}</div></div>`).join("")}</div>
          <svg class="s5-lines" id="s5-lines" viewBox="0 0 500 300" preserveAspectRatio="none" aria-hidden="true"></svg>
        </div>
        <div class="result-line" id="s5-result"></div>
        <div class="s5-pays">
          ${Object.entries(PAYS)
            .map(([k, p]) => `<div class="s5-pay" data-pay="${k}"><span class="s5-pay-sym">${SLOT5_SYMBOLS[k]}</span><span><i>5</i><b>${fmt(p[2])}</b></span><span><i>4</i><b>${fmt(p[1])}</b></span><span><i>3</i><b>${fmt(p[0])}</b></span></div>`)
            .join("")}
          <div class="s5-pay scatter" data-pay="S"><span class="s5-pay-sym">${SLOT5_SYMBOLS.S}</span><span><i>5</i><b>×100</b></span><span><i>4</i><b>×20</b></span><span><i>3</i><b>×4</b></span></div>
        </div>
      </div>`,
    rules: `<p>La mise totale est répartie sur dix lignes (une part par ligne). Une ligne paie quand au moins trois symboles identiques s'alignent depuis le rouleau de gauche. Les gains de ligne sont exprimés en multiples de la mise par ligne.</p>
      <p>Le joker <b>W</b> remplace tous les symboles sauf la lune, et paie lui-même jusqu'à 5 000 fois la mise par ligne. Trois lunes ou plus, n'importe où, paient 4, 20 ou 100 fois la mise totale.</p>`,
  });
  $("#s5-bet").step = "10";
  $("#s5-bet").min = "10";
  $("#s5-bet").addEventListener("input", (e) => {
    s5.bet = e.target.value;
    paintInfo();
  });
  $("#s5-spin").addEventListener("click", spin);
  onSpace(spin);
  paintInfo();
}

function paintInfo() {
  const bet = Math.floor(Number(s5.bet)) || 0;
  $("#s5-info").innerHTML = `<div><span>Mise par ligne</span><b>${bet % 10 === 0 && bet ? fmt(bet / 10) : "—"}</b></div><div><span>Lignes</span><b>10</b></div>`;
}

function spinReel(reel, final, rowH, duration) {
  return new Promise((resolve) => {
    const strip = reel.querySelector(".s5-strip");
    const current = [...strip.children].slice(0, 3).map((c) => c.dataset.s);
    const filler = Array.from({ length: 12 + Math.round(duration / 110) }, rand);
    const seq = [...current, ...filler, ...final];
    strip.style.transition = "none";
    strip.style.transform = "translateY(0)";
    strip.innerHTML = seq.map(cellHtml).join("");
    void strip.offsetHeight;
    reel.classList.add("spinning");
    strip.style.transition = `transform ${duration}ms cubic-bezier(.14,.8,.22,1)`;
    strip.style.transform = `translateY(-${(seq.length - 3) * rowH}px)`;
    setTimeout(() => reel.classList.remove("spinning"), duration - 260);
    setTimeout(() => {
      strip.style.transition = "none";
      strip.style.transform = "translateY(0)";
      strip.innerHTML = final.map(cellHtml).join("");
      resolve();
    }, duration + 40);
  });
}

async function spin() {
  if (s5.busy) return;
  const bet = readStake("s5-bet");
  if (!bet) return;
  if (bet % 10) return toast("La mise totale doit être un multiple de 10 (une part par ligne)", "error");
  s5.busy = true;
  $("#s5-spin").disabled = true;
  banner($("#s5-result"), "");
  $("#s5-lines").innerHTML = "";
  $$("#s5-reels .s5-sym").forEach((c) => c.classList.remove("win"));
  $$(".s5-pay").forEach((p) => p.classList.remove("on"));
  try {
    const r = await api("slot5", { bet });
    setBalance(r.balance - r.payout);
    const reels = $$("#s5-reels .s5-reel");
    const rowH = reels[0].querySelector(".s5-sym").offsetHeight;
    await Promise.all(reels.map((reel, i) => spinReel(reel, r.grid[i], rowH, 900 + i * 260)));
    s5.grid = r.grid;
    if (state.page !== "slot5") return;
    setBalance(r.balance);
    // Lignes gagnantes et symboles concernés.
    const cells = reels.map((reel) => [...reel.querySelectorAll(".s5-sym")]);
    $("#s5-lines").innerHTML = r.wins
      .map(({ line, count }) => {
        const pts = LINES[line].map((row, reel) => `${50 + reel * 100},${50 + row * 100}`).join(" ");
        LINES[line].slice(0, count).forEach((row, reel) => cells[reel][row].classList.add("win"));
        return `<polyline points="${pts}" stroke="${LINE_COLORS[line]}"/>`;
      })
      .join("");
    if (r.scatters >= 3) cells.forEach((col) => col.forEach((c) => c.dataset.s === "S" && c.classList.add("win")));
    r.wins.forEach((w) => $(`.s5-pay[data-pay="${w.symbol}"]`)?.classList.add("on"));
    if (r.scatterWin) $('.s5-pay[data-pay="S"]').classList.add("on");
    const m = r.payout / bet;
    if (r.payout > 0) {
      const parts = [];
      if (r.wins.length) parts.push(`${r.wins.length} ligne${r.wins.length > 1 ? "s" : ""}`);
      if (r.scatterWin) parts.push(`${r.scatters} lunes`);
      banner($("#s5-result"), `<b>+${fmt(r.payout)}</b> jetons, ${mult(m)} · ${parts.join(" + ")}`, r.payout >= bet ? "win" : "");
      if (m >= 10) flare();
    } else banner($("#s5-result"), "Pas de combinaison gagnante", "lose");
    refreshHistory("slot5");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    s5.busy = false;
    if (state.page === "slot5") $("#s5-spin").disabled = false;
  }
}

gamePage("slot5", render);
