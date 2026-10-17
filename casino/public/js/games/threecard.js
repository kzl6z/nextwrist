/* Three Card Poker : Ante et Play contre le croupier, Pair Plus en option */
import { $, api, fmt, setBalance, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { cardHtml } from "./cards.js";

const HAND = { high: "Carte haute", pair: "Paire", flush: "Couleur", straight: "Suite", trips: "Brelan", straightflush: "Quinte flush" };
const PAIR_PLUS = [["straightflush", 40], ["trips", 30], ["straight", 6], ["flush", 4], ["pair", 1]];
const ANTE_BONUS = [["straightflush", 5], ["trips", 4], ["straight", 1]];
const tc = { ante: 10, pairPlus: 0, game: null, busy: false };

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "threecard",
    stageClass: "felt-stage",
    controls: `
      <div><div class="label">Ante</div>${stakeInput("tc-ante", tc.ante, 5000)}</div>
      <div><div class="label">Pair Plus (facultatif)</div>${stakeInput("tc-pp", tc.pairPlus, 5000)}</div>
      <div class="paytable tc-pays">
        <div class="tc-pays-head">Pair Plus</div>
        ${PAIR_PLUS.map(([k, m]) => `<div class="pay-row" data-pp="${k}"><span>${HAND[k]}</span><b>${m} pour 1</b></div>`).join("")}
        <div class="tc-pays-head">Bonus d'Ante</div>
        ${ANTE_BONUS.map(([k, m]) => `<div class="pay-row" data-ab="${k}"><span>${HAND[k]}</span><b>${m} pour 1</b></div>`).join("")}
      </div>`,
    action: `<div id="tc-actions"></div>`,
    stage: `
      <div class="table-felt tc-table">
        <div class="hand"><div class="hand-label">Croupier <span class="hand-value" id="tc-dv"></span></div><div class="cards" id="tc-dc"></div></div>
        <div class="bj-banner display" id="tc-banner"></div>
        <div class="table-text">Le croupier joue avec Dame haute ou mieux</div>
        <div class="hand"><div class="cards" id="tc-pc"></div><div class="hand-label">Toi <span class="hand-value" id="tc-pv"></span></div></div>
      </div>
      <div class="result-line" id="tc-result"></div>`,
    rules: `<p>Pose l'Ante (et, si tu veux, une mise Pair Plus), puis reçois trois cartes. Regarde ta main : <b>joue</b> en ajoutant une mise Play égale à l'Ante, ou <b>couche-toi</b> et perds l'Ante.</p>
      <p>Si le croupier n'a pas au moins Dame haute, l'Ante est payé 1 pour 1 et le Play est rendu. Sinon, la meilleure main gagne : Ante et Play sont payés 1 pour 1. Ordre des mains : quinte flush, brelan, suite, couleur, paire, carte haute. Pair Plus paie selon ta main, quoi qu'ait le croupier. Conseil : jouer à partir de Dame-6-4.</p>`,
  });
  $("#tc-ante").addEventListener("input", (e) => (tc.ante = e.target.value));
  $("#tc-pp").addEventListener("input", (e) => (tc.pairPlus = e.target.value));
  $("#tc-pp").min = "0";
  $("#tc-actions").addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    if (b.dataset.act === "deal") deal();
    else decide(b.dataset.act);
  });
  paint(false);
  api("threecard")
    .then((d) => {
      if (state.page !== "threecard") return;
      setBalance(d.balance);
      tc.game = d.game;
      paint(false);
    })
    .catch((err) => toast(err.message, "error"));
}

function paint(animate) {
  const g = tc.game;
  const playing = g?.status === "playing";
  ["tc-ante", "tc-pp"].forEach((id) => {
    $(`#${id}-box`)?.classList.toggle("disabled", playing);
    $(`#${id}`).disabled = playing;
  });
  $("#tc-actions").innerHTML = playing
    ? `<div class="bj-actions"><button class="btn btn-gold btn-lg" data-act="play">Jouer (+${fmt(g.ante)})</button><button class="btn btn-lg" data-act="fold">Se coucher</button></div>`
    : `<button class="btn btn-gold btn-lg btn-block" data-act="deal">Distribuer</button>`;
  $("#tc-pc").innerHTML = g ? g.player.map((c, i) => cardHtml(c, { animate, delay: i * 140 })).join("") : "";
  $("#tc-pv").textContent = g ? HAND[g.playerHand] : "";
  if (!g) $("#tc-dc").innerHTML = "";
  else if (playing) $("#tc-dc").innerHTML = [0, 1, 2].map((i) => cardHtml("??", { animate, delay: 60 + i * 140 })).join("");
  else $("#tc-dc").innerHTML = g.dealer.map((c) => cardHtml(c)).join("");
  $("#tc-dv").textContent = g && !playing && g.result ? HAND[g.result.dealerHand] : "";
  document.querySelectorAll(".tc-pays .pay-row").forEach((r) => r.classList.remove("on"));
  if (g?.result) showResult(g);
  else {
    $("#tc-banner").textContent = "";
    banner($("#tc-result"), playing ? `Ta main : ${HAND[g.playerHand]}` : "");
  }
}

function showResult(g) {
  const r = g.result;
  const el = $("#tc-banner");
  const text = { win: "Tu gagnes", lose: "Le croupier gagne", push: "Égalité", noqualify: "Le croupier ne joue pas", fold: "Couché" }[r.outcome];
  const staked = g.ante + g.pairPlus + g.play;
  el.textContent = text;
  el.className = `bj-banner display ${g.payout > staked ? "win" : g.payout ? "" : "lose"}`;
  if (r.pairPlusWin) document.querySelector(`.tc-pays [data-pp="${r.playerHand}"]`)?.classList.add("on");
  if (r.bonusWin) document.querySelector(`.tc-pays [data-ab="${r.playerHand}"]`)?.classList.add("on");
  const parts = [];
  if (r.anteWin || r.playWin) parts.push(`Ante et Play ${fmt(r.anteWin + r.playWin)}`);
  if (r.bonusWin) parts.push(`bonus ${fmt(r.bonusWin)}`);
  if (r.pairPlusWin) parts.push(`Pair Plus ${fmt(r.pairPlusWin)}`);
  banner(
    $("#tc-result"),
    g.payout ? `Retour : <b>${fmt(g.payout)}</b> jetons pour ${fmt(staked)} misés${parts.length ? ` (${parts.join(", ")})` : ""}` : `Mise de ${fmt(staked)} jetons perdue`,
    g.payout > staked ? "win" : "lose",
  );
}

function readBets() {
  const ante = Math.floor(Number($("#tc-ante").value));
  const pp = Math.floor(Number($("#tc-pp").value)) || 0;
  if (!Number.isFinite(ante) || ante < 1) return toast("Indique un Ante d'au moins 1 jeton", "error"), null;
  if (pp < 0) return toast("Pair Plus invalide", "error"), null;
  if (ante * 2 + pp > 10_000) return toast("Ante + Play + Pair Plus : 10 000 jetons maximum", "error"), null;
  if (ante * 2 + pp > state.balance) return toast("Solde insuffisant : prévois l'Ante deux fois (Ante et Play) plus le Pair Plus", "error"), null;
  return { ante, pairPlus: pp };
}

async function deal() {
  if (tc.busy) return;
  const bets = readBets();
  if (!bets) return;
  tc.busy = true;
  try {
    const d = await api("threecard/deal", bets);
    setBalance(d.balance);
    tc.game = d.game;
    paint(true);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    tc.busy = false;
  }
}

async function decide(action) {
  if (tc.busy || tc.game?.status !== "playing") return;
  tc.busy = true;
  try {
    const d = await api("threecard/decide", { action });
    setBalance(d.balance - d.game.payout);
    tc.game = { ...d.game, result: null };
    $("#tc-actions").innerHTML = "";
    // Retournement des cartes du croupier une par une.
    for (let i = 0; i < 3; i++) {
      if (state.page !== "threecard") return;
      const slots = $("#tc-dc").children;
      slots[i].outerHTML = cardHtml(d.game.dealer[i], { animate: true });
      await sleep(300);
    }
    tc.game = d.game;
    setBalance(d.balance);
    paint(false);
    if (d.game.result.pairPlusWin >= d.game.pairPlus * 7 && d.game.pairPlus) flare();
    refreshHistory("threecard");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    tc.busy = false;
  }
}

gamePage("threecard", render);
