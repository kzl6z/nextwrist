/* Dice : tirage de 0,00 à 99,99, au-dessus ou en dessous d'un seuil */
import { $, api, fmt, fmtDec, onSpace, readStake, setBalance, stakeInput, state, toast, tok, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const EDGE = 0.99;
const dc = { bet: 10, target: 50, over: true, busy: false, recent: [] };
const chance = () => (dc.over ? 100 - dc.target : dc.target);
const multiplier = () => Math.floor((EDGE / (chance() / 100)) * 10_000) / 10_000;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "dice",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("dc-bet", dc.bet)}</div>
      <div><div class="label">Gagner si le tirage est</div>
        <div class="seg" id="dc-dir"><button data-over="0">En dessous</button><button data-over="1">Au-dessus</button></div></div>
      <div class="info-list" id="dc-info"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="dc-roll">Lancer le dé</button>
      <p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="dice-stage">
        <div class="dice-recent" id="dc-recent"></div>
        <div class="dice-roll display" id="dc-value">50,00</div>
        <div class="result-line" id="dc-result"></div>
        <div class="dice-track" id="dc-track">
          <div class="dice-zone" id="dc-zone"></div>
          <div class="dice-marker" id="dc-marker"></div>
          <input type="range" id="dc-range" min="2" max="98" step="1" value="${dc.target}" aria-label="Seuil" />
        </div>
        <div class="dice-scale"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>
        <div class="dice-fields">
          <label><span>Seuil</span><input type="number" id="dc-target" min="2" max="98" step="1" value="${dc.target}" /></label>
          <label><span>Multiplicateur</span><output id="dc-mult"></output></label>
          <label><span>Chance de gagner</span><output id="dc-chance"></output></label>
        </div>
      </div>`,
    rules: `<p>Le dé tire un nombre entre 0,00 et 99,99. Fixe un seuil et choisis de gagner au-dessus ou en dessous.</p>
      <p>Plus ta chance de gagner est faible, plus le multiplicateur est élevé : multiplicateur = 99 ÷ chance en %.</p>`,
  });
  $("#dc-bet").addEventListener("input", (e) => {
    dc.bet = e.target.value;
    paint();
  });
  $("#dc-range").addEventListener("input", (e) => setTarget(e.target.value));
  $("#dc-target").addEventListener("change", (e) => setTarget(e.target.value));
  $("#dc-dir").addEventListener("click", (e) => {
    const b = e.target.closest("[data-over]");
    if (!b) return;
    dc.over = b.dataset.over === "1";
    paint();
  });
  $("#dc-roll").addEventListener("click", roll);
  onSpace(roll);
  paint();
  paintRecent();
}

function setTarget(v) {
  dc.target = Math.min(98, Math.max(2, Math.round(Number(v) || 50)));
  paint();
}

function paint() {
  if (state.page !== "dice") return;
  $("#dc-range").value = dc.target;
  $("#dc-target").value = dc.target;
  document.querySelectorAll("#dc-dir [data-over]").forEach((b) => b.classList.toggle("active", (b.dataset.over === "1") === dc.over));
  const zone = $("#dc-zone");
  zone.style.left = dc.over ? `${dc.target}%` : "0";
  zone.style.width = dc.over ? `${100 - dc.target}%` : `${dc.target}%`;
  $("#dc-mult").textContent = `×${fmtDec(multiplier(), 4).replace(/0+$/, "").replace(/,$/, "")}`;
  $("#dc-chance").textContent = `${fmtDec(chance(), 0)} %`;
  const bet = Math.max(0, Math.floor(Number($("#dc-bet").value) || 0));
  $("#dc-info").innerHTML = `<div><span>Gain si tu gagnes</span><b>${tok(Math.floor(bet * multiplier()))}</b></div>`;
}

function paintRecent() {
  $("#dc-recent").innerHTML = dc.recent.map((r) => `<span class="hpill ${r.win ? "high" : "low"}">${fmtDec(r.roll)}</span>`).join("");
}

async function roll() {
  if (dc.busy) return;
  const bet = readStake("dc-bet");
  if (!bet) return;
  dc.busy = true;
  $("#dc-roll").disabled = true;
  try {
    const r = await api("dice", { bet, target: dc.target, over: dc.over });
    setBalance(r.balance - r.payout);
    const value = $("#dc-value");
    const marker = $("#dc-marker");
    marker.classList.add("show");
    marker.style.left = `${r.roll}%`;
    // Défilement rapide des chiffres jusqu'au tirage.
    const start = performance.now();
    const from = Number(value.dataset.v ?? 50);
    await new Promise((resolve) => {
      const step = (now) => {
        const k = Math.min(1, (now - start) / 380);
        value.textContent = fmtDec(from + (r.roll - from) * (1 - (1 - k) ** 3));
        if (k < 1) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });
    value.dataset.v = r.roll;
    value.className = `dice-roll display ${r.win ? "win" : "lose"}`;
    marker.className = `dice-marker show ${r.win ? "win" : "lose"}`;
    setBalance(r.balance);
    banner($("#dc-result"), r.win ? `<b>+${fmt(r.payout)}</b> jetons, ×${fmtDec(r.multiplier)}` : "Perdu", r.win ? "win" : "lose");
    dc.recent = [{ roll: r.roll, win: r.win }, ...dc.recent].slice(0, 10);
    paintRecent();
    refreshHistory("dice");
    if (r.win && r.multiplier >= 10) flare();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    dc.busy = false;
    if (state.page === "dice") $("#dc-roll").disabled = false;
  }
}

gamePage("dice", render);
