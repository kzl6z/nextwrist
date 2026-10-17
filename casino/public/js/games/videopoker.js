/* Video poker — Jacks or Better, table 9/6 */
import { $, api, fmt, onSpace, readStake, setBalance, setStakeDisabled, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";
import { cardHtml } from "./cards.js";

const vp = { bet: 10, game: null, holds: [false, false, false, false, false], busy: false, pays: [] };

async function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "videopoker",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("vp-bet", vp.bet)}</div>
      <div><div class="label">Table des gains</div><div class="paytable" id="vp-pays"></div></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="vp-main">Distribuer</button>
      <p class="hint"><kbd>Espace</kbd> pour distribuer ou tirer</p>`,
    stage: `
      <div class="vp-stage felt-soft">
        <div class="vp-hand" id="vp-hand">${Array.from({ length: 5 }, () => `<div class="vp-slot">${cardHtml("??")}</div>`).join("")}</div>
        <div class="result-line" id="vp-result"></div>
      </div>`,
    rules: `<p>Tu reçois cinq cartes. Touche celles que tu veux garder, puis tire : les autres sont remplacées. La main finale est payée selon la table, à partir d'une paire de valets.</p>
      <p>Avec un jeu optimal, cette table redistribue 99,5 % des mises.</p>`,
  });
  $("#vp-bet").addEventListener("input", (e) => {
    vp.bet = e.target.value;
    paintPays();
  });
  $("#vp-main").addEventListener("click", main);
  $("#vp-hand").addEventListener("click", (e) => {
    const slot = e.target.closest("[data-i]");
    if (!slot || vp.game?.status !== "playing" || vp.busy) return;
    const i = Number(slot.dataset.i);
    vp.holds[i] = !vp.holds[i];
    paintHand(false);
  });
  onSpace(main);
  try {
    vp.pays = (await casinoConfig()).poker;
    const d = await api("videopoker");
    apply(d, false);
  } catch (err) {
    toast(err.message, "error");
  }
}

function apply(d, animate = true) {
  if (state.page !== "videopoker") return;
  setBalance(d.balance);
  vp.game = d.game;
  if (d.game?.status === "playing") vp.holds = [...d.game.held];
  paint(animate);
}

function paintPays() {
  const g = vp.game;
  const bet = g?.status === "playing" ? g.bet : Math.max(0, Math.floor(Number($("#vp-bet")?.value) || 0));
  $("#vp-pays").innerHTML = vp.pays
    .map(([key, label, m]) => `<div class="pay-row ${g?.result === key ? "on" : ""}"><span>${label}</span><b>×${m}</b><em>${fmt(bet * m)}</em></div>`)
    .join("");
}

function paintHand(animate, fresh = [0, 1, 2, 3, 4]) {
  const g = vp.game;
  if (!g) return;
  $("#vp-hand").innerHTML = g.hand
    .map(
      (c, i) => `<button class="vp-slot ${vp.holds[i] && g.status === "playing" ? "held" : ""}" data-i="${i}" ${g.status === "playing" ? "" : "disabled"} aria-pressed="${vp.holds[i]}">
        ${cardHtml(c, { animate: animate && fresh.includes(i), delay: fresh.indexOf(i) * 90 })}<span class="hold-tag">Gardée</span></button>`,
    )
    .join("");
}

function paint(animate = false, fresh) {
  if (state.page !== "videopoker") return;
  const g = vp.game;
  const playing = g?.status === "playing";
  setStakeDisabled("vp-bet", playing);
  const btn = $("#vp-main");
  btn.textContent = playing ? "Tirer" : "Distribuer";
  btn.className = `btn ${playing ? "btn-line" : "btn-gold"} btn-lg btn-block`;
  paintPays();
  if (!g) return;
  paintHand(animate, fresh);
  const label = vp.pays.find(([k]) => k === g.result)?.[1];
  if (playing) banner($("#vp-result"), label ? `Main servie : ${label}. Touche les cartes à garder.` : "Touche les cartes à garder, puis tire.");
  else if (animate) {
    banner($("#vp-result"), g.payout ? `${label} : <b>+${fmt(g.payout)}</b> jetons` : "Pas de combinaison payante", g.payout ? "win" : "lose");
    if (g.payout >= g.bet * 9) flare();
  }
}

async function main() {
  if (vp.busy) return;
  vp.busy = true;
  try {
    if (vp.game?.status === "playing") {
      const before = vp.game.hand;
      const d = await api("videopoker/draw", { holds: vp.holds });
      // Les cartes remplacées tombent l'une après l'autre.
      vp.game = d.game;
      const fresh = d.game.hand.map((c, i) => (c !== before[i] ? i : -1)).filter((i) => i >= 0);
      setBalance(d.balance);
      paint(true, fresh);
      await sleep(fresh.length * 90 + 200);
      refreshHistory("videopoker");
    } else {
      const bet = readStake("vp-bet");
      if (!bet) return;
      vp.holds = [false, false, false, false, false];
      apply(await api("videopoker/deal", { bet }));
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    vp.busy = false;
  }
}

gamePage("videopoker", render);