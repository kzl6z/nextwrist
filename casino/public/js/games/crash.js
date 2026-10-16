/* Crash : courbe exponentielle, encaissement manuel ou automatique */
import { $, api, fmt, fmtDec, onLeave, onSpace, readStake, setStakeDisabled, stakeInput, state, toast, flare, tok, setBalance } from "../core.js";
import { gamePage, gameShell, refreshHistory } from "../casino.js";

const cr = { growth: 0.00006, round: null, startedLocal: 0, raf: 0, poll: 0, auto: false, autoVal: "2.00", bet: 10, redraw: null };
const crashChance = (m) => Math.min(100, 97 / (m + 0.01));

function render() {
  view();
  $("#cr-main").addEventListener("click", main);
  $("#cr-auto-toggle").addEventListener("click", (e) => {
    cr.auto = !cr.auto;
    e.currentTarget.classList.toggle("on", cr.auto);
    e.currentTarget.setAttribute("aria-checked", cr.auto);
    $("#cr-auto-box").classList.toggle("disabled", !cr.auto);
    paintInfo();
  });
  $("#cr-bet").addEventListener("input", (e) => {
    cr.bet = e.target.value;
    paintButton();
    paintInfo();
  });
  $("#cr-auto").addEventListener("input", (e) => {
    cr.autoVal = e.target.value;
    paintInfo();
  });
  onSpace(main);
  const onResize = () => cr.redraw?.();
  window.addEventListener("resize", onResize);
  onLeave(() => {
    cancelAnimationFrame(cr.raf);
    clearInterval(cr.poll);
    window.removeEventListener("resize", onResize);
  });
  paintInfo();
  api("crash")
    .then(apply)
    .catch((err) => toast(err.message, "error"));
}

function view() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "crash",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("cr-bet", cr.bet)}</div>
      <div>
        <label class="toggle-row"><span>Encaissement automatique</span><button type="button" class="switch ${cr.auto ? "on" : ""}" id="cr-auto-toggle" role="switch" aria-checked="${cr.auto}"></button></label>
        <div class="stake-input ${cr.auto ? "" : "disabled"}" id="cr-auto-box" style="margin-top:9px"><input id="cr-auto" type="number" inputmode="decimal" step="0.01" min="1.01" max="1000" value="${cr.autoVal}" aria-label="Multiplicateur d'encaissement automatique" /><span class="suffix">×</span></div>
      </div>
      <div class="info-list" id="cr-info"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="cr-main" data-mode="start">Lancer</button>
      <p class="hint"><kbd>Espace</kbd> pour lancer ou encaisser</p>`,
    stage: `
      <div class="crash-hist" id="cr-hist"></div>
      <div class="crash-stage">
        <canvas id="cr-canvas"></canvas>
        <div class="crash-mult" id="cr-mult"><b id="cr-m" class="display">1,00×</b><small id="cr-sub">Place ta mise et lance la partie</small></div>
      </div>`,
    rules: `<p>Le multiplicateur part de ×1,00 et grimpe jusqu'à ce que la courbe s'effondre, à un point tiré au hasard dès le lancement et gardé secret par le serveur.</p>
      <p>Encaisse avant l'effondrement pour gagner ta mise multipliée. Avec l'encaissement automatique, la partie s'arrête toute seule à ta cible.</p>`,
  });
}

function apply(d) {
  if (state.page !== "crash") return;
  setBalance(d.balance);
  cr.growth = d.growth;
  cr.round = d.round;
  $("#cr-hist").innerHTML =
    d.history.map((m) => `<span class="hpill ${m < 2 ? "low" : m < 10 ? "mid" : "high"}">${fmtDec(m)}×</span>`).join("") ||
    `<span class="muted">Aucune partie jouée pour l'instant</span>`;
  cancelAnimationFrame(cr.raf);
  clearInterval(cr.poll);
  const r = d.round;
  const box = $("#cr-mult");
  if (r?.status === "playing") {
    cr.startedLocal = performance.now() - r.elapsedMs;
    cr.redraw = null;
    box.className = "crash-mult";
    cr.raf = requestAnimationFrame(frame);
    // Seul le serveur connaît le point d'effondrement : on lui demande l'état en continu.
    cr.poll = setInterval(async () => {
      const next = await api("crash").catch(() => null);
      if (!next || next.round?.status === "playing") return;
      apply(next);
      refreshHistory("crash");
      if (next.round?.status === "won" && next.round.cashoutAt >= 5) flare();
    }, 250);
  } else if (r) {
    const end = Math.log(r.crashPoint) / cr.growth;
    const won = r.status === "won";
    cr.redraw = () => draw(end, won ? "won" : "lost", won ? r.cashoutAt : null);
    cr.redraw();
    box.className = `crash-mult ${won ? "won" : "crashed"}`;
    $("#cr-m").innerHTML = won ? `+${fmt(r.payout)}` : `${fmtDec(r.crashPoint)}×`;
    $("#cr-sub").textContent = won
      ? `Encaissé à ×${fmtDec(r.cashoutAt)}, effondrement à ×${fmtDec(r.crashPoint)}`
      : `Effondrement : mise de ${fmt(r.bet)} jetons perdue`;
  } else {
    cr.redraw = () => draw(0, "idle");
    cr.redraw();
  }
  paintButton();
}

function frame() {
  const r = cr.round;
  if (state.page !== "crash" || r?.status !== "playing") return;
  const elapsed = performance.now() - cr.startedLocal;
  const m = Math.floor(Math.exp(cr.growth * elapsed) * 100) / 100;
  const shown = r.autoCashout ? Math.min(m, r.autoCashout) : m;
  draw(elapsed, "fly");
  $("#cr-m").textContent = `${fmtDec(shown)}×`;
  $("#cr-sub").textContent = `Gain actuel : ${fmt(Math.floor(r.bet * shown))} jetons`;
  if (!r.autoCashout) $("#cr-main").textContent = `Encaisser ${fmt(Math.floor(r.bet * m))}`;
  cr.raf = requestAnimationFrame(frame);
}

function paintButton() {
  const btn = $("#cr-main");
  if (!btn) return;
  const r = cr.round;
  const playing = r?.status === "playing";
  btn.disabled = false;
  if (playing && r.autoCashout) {
    btn.className = "btn btn-lg btn-block";
    btn.dataset.mode = "wait";
    btn.disabled = true;
    btn.textContent = `Encaissement auto à ×${fmtDec(r.autoCashout)}`;
  } else if (playing) {
    btn.className = "btn btn-win btn-lg btn-block";
    btn.dataset.mode = "cashout";
    btn.textContent = "Encaisser";
  } else {
    btn.className = "btn btn-gold btn-lg btn-block";
    btn.dataset.mode = "start";
    btn.textContent = `Lancer pour ${fmt(Math.max(0, Math.floor(Number($("#cr-bet").value) || 0)))} jetons`;
  }
  setStakeDisabled("cr-bet", playing);
  $("#cr-auto").disabled = playing;
  $("#cr-auto-toggle").disabled = playing;
}

function paintInfo() {
  const el = $("#cr-info");
  if (!el) return;
  const bet = Math.max(0, Math.floor(Number($("#cr-bet").value) || 0));
  const auto = Number($("#cr-auto").value);
  const pct = (m) => `${fmtDec(crashChance(m), 1)} %`;
  el.innerHTML =
    cr.auto && auto >= 1.01
      ? `<div><span>Gain à ×${fmtDec(auto)}</span><b>${tok(Math.floor(bet * auto))}</b></div><div><span>Chance d'y arriver</span><b>${pct(auto)}</b></div>`
      : `<div><span>Chance d'atteindre ×2</span><b>${pct(2)}</b></div><div><span>Chance d'atteindre ×10</span><b>${pct(10)}</b></div>`;
}

async function main() {
  const btn = $("#cr-main");
  if (!btn || btn.disabled) return;
  if (btn.dataset.mode === "cashout") {
    btn.disabled = true;
    try {
      const d = await api("crash/cashout", {});
      apply(d);
      refreshHistory("crash");
      if (d.round?.status === "won" && d.round.cashoutAt >= 5) flare();
    } catch (err) {
      toast(err.message, "error");
      paintButton();
    }
    return;
  }
  if (btn.dataset.mode !== "start") return;
  const bet = readStake("cr-bet");
  if (!bet) return;
  let auto = null;
  if (cr.auto) {
    auto = Number($("#cr-auto").value);
    if (!(auto >= 1.01)) return toast("L'encaissement automatique commence à ×1,01", "error");
  }
  btn.disabled = true;
  try {
    apply(await api("crash/start", { bet, autoCashout: auto }));
  } catch (err) {
    toast(err.message, "error");
    paintButton();
  }
}

/* ---------- Dessin de la courbe ---------- */
function ctx2d() {
  const c = $("#cr-canvas");
  if (!c) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (!w || !h) return null;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}
function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const f = x / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}

function draw(elapsed, mode, cashAt = null) {
  const cv = ctx2d();
  if (!cv) return;
  const { ctx, w, h } = cv;
  const g = cr.growth;
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 50, r: 30, t: 30, b: 34 };
  const m = Math.exp(g * Math.max(0, elapsed));
  const tMax = Math.max(8000, elapsed * 1.2);
  const mMax = Math.max(2, 1 + (m - 1) * 1.25);
  const X = (t) => pad.l + (t / tMax) * (w - pad.l - pad.r);
  const Y = (v) => h - pad.b - ((v - 1) / (mMax - 1)) * (h - pad.t - pad.b);

  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(236,230,214,0.06)";
  ctx.fillStyle = "rgba(236,230,214,0.4)";
  ctx.font = "500 11px 'Geist Variable', system-ui, sans-serif";
  const sm = niceStep((mMax - 1) / 4);
  for (let k = 0; 1 + k * sm <= mMax + 1e-9; k++) {
    const v = 1 + k * sm;
    const y = Y(v);
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
    ctx.fillText(`${v < 10 ? v.toFixed(1).replace(".", ",") : Math.round(v)}×`, 10, y + 4);
  }
  const st = niceStep(tMax / 1000 / 5) * 1000;
  for (let t = st; t <= tMax; t += st) ctx.fillText(`${Math.round(t / 1000)} s`, X(t) - 8, h - 12);
  if (elapsed <= 0) return;

  const color = mode === "lost" ? "#d9776a" : mode === "won" ? "#8cc49a" : "#c9a96a";
  const curve = new Path2D();
  for (let i = 0; i <= 100; i++) {
    const t = (elapsed * i) / 100;
    if (i) curve.lineTo(X(t), Y(Math.exp(g * t)));
    else curve.moveTo(X(t), Y(Math.exp(g * t)));
  }
  const area = new Path2D(curve);
  area.lineTo(X(elapsed), Y(1));
  area.lineTo(X(0), Y(1));
  area.closePath();
  const fill = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
  const rgb = mode === "lost" ? "217,119,106" : mode === "won" ? "140,196,154" : "201,169,106";
  fill.addColorStop(0, `rgba(${rgb},0.22)`);
  fill.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = fill;
  ctx.fill(area);
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.stroke(curve);
  ctx.restore();

  if (cashAt) {
    const x = X(Math.log(cashAt) / g);
    const y = Y(cashAt);
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fillStyle = "#8cc49a";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#0e100f";
    ctx.stroke();
    ctx.fillStyle = "#ece6d6";
    ctx.font = "600 12px 'Geist Variable', system-ui, sans-serif";
    ctx.fillText(`×${cashAt.toFixed(2).replace(".", ",")}`, x + 11, y - 10);
  }
  // Tête de la courbe : point lumineux, ou éclat à l'effondrement.
  const hx = X(elapsed);
  const hy = Y(m);
  ctx.beginPath();
  ctx.arc(hx, hy, mode === "fly" ? 6 : 5, 0, Math.PI * 2);
  ctx.fillStyle = mode === "fly" ? "#e2c88f" : color;
  ctx.fill();
  if (mode === "fly") {
    ctx.beginPath();
    ctx.arc(hx, hy, 12, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(226,200,143,0.35)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  } else if (mode === "lost") {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(hx + Math.cos(a) * 9, hy + Math.sin(a) * 9);
      ctx.lineTo(hx + Math.cos(a) * 16, hy + Math.sin(a) * 16);
      ctx.stroke();
    }
  }
}

gamePage("crash", render);
