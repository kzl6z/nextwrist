/* Tower : huit étages, une case sûre à trouver par étage */
import { $, api, fmt, mult, readStake, setBalance, setStakeDisabled, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { icon } from "../icons.js";

const LEVELS = 8;
const DIFF = {
  easy: { label: "Facile", cols: 4, traps: 1 },
  medium: { label: "Moyen", cols: 3, traps: 1 },
  hard: { label: "Difficile", cols: 2, traps: 1 },
  expert: { label: "Expert", cols: 3, traps: 2 },
};
const tw = { bet: 10, difficulty: "medium", game: null, busy: false };
const ladder = (d) => Array.from({ length: LEVELS }, (_, i) => Math.floor(0.98 * (DIFF[d].cols / (DIFF[d].cols - DIFF[d].traps)) ** (i + 1) * 10_000) / 10_000);

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "tower",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("tw-bet", tw.bet)}</div>
      <div><div class="label">Difficulté</div><div class="seg seg-wrap" id="tw-diff">${Object.entries(DIFF).map(([k, d]) => `<button data-d="${k}">${d.label}</button>`).join("")}</div></div>
      <div class="info-list" id="tw-info"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="tw-main">Commencer</button>`,
    stage: `<div class="tower-stage"><div class="tower" id="tw-tower"></div><div class="result-line" id="tw-result"></div></div>`,
    rules: `<p>Monte étage par étage en choisissant une case. Chaque étage cache un ou deux pièges selon la difficulté. Une case sûre te fait monter et augmente le multiplicateur.</p>
      <p>Encaisse quand tu veux ; atteindre le sommet encaisse automatiquement.</p>`,
  });
  $("#tw-bet").addEventListener("input", (e) => (tw.bet = e.target.value));
  $("#tw-diff").addEventListener("click", (e) => {
    const b = e.target.closest("[data-d]");
    if (!b || tw.game?.status === "playing") return;
    tw.difficulty = b.dataset.d;
    tw.game = null;
    paint();
  });
  $("#tw-main").addEventListener("click", main);
  $("#tw-tower").addEventListener("click", (e) => {
    const b = e.target.closest("[data-col]");
    if (b && !b.disabled) pick(Number(b.dataset.col));
  });
  paint();
  api("tower")
    .then((d) => apply(d, false))
    .catch((err) => toast(err.message, "error"));
}

function apply(d, animate = true) {
  if (state.page !== "tower") return;
  setBalance(d.balance);
  tw.game = d.game;
  if (d.game) tw.difficulty = d.game.difficulty;
  paint(animate);
}

function paint(animate = false) {
  if (state.page !== "tower") return;
  const g = tw.game?.difficulty === tw.difficulty ? tw.game : null;
  const playing = g?.status === "playing";
  const d = DIFF[tw.difficulty];
  document.querySelectorAll("#tw-diff [data-d]").forEach((b) => {
    b.classList.toggle("active", b.dataset.d === tw.difficulty);
    b.disabled = playing;
  });
  setStakeDisabled("tw-bet", playing);
  const level = g ? g.picks.length : 0;
  const lad = g?.ladder ?? ladder(tw.difficulty);
  const btn = $("#tw-main");
  if (playing) {
    btn.className = "btn btn-win btn-lg btn-block";
    btn.disabled = !level;
    btn.textContent = level ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Choisis une case du premier étage";
  } else {
    btn.className = "btn btn-gold btn-lg btn-block";
    btn.disabled = false;
    btn.textContent = "Commencer";
  }
  $("#tw-info").innerHTML = `<div><span>Chance par étage</span><b>${Math.round(((d.cols - d.traps) / d.cols) * 100)} %</b></div><div><span>Sommet</span><b>${mult(lad[LEVELS - 1])}</b></div>`;
  const rows = [];
  for (let r = LEVELS - 1; r >= 0; r--) {
    const current = playing && r === level;
    const cells = Array.from({ length: d.cols }, (_, c) => {
      const picked = g?.picks[r] === c;
      const trap = g?.traps?.[r]?.includes(c);
      const lost = picked && (g.status === "lost" && r === g.picks.length - 1);
      let cls = "tc";
      let inner = "";
      if (picked && !lost) {
        cls += " safe";
        inner = icon("gem", { size: 22, sw: 1.6 });
      } else if (lost) {
        cls += " trap open";
        inner = icon("bomb", { size: 22, sw: 1.6 });
      } else if (g && !playing && g.traps) {
        cls += trap ? " trap ghost" : " ghost";
        inner = trap ? icon("bomb", { size: 20, sw: 1.5 }) : "";
      }
      if (current) cls += " live";
      if (animate && picked && r === g.picks.length - 1) cls += " pop";
      return `<button class="${cls}" data-col="${c}" ${current ? "" : "disabled"} aria-label="Étage ${r + 1}, case ${c + 1}">${inner}</button>`;
    }).join("");
    rows.push(`<div class="tw-row ${current ? "current" : ""} ${g && r < level ? "done" : ""}"><span class="tw-mult">${mult(lad[r])}</span><div class="tw-cells" style="--cols:${d.cols}">${cells}</div></div>`);
  }
  $("#tw-tower").innerHTML = rows.join("");
  if (g && !playing && animate) {
    if (g.status === "won") {
      banner($("#tw-result"), `<b>+${fmt(g.payout)}</b> jetons, ${mult(g.multiplier)}`, "win");
      if (g.multiplier >= 5) flare();
    } else banner($("#tw-result"), "Piège : mise perdue", "lose");
  } else if (playing) banner($("#tw-result"), level ? `Étage ${level} atteint` : "");
}

async function main() {
  if (tw.busy) return;
  const playing = tw.game?.status === "playing";
  tw.busy = true;
  try {
    if (playing) {
      if (!tw.game.picks.length) return;
      apply(await api("tower/cashout", {}));
      refreshHistory("tower");
    } else {
      const bet = readStake("tw-bet");
      if (!bet) return;
      apply(await api("tower/start", { bet, difficulty: tw.difficulty }));
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    tw.busy = false;
  }
}

async function pick(col) {
  if (tw.busy || tw.game?.status !== "playing") return;
  tw.busy = true;
  try {
    const d = await api("tower/pick", { col });
    apply(d);
    if (d.game.status !== "playing") refreshHistory("tower");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    tw.busy = false;
  }
}

gamePage("tower", render);
