/* Roulette européenne : roue animée, tapis horizontal (ordinateur) ou vertical (téléphone) */
import { $, $$, api, fmt, onLeave, onSpace, setBalance, sleep, state, toast, flare, tok } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const CHIPS = [
  [1, "#d9d2bf"],
  [5, "#9c3a30"],
  [10, "#3d5a73"],
  [25, "#2f6b4f"],
  [100, "#1d1f1e"],
  [500, "#b8955a"],
];
const COLOR_FR = { red: "rouge", black: "noir", green: "vert" };
const rl = { bets: new Map(), undo: [], chip: 10, rot: 0, spinning: false, history: [], last: null };
const numColor = (n) => (n === 0 ? "green" : RED.has(n) ? "red" : "black");
const total = () => [...rl.bets.values()].reduce((s, b) => s + b.amount, 0);
const chipColor = (amount) => CHIPS.reduce((c, [v, col]) => (amount >= v ? col : c), CHIPS[0][1]);
const shortAmt = (n) => (n >= 1000 ? `${Math.round(n / 100) / 10}k`.replace(".", ",") : String(n));
const MOBILE = matchMedia("(max-width: 860px)");

function wheelSvg() {
  const c = 160;
  const R = 150;
  const r0 = 106;
  const seg = 360 / 37;
  const xy = (rad, deg) => {
    const a = (deg * Math.PI) / 180;
    return [(c + rad * Math.sin(a)).toFixed(2), (c - rad * Math.cos(a)).toFixed(2)];
  };
  const pt = (rad, deg) => xy(rad, deg).join(" ");
  const sectors = WHEEL.map((n, i) => {
    const a0 = i * seg - seg / 2;
    const a1 = i * seg + seg / 2;
    const fill = n === 0 ? "#1d6b4c" : RED.has(n) ? "#8e2b23" : "#141615";
    return `<path d="M${pt(R, a0)}A${R} ${R} 0 0 1 ${pt(R, a1)}L${pt(r0, a1)}A${r0} ${r0} 0 0 0 ${pt(r0, a0)}Z" fill="${fill}" stroke="#b8955a" stroke-width=".5"/>`;
  }).join("");
  const labels = WHEEL.map(
    (n, i) =>
      `<text x="${c}" y="${c - 134}" transform="rotate(${(i * seg).toFixed(2)} ${c} ${c})" text-anchor="middle" dominant-baseline="middle" font-size="11.5" font-weight="500" fill="#ece6d6" font-family="Bodoni Moda Variable, serif">${n}</text>`,
  ).join("");
  const spokes = [0, 45, 90, 135]
    .map((a) => {
      const [x1, y1] = xy(r0 - 6, a);
      const [x2, y2] = xy(r0 - 6, a + 180);
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#b8955a" stroke-width="2.5" stroke-linecap="round" opacity=".75"/>`;
    })
    .join("");
  return `<svg viewBox="0 0 320 320" aria-hidden="true">
    <defs><radialGradient id="rl-cone" cx="45%" cy="40%" r="70%"><stop offset="0%" stop-color="#262a27"/><stop offset="100%" stop-color="#090a09"/></radialGradient></defs>
    <circle cx="${c}" cy="${c}" r="159" fill="#0b0c0b" stroke="#b8955a" stroke-width="1.2"/>
    <circle cx="${c}" cy="${c}" r="152" fill="none" stroke="#b8955a" stroke-width=".6" opacity=".6"/>
    ${sectors}${labels}
    <circle cx="${c}" cy="${c}" r="${r0}" fill="url(#rl-cone)" stroke="#b8955a" stroke-width="1.2"/>
    <circle cx="${c}" cy="${c}" r="${r0 - 18}" fill="none" stroke="#b8955a" stroke-width=".5" opacity=".4"/>
    ${spokes}
    <circle cx="${c}" cy="${c}" r="10" fill="#b8955a"/>
  </svg>`;
}

const OUTSIDE = [
  ["low", "1 à 18", "out"],
  ["even", "Pair", "out"],
  ["red", "Rouge", "red"],
  ["black", "Noir", "black"],
  ["odd", "Impair", "out"],
  ["high", "19 à 36", "out"],
];
const DOZENS = ["1re douzaine", "2e douzaine", "3e douzaine"];

function boardHtml(vertical = MOBILE.matches) {
  const cell = (cls, key, col, row, label) =>
    `<button class="cell ${cls}" data-key="${key}" style="grid-column:${col};grid-row:${row}" aria-label="${String(label).replace(/<[^>]+>/g, "")}">${label}</button>`;
  const cells = [];
  if (vertical) {
    cells.push(cell("green", "number:0", "3/6", 1, "0"));
    for (let row = 0; row < 12; row++)
      for (let col = 0; col < 3; col++) {
        const n = row * 3 + col + 1;
        cells.push(cell(numColor(n), `number:${n}`, col + 3, row + 2, n));
      }
    [1, 2, 3].forEach((column, i) => cells.push(cell("out", `column:${column}`, i + 3, 14, "2:1")));
    DOZENS.forEach((label, i) => cells.push(cell("out", `dozen:${i + 1}`, 2, `${2 + i * 4}/span 4`, `<span class="vlabel">${label}</span>`)));
    OUTSIDE.forEach(([key, label, cls], i) => cells.push(cell(cls, key, 1, `${2 + i * 2}/span 2`, `<span class="vlabel">${label}</span>`)));
    cells.push(`<span class="blank" style="grid-column:1/3;grid-row:1"></span><span class="blank" style="grid-column:1/3;grid-row:14"></span>`);
  } else {
    cells.push(cell("green", "number:0", 1, "1/4", "0"));
    for (let col = 0; col < 12; col++)
      for (let row = 0; row < 3; row++) {
        const n = col * 3 + (3 - row);
        cells.push(cell(numColor(n), `number:${n}`, col + 2, row + 1, n));
      }
    [3, 2, 1].forEach((column, row) => cells.push(cell("out", `column:${column}`, 14, row + 1, "2:1")));
    DOZENS.forEach((label, i) => cells.push(cell("out", `dozen:${i + 1}`, `${2 + i * 4}/span 4`, 4, label)));
    OUTSIDE.forEach(([key, label, cls], i) => cells.push(cell(cls, key, `${2 + i * 2}/span 2`, 5, label)));
    cells.push(`<span class="blank" style="grid-column:1;grid-row:4/6"></span><span class="blank" style="grid-column:14;grid-row:4/6"></span>`);
  }
  return cells.join("");
}

function render() {
  const last = rl.last;
  document.querySelector("#view").innerHTML = gameShell({
    id: "roulette",
    stageClass: "roulette-stage",
    controls: `
      <div><div class="label">Jeton</div><div class="chips-row" id="chips">${CHIPS.map(
        ([v, col]) => `<button class="chip-token ${v === rl.chip ? "active" : ""}" style="--c:${col}${v === 1 ? ";--t:#1b1b1a" : ""}" data-chip="${v}" aria-label="Jeton de ${v}">${v}</button>`,
      ).join("")}</div></div>
      <div class="rl-actions">
        <button class="btn btn-sm" id="rl-undo">Annuler</button>
        <button class="btn btn-sm" id="rl-double">Doubler</button>
        <button class="btn btn-sm" id="rl-clear">Effacer</button>
      </div>
      <div class="info-list"><div><span>Mise totale</span><b id="rl-total">0</b></div></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="rl-spin">Lancer la roue</button>
      <p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="wheel-zone">
        <div class="wheel-wrap">
          <div class="wheel-pointer"></div>
          <div class="wheel-spin" id="wheel-spin" style="transform:rotate(${rl.rot}deg)">${wheelSvg()}</div>
          <div class="wheel-center display ${last ? last.color : ""}" id="wheel-center">${last ? last.n : ""}</div>
        </div>
        <div class="wheel-side">
          <div class="result-line" id="rl-result"></div>
          <div class="label">Derniers numéros</div>
          <div class="history-nums" id="rl-history"></div>
        </div>
      </div>
      <div class="board-scroll"><div class="board-felt ${MOBILE.matches ? "vertical" : ""}" id="board">${boardHtml()}</div></div>`,
    rules: `<p>Pose tes jetons sur un numéro (payé 35 fois la mise), une douzaine ou une colonne (2 fois), ou une chance simple : rouge, noir, pair, impair, 1 à 18, 19 à 36 (1 fois).</p>
      <p>Roue européenne à un seul zéro. Le zéro fait perdre les chances simples.</p>`,
  });

  $("#chips").addEventListener("click", (e) => {
    const c = e.target.closest("[data-chip]");
    if (!c) return;
    rl.chip = Number(c.dataset.chip);
    $$("#chips .chip-token").forEach((x) => x.classList.toggle("active", x === c));
  });
  $("#board").addEventListener("click", (e) => {
    const cell = e.target.closest("[data-key]");
    if (!cell || rl.spinning) return;
    const t = total();
    if (t + rl.chip > state.balance) return toast("Solde insuffisant pour ajouter ce jeton", "error");
    if (t + rl.chip > 100_000) return toast("La mise totale est limitée à 100 000 jetons", "error");
    const key = cell.dataset.key;
    const [type, value] = key.split(":");
    const bet = rl.bets.get(key) ?? { type, value: value === undefined ? undefined : Number(value), amount: 0 };
    bet.amount += rl.chip;
    rl.bets.set(key, bet);
    rl.undo.push([key, rl.chip]);
    paintCell(cell);
    paintTotals();
  });
  $("#rl-undo").addEventListener("click", () => {
    if (rl.spinning) return;
    const last = rl.undo.pop();
    if (!last) return;
    const bet = rl.bets.get(last[0]);
    if (bet) {
      bet.amount -= last[1];
      if (bet.amount <= 0) rl.bets.delete(last[0]);
    }
    paintAll();
  });
  $("#rl-clear").addEventListener("click", () => {
    if (rl.spinning) return;
    rl.bets.clear();
    rl.undo = [];
    paintAll();
  });
  $("#rl-double").addEventListener("click", () => {
    if (rl.spinning || !rl.bets.size) return;
    const t = total();
    if (t * 2 > state.balance) return toast("Solde insuffisant pour doubler", "error");
    if (t * 2 > 100_000) return toast("La mise totale est limitée à 100 000 jetons", "error");
    for (const [key, bet] of rl.bets) {
      rl.undo.push([key, bet.amount]);
      bet.amount *= 2;
    }
    paintAll();
  });
  $("#rl-spin").addEventListener("click", spin);
  onSpace(spin);
  const onLayout = () => {
    const board = $("#board");
    board.className = `board-felt ${MOBILE.matches ? "vertical" : ""}`;
    board.innerHTML = boardHtml();
    paintAll();
  };
  MOBILE.addEventListener("change", onLayout);
  onLeave(() => MOBILE.removeEventListener("change", onLayout));
  paintAll();
  paintHistory();
}

function paintCell(cell) {
  const bet = rl.bets.get(cell.dataset.key);
  let c = cell.querySelector(".chip-on");
  if (!bet) return c?.remove();
  if (!c) {
    c = document.createElement("span");
    c.className = "chip-on";
    cell.append(c);
  }
  c.style.setProperty("--c", chipColor(bet.amount));
  c.textContent = shortAmt(bet.amount);
}
function paintAll() {
  $$("#board [data-key]").forEach(paintCell);
  paintTotals();
}
function paintTotals() {
  const t = total();
  $("#rl-total").innerHTML = tok(t);
  const btn = $("#rl-spin");
  btn.disabled = !t || rl.spinning;
  btn.textContent = rl.spinning ? "La roue tourne…" : t ? `Lancer pour ${fmt(t)} jetons` : "Pose tes jetons sur le tapis";
}
function paintHistory() {
  const el = $("#rl-history");
  if (el)
    el.innerHTML = rl.history.map((h) => `<span class="hnum ${h.color}">${h.n}</span>`).join("") || `<span class="muted">Aucun tirage pour l'instant</span>`;
}

async function spin() {
  if (rl.spinning || !rl.bets.size) return;
  rl.spinning = true;
  paintTotals();
  const res = $("#rl-result");
  banner(res, "");
  $$("#board .hit").forEach((c) => c.classList.remove("hit"));
  const center = $("#wheel-center");
  center.className = "wheel-center display";
  center.textContent = "";
  if (MOBILE.matches) $(".wheel-wrap").scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    const r = await api("roulette/spin", { bets: [...rl.bets.values()] });
    setBalance(r.balance - r.totalWin);
    const seg = 360 / 37;
    const target = (((-WHEEL.indexOf(r.number) * seg) % 360) + 360) % 360;
    const jitter = (Math.random() - 0.5) * seg * 0.6;
    rl.rot = Math.ceil(rl.rot / 360) * 360 + 360 * 6 + target + jitter;
    $("#wheel-spin").style.transform = `rotate(${rl.rot}deg)`;
    await sleep(5100);
    rl.last = { n: r.number, color: r.color };
    rl.history = [rl.last, ...rl.history].slice(0, 16);
    setBalance(r.balance);
    if (state.page !== "roulette") return;
    center.textContent = r.number;
    center.className = `wheel-center display ${r.color}`;
    paintHistory();
    refreshHistory("roulette");
    $(`#board [data-key="number:${r.number}"]`)?.classList.add("hit");
    if (r.totalWin > 0) {
      banner(res, `${r.number} ${COLOR_FR[r.color]} : <b>+${fmt(r.totalWin)}</b> jetons`, "win");
      if (r.totalWin >= r.totalBet * 10) flare();
    } else banner(res, `${r.number} ${COLOR_FR[r.color]} : pas de gain`, "lose");
  } catch (err) {
    toast(err.message, "error");
    if (state.page === "roulette") center.textContent = rl.last ? rl.last.n : "";
  } finally {
    rl.spinning = false;
    if (state.page === "roulette") paintTotals();
  }
}

gamePage("roulette", render);
