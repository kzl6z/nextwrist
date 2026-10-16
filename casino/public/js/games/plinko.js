/* Plinko : la bille rebondit sur les picots ; le chemin est tiré par le serveur */
import { mult, $, api, fmt, fmtDec, onLeave, onSpace, readStake, setBalance, stakeInput, state, toast, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";

const pk = { bet: 10, rows: 12, risk: "medium", table: null, balls: [], raf: 0, inFlight: 0, serverBalance: null, hits: new Map(), recent: [] };
const RISKS = [
  ["low", "Faible"],
  ["medium", "Moyen"],
  ["high", "Élevé"],
];
const STEP_MS = 115;

async function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "plinko",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("pk-bet", pk.bet)}</div>
      <div><div class="label">Risque</div><div class="seg" id="pk-risk">${RISKS.map(([k, l]) => `<button data-risk="${k}">${l}</button>`).join("")}</div></div>
      <div><div class="label">Rangées</div><div class="seg" id="pk-rows">${[8, 12, 16].map((r) => `<button data-rows="${r}">${r}</button>`).join("")}</div></div>
      <p class="hint">Tu peux lâcher plusieurs billes à la suite.</p>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="pk-drop">Lâcher une bille</button>
      <p class="hint"><kbd>Espace</kbd> pour lâcher</p>`,
    stage: `
      <div class="plinko-stage">
        <div class="dice-recent" id="pk-recent"></div>
        <canvas id="pk-canvas" aria-label="Plateau de Plinko"></canvas>
        <div class="result-line" id="pk-result"></div>
      </div>`,
    rules: `<p>La bille descend à travers les rangées de picots et rebondit à gauche ou à droite avec la même chance à chaque fois. Elle termine dans une case qui multiplie ta mise.</p>
      <p>Les bords paient le plus mais sont rarement atteints. Un risque élevé creuse l'écart entre le centre et les bords.</p>`,
  });
  $("#pk-bet").addEventListener("input", (e) => (pk.bet = e.target.value));
  $("#pk-risk").addEventListener("click", (e) => {
    const b = e.target.closest("[data-risk]");
    if (!b || pk.inFlight) return b && toast("Attends que les billes soient arrivées", "info");
    pk.risk = b.dataset.risk;
    setup();
  });
  $("#pk-rows").addEventListener("click", (e) => {
    const b = e.target.closest("[data-rows]");
    if (!b || pk.inFlight) return b && toast("Attends que les billes soient arrivées", "info");
    pk.rows = Number(b.dataset.rows);
    setup();
  });
  $("#pk-drop").addEventListener("click", drop);
  onSpace(drop);
  const onResize = () => draw();
  window.addEventListener("resize", onResize);
  onLeave(() => {
    cancelAnimationFrame(pk.raf);
    window.removeEventListener("resize", onResize);
    pk.balls = [];
    pk.inFlight = 0;
  });
  try {
    pk.config = (await casinoConfig()).plinko;
    setup();
  } catch (err) {
    toast(err.message, "error");
  }
}

function setup() {
  if (state.page !== "plinko") return;
  pk.table = pk.config[pk.rows][pk.risk];
  document.querySelectorAll("#pk-risk [data-risk]").forEach((b) => b.classList.toggle("active", b.dataset.risk === pk.risk));
  document.querySelectorAll("#pk-rows [data-rows]").forEach((b) => b.classList.toggle("active", Number(b.dataset.rows) === pk.rows));
  pk.hits.clear();
  draw();
}

/* ---------- Géométrie ---------- */
function geometry(w, h) {
  const R = pk.rows;
  const top = 26;
  const slotH = Math.max(26, Math.min(34, w / (R + 1) - 6));
  const bottom = h - slotH - 14;
  const gapY = (bottom - top) / R;
  const gapX = Math.min(gapY * 1.15, (w - 24) / (R + 2));
  const cx = w / 2;
  // Rangée i : i + 3 picots, centrés.
  const pegX = (row, k) => cx + (k - (row + 2) / 2) * gapX;
  const pegY = (row) => top + gapY * (row + 0.5);
  const slotX = (s) => cx + (s - R / 2) * gapX;
  return { R, top, gapX, gapY, cx, pegX, pegY, slotX, slotY: bottom + 8, slotH };
}

/** Position de la bille au temps t (en rangées parcourues). */
function ballPos(g, path, t) {
  const i = Math.min(Math.floor(t), g.R);
  const f = t - i;
  // Décalage horizontal (en demi-intervalles) après i rebonds.
  const off = (n) => path.slice(0, n).reduce((s, x) => s + (x ? 0.5 : -0.5), 0);
  if (i >= g.R) return { x: g.cx + off(g.R) * g.gapX, y: g.slotY + g.slotH / 2 };
  const x0 = g.cx + off(i) * g.gapX;
  const x1 = g.cx + off(i + 1) * g.gapX;
  const y0 = i === 0 ? g.top - g.gapY * 0.6 : g.pegY(i - 1) - g.gapY * 0.25;
  const y1 = g.pegY(i) - g.gapY * 0.25;
  // Petit rebond parabolique au-dessus du picot.
  const y = y0 + (y1 - y0) * f - Math.sin(Math.PI * f) * g.gapY * 0.35;
  return { x: x0 + (x1 - x0) * f, y };
}

/** Couleur d'une case : dorée, d'autant plus intense que le multiplicateur est élevé. */
function slotStyle(m) {
  if (m < 1) return { fill: "rgba(125,120,108,0.28)", ink: "rgba(236,230,214,0.7)" };
  const k = Math.min(1, Math.log10(m) / Math.log10(1000));
  const a = 0.3 + k * 0.7;
  return { fill: `rgba(201,169,106,${a.toFixed(2)})`, ink: a > 0.5 ? "#17130a" : "#ece6d6" };
}

function draw() {
  const c = $("#pk-canvas");
  if (!c || !pk.table) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (!w || !h) return;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const g = geometry(w, h);
  // Picots
  const pegR = Math.max(2, Math.min(4, g.gapX * 0.12));
  ctx.fillStyle = "rgba(236,230,214,0.78)";
  for (let r = 0; r < g.R; r++)
    for (let k = 0; k < r + 3; k++) {
      ctx.beginPath();
      ctx.arc(g.pegX(r, k), g.pegY(r), pegR, 0, Math.PI * 2);
      ctx.fill();
    }
  // Cases
  const now = performance.now();
  const sw = g.gapX - 4;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `600 ${Math.max(9, Math.min(13, sw * 0.3))}px 'Geist Variable', system-ui, sans-serif`;
  pk.table.forEach((m, s) => {
    const x = g.slotX(s);
    const hit = pk.hits.get(s);
    const bump = hit ? Math.max(0, 1 - (now - hit) / 350) : 0;
    const y = g.slotY + bump * 5;
    const st = slotStyle(m);
    ctx.fillStyle = bump ? "#e2c88f" : st.fill;
    roundRect(ctx, x - sw / 2, y, sw, g.slotH, 5);
    ctx.fill();
    ctx.fillStyle = bump ? "#17130a" : st.ink;
    ctx.fillText(mult(m).slice(1), x, y + g.slotH / 2 + 0.5);
  });
  // Billes
  for (const b of pk.balls) {
    const t = Math.min(g.R, (now - b.start) / STEP_MS);
    const p = ballPos(g, b.path, t);
    ctx.beginPath();
    ctx.arc(p.x, p.y, Math.max(4, g.gapX * 0.17), 0, Math.PI * 2);
    ctx.fillStyle = "#e2c88f";
    ctx.fill();
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function loop() {
  const now = performance.now();
  for (const b of [...pk.balls]) {
    if (now - b.start >= pk.rows * STEP_MS) {
      pk.balls.splice(pk.balls.indexOf(b), 1);
      land(b);
    }
  }
  draw();
  if (pk.balls.length || [...pk.hits.values()].some((t) => now - t < 400)) pk.raf = requestAnimationFrame(loop);
  else pk.raf = 0;
}

function land(b) {
  pk.hits.set(b.slot, performance.now());
  pk.inFlight--;
  setBalance(state.balance + b.payout);
  if (pk.inFlight === 0 && pk.serverBalance !== null) setBalance(pk.serverBalance);
  banner($("#pk-result"), b.payout >= b.bet ? `<b>+${fmt(b.payout)}</b> jetons, ${mult(b.multiplier)}` : `${mult(b.multiplier)} : ${fmt(b.payout)} jetons récupérés`, b.payout >= b.bet ? "win" : "lose");
  pk.recent = [b.multiplier, ...pk.recent].slice(0, 10);
  $("#pk-recent").innerHTML = pk.recent.map((m) => `<span class="hpill ${m >= 2 ? "high" : m >= 1 ? "mid" : "low"}">${mult(m)}</span>`).join("");
  if (b.multiplier >= 25) flare();
  if (pk.inFlight === 0) refreshHistory("plinko");
}

async function drop() {
  if (!pk.table) return;
  const bet = readStake("pk-bet");
  if (!bet) return;
  if (pk.inFlight >= 12) return toast("Douze billes au maximum en même temps", "info");
  pk.inFlight++;
  setBalance(state.balance - bet);
  try {
    const r = await api("plinko", { bet, rows: pk.rows, risk: pk.risk });
    if (state.page !== "plinko") return;
    pk.serverBalance = r.balance;
    pk.balls.push({ path: r.path, slot: r.slot, multiplier: r.multiplier, payout: r.payout, bet, start: performance.now() });
    if (!pk.raf) pk.raf = requestAnimationFrame(loop);
  } catch (err) {
    pk.inFlight--;
    setBalance(state.balance + bet);
    toast(err.message, "error");
  }
}

gamePage("plinko", render);
