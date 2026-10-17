/* Limbo : fixe une cible, le multiplicateur tiré doit l'atteindre */
import { $, api, fmt, fmtDec, mult, onSpace, readStake, setBalance, stakeInput, state, toast, tok, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const lb = { bet: 10, target: "2.00", busy: false, recent: [] };
const target = () => Math.floor(Number(lb.target) * 100) / 100;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "limbo",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("lb-bet", lb.bet)}</div>
      <div><div class="label">Multiplicateur cible</div>
        <div class="stake-input"><input id="lb-target" type="number" inputmode="decimal" step="0.01" min="1.01" max="10000" value="${lb.target}" aria-label="Multiplicateur cible" /><span class="suffix">×</span></div>
        <div class="quick-row" id="lb-quick">${[1.5, 2, 5, 10, 100].map((m) => `<button class="btn btn-sm" data-t="${m}">${mult(m)}</button>`).join("")}</div>
      </div>
      <div class="info-list" id="lb-info"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="lb-play">Jouer</button>
      <p class="hint"><kbd>Espace</kbd> pour jouer</p>`,
    stage: `
      <div class="limbo-stage">
        <div class="dice-recent" id="lb-recent"></div>
        <div class="limbo-value display" id="lb-value">1,00×</div>
        <div class="limbo-target">Cible <b id="lb-target-show"></b></div>
        <div class="result-line" id="lb-result"></div>
      </div>`,
    rules: `<p>Un multiplicateur est tiré au hasard. S'il atteint ou dépasse ta cible, tu gagnes ta mise multipliée par la cible.</p>
      <p>Chance de gagner = 99 ÷ cible : 49,5 % pour ×2, 9,9 % pour ×10, 0,99 % pour ×100.</p>`,
  });
  $("#lb-bet").addEventListener("input", (e) => {
    lb.bet = e.target.value;
    paint();
  });
  $("#lb-target").addEventListener("input", (e) => {
    lb.target = e.target.value;
    paint();
  });
  $("#lb-quick").addEventListener("click", (e) => {
    const b = e.target.closest("[data-t]");
    if (!b) return;
    lb.target = Number(b.dataset.t).toFixed(2);
    $("#lb-target").value = lb.target;
    paint();
  });
  $("#lb-play").addEventListener("click", play);
  onSpace(play);
  paint();
  paintRecent();
}

function paint() {
  const t = target();
  const bet = Math.max(0, Math.floor(Number($("#lb-bet").value) || 0));
  const ok = t >= 1.01;
  $("#lb-target-show").textContent = ok ? `×${fmtDec(t)}` : "invalide";
  $("#lb-info").innerHTML = ok
    ? `<div><span>Chance de gagner</span><b>${fmtDec(Math.min(99, 99 / t), 2)} %</b></div><div><span>Gain si tu gagnes</span><b>${tok(Math.floor(bet * t))}</b></div>`
    : `<div><span>La cible commence à ×1,01</span></div>`;
}

function paintRecent() {
  $("#lb-recent").innerHTML = lb.recent.map((r) => `<span class="hpill ${r.win ? "high" : "low"}">${fmtDec(r.result)}×</span>`).join("");
}

async function play() {
  if (lb.busy) return;
  const bet = readStake("lb-bet");
  if (!bet) return;
  const t = target();
  if (!(t >= 1.01)) return toast("La cible commence à ×1,01", "error");
  lb.busy = true;
  $("#lb-play").disabled = true;
  try {
    const r = await api("limbo", { bet, target: t });
    setBalance(r.balance - r.payout);
    const value = $("#lb-value");
    value.className = "limbo-value display";
    // Montée rapide jusqu'au résultat (échelle logarithmique).
    const start = performance.now();
    const dur = 420 + Math.min(500, Math.log10(r.result) * 260);
    await new Promise((resolve) => {
      const step = (now) => {
        const k = Math.min(1, (now - start) / dur);
        const v = Math.exp(Math.log(r.result) * (1 - (1 - k) ** 3));
        value.textContent = `${fmtDec(Math.max(1, v))}×`;
        if (k < 1) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });
    value.textContent = `${fmtDec(r.result)}×`;
    value.className = `limbo-value display ${r.win ? "win" : "lose"}`;
    setBalance(r.balance);
    banner($("#lb-result"), r.win ? `<b>+${fmt(r.payout)}</b> jetons` : `Il fallait ×${fmtDec(r.target)}`, r.win ? "win" : "lose");
    lb.recent = [{ result: r.result, win: r.win }, ...lb.recent].slice(0, 10);
    paintRecent();
    refreshHistory("limbo");
    if (r.win && r.target >= 10) flare();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    lb.busy = false;
    if (state.page === "limbo") $("#lb-play").disabled = false;
  }
}

gamePage("limbo", render);
