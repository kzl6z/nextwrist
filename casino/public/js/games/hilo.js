/* Hi-Lo : la carte suivante sera-t-elle plus haute ou plus basse ? */
import { $, api, fmt, fmtDec, mult, onSpace, readStake, setBalance, setStakeDisabled, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { icon } from "../icons.js";
import { cardHtml } from "./cards.js";

const hl = { bet: 10, game: null, busy: false, lastCard: null };
const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
const rankOf = (card) => RANKS.indexOf(card.slice(0, -1)) + 1;

function render() {
  hl.lastCard = null;
  document.querySelector("#view").innerHTML = gameShell({
    id: "hilo",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("hl-bet", hl.bet)}</div>
      <div class="info-list" id="hl-info"></div>`,
    action: `<div class="hl-choices" id="hl-choices"></div>
      <button class="btn btn-gold btn-lg btn-block" id="hl-main">Commencer</button>`,
    stage: `
      <div class="hilo-stage felt-soft">
        <div class="hilo-scale" id="hl-scale">${RANKS.map((r) => `<span data-r="${r}">${{ J: "V", Q: "D", K: "R" }[r] ?? r}</span>`).join("")}</div>
        <div class="hilo-card" id="hl-card">${cardHtml("??")}</div>
        <div class="result-line" id="hl-result"></div>
        <div class="hilo-trail" id="hl-trail"></div>
      </div>`,
    rules: `<p>Une carte est retournée. Devine si la suivante sera plus haute ou égale, ou plus basse ou égale. Chaque bonne réponse multiplie tes gains selon sa probabilité.</p>
      <p>Tu peux passer une carte sans risque, et encaisser après au moins une bonne réponse. L'as est la plus basse carte, le roi la plus haute.</p>`,
  });
  $("#hl-bet").addEventListener("input", (e) => (hl.bet = e.target.value));
  $("#hl-main").addEventListener("click", main);
  $("#hl-choices").addEventListener("click", (e) => {
    const b = e.target.closest("[data-dir]");
    if (b && !b.disabled) guess(b.dataset.dir);
  });
  onSpace(main);
  paint();
  api("hilo")
    .then((d) => apply(d, false))
    .catch((err) => toast(err.message, "error"));
}

function apply(d, animate = true) {
  if (state.page !== "hilo") return;
  setBalance(d.balance);
  hl.game = d.game;
  paint(animate);
}

function dirLabel(rank, dir) {
  if (rank === 1) return dir === "hi" ? "Plus haute" : "Égale (as)";
  if (rank === 13) return dir === "lo" ? "Plus basse" : "Égale (roi)";
  return dir === "hi" ? "Plus haute ou égale" : "Plus basse ou égale";
}

function paint(animate = false) {
  if (state.page !== "hilo") return;
  const g = hl.game;
  const playing = g?.status === "playing";
  setStakeDisabled("hl-bet", playing);
  const btn = $("#hl-main");
  if (playing) {
    btn.className = "btn btn-win btn-lg btn-block";
    btn.disabled = !g.steps;
    btn.textContent = g.steps ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Fais un premier pronostic";
  } else {
    btn.className = "btn btn-gold btn-lg btn-block";
    btn.disabled = false;
    btn.textContent = "Commencer";
  }
  const r = g ? rankOf(g.card) : 0;
  $("#hl-choices").innerHTML = playing
    ? `<button class="hl-btn" data-dir="hi">${icon("up", { size: 18 })}<span>${dirLabel(r, "hi")}<small>${fmtDec(g.odds.hi.chance * 100, 1)} %</small></span><b>${mult(g.odds.hi.multiplier)}</b></button>
       <button class="hl-btn" data-dir="lo">${icon("down", { size: 18 })}<span>${dirLabel(r, "lo")}<small>${fmtDec(g.odds.lo.chance * 100, 1)} %</small></span><b>${mult(g.odds.lo.multiplier)}</b></button>
       <button class="btn btn-quiet btn-sm" data-dir="skip">Passer cette carte</button>`
    : "";
  $("#hl-info").innerHTML = playing
    ? `<div><span>Multiplicateur actuel</span><b>${mult(g.multiplier)}</b></div><div><span>Gain si tu encaisses</span><b>${fmt(Math.floor(g.bet * g.multiplier))}</b></div>`
    : "";
  // Carte courante
  if (g) {
    const cardEl = $("#hl-card");
    if (hl.lastCard !== g.card) {
      cardEl.innerHTML = cardHtml(g.card, { animate });
      hl.lastCard = g.card;
    }
    document.querySelectorAll("#hl-scale [data-r]").forEach((s) => s.classList.toggle("on", rankOf(`${s.dataset.r}x`) === r));
    $("#hl-trail").innerHTML = g.history
      .slice(-12)
      .map((h) => `<div class="trail-item ${h.dir === "skip" ? "skip" : h.ok ? "ok" : "ko"}">${cardHtml(h.card)}<i>${h.dir === "skip" ? icon("next", { size: 12 }) : icon(h.dir === "hi" ? "up" : "down", { size: 12 })}</i></div>`)
      .join("");
  }
  if (g && !playing && animate) {
    if (g.status === "won") {
      banner($("#hl-result"), `<b>+${fmt(g.payout)}</b> jetons, ${mult(g.multiplier)}`, "win");
      if (g.multiplier >= 5) flare();
    } else banner($("#hl-result"), "Raté : mise perdue", "lose");
  } else if (playing) banner($("#hl-result"), g.steps ? `${g.steps} bonne${g.steps > 1 ? "s" : ""} réponse${g.steps > 1 ? "s" : ""}` : "");
}

async function main() {
  if (hl.busy) return;
  const playing = hl.game?.status === "playing";
  hl.busy = true;
  try {
    if (playing) {
      if (!hl.game.steps) return;
      apply(await api("hilo/cashout", {}));
      refreshHistory("hilo");
    } else {
      const bet = readStake("hl-bet");
      if (!bet) return;
      apply(await api("hilo/start", { bet }));
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    hl.busy = false;
  }
}

async function guess(dir) {
  if (hl.busy || hl.game?.status !== "playing") return;
  hl.busy = true;
  try {
    const d = await api("hilo/guess", { dir });
    apply(d);
    if (d.game.status !== "playing") refreshHistory("hilo");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    hl.busy = false;
  }
}

gamePage("hilo", render);
