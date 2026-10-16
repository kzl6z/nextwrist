/* Pile ou face : enchaîne les bons choix, le multiplicateur double à chaque fois */
import { $, api, fmt, mult, readStake, setBalance, setStakeDisabled, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const cf = { bet: 10, game: null, busy: false, turns: 0 };
const SIDE = { heads: "Face", tails: "Pile" };

const coinFace = (letter) => `<div class="coin-face"><span class="display">${letter}</span></div>`;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "coinflip",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("cf-bet", cf.bet)}</div>
      <div class="info-list" id="cf-info"></div>`,
    action: `<div class="label" id="cf-pick-label">Choisis ton côté pour lancer</div>
      <div class="cf-pick"><button class="btn btn-lg btn-gold" data-side="heads">Face</button><button class="btn btn-lg btn-gold" data-side="tails">Pile</button></div>
      <button class="btn btn-win btn-lg btn-block hidden" id="cf-cash" style="margin-top:8px">Encaisser</button>`,
    stage: `
      <div class="coin-stage">
        <div class="coin" id="cf-coin"><div class="coin-inner" id="cf-inner">${coinFace("F")}<div class="coin-back">${coinFace("P")}</div></div></div>
        <div class="result-line" id="cf-result"></div>
        <div class="cf-ladder" id="cf-ladder"></div>
      </div>`,
    rules: `<p>Choisis pile ou face : la pièce est lancée. Si tu as vu juste, ton multiplicateur double et tu peux relancer ou encaisser.</p>
      <p>Un mauvais choix fait perdre la mise. Vingt bons choix d'affilée encaissent automatiquement.</p>`,
  });
  $("#cf-bet").addEventListener("input", (e) => (cf.bet = e.target.value));
  document.querySelector(".cf-pick").addEventListener("click", (e) => {
    const b = e.target.closest("[data-side]");
    if (b) flip(b.dataset.side);
  });
  $("#cf-cash").addEventListener("click", cashout);
  paint();
  api("coinflip")
    .then((d) => apply(d))
    .catch((err) => toast(err.message, "error"));
}

function apply(d) {
  if (state.page !== "coinflip") return;
  setBalance(d.balance);
  cf.game = d.game;
  paint();
}

function paint() {
  if (state.page !== "coinflip") return;
  const g = cf.game;
  const playing = g?.status === "playing";
  setStakeDisabled("cf-bet", playing);
  $("#cf-pick-label").textContent = playing ? "Relance : pile ou face ?" : "Choisis ton côté pour lancer";
  const cash = $("#cf-cash");
  cash.classList.toggle("hidden", !playing);
  if (playing) cash.textContent = `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}`;
  $("#cf-info").innerHTML = playing
    ? `<div><span>Série</span><b>${g.streak} bon${g.streak > 1 ? "s" : ""} choix</b></div><div><span>Multiplicateur actuel</span><b>${mult(g.multiplier)}</b></div><div><span>Au prochain bon choix</span><b>${mult(g.next)}</b></div>`
    : `<div><span>Premier bon choix</span><b>×1,96</b></div>`;
  const streak = playing ? g.streak : 0;
  $("#cf-ladder").innerHTML = Array.from({ length: 8 }, (_, i) => {
    const m = Math.floor(0.98 * 2 ** (i + 1) * 100) / 100;
    return `<span class="${i < streak ? "on" : i === streak && playing ? "next" : ""}">${mult(m)}</span>`;
  }).join("");
}

async function flip(side) {
  if (cf.busy) return;
  const playing = cf.game?.status === "playing";
  let bet = 0;
  if (!playing) {
    bet = readStake("cf-bet");
    if (!bet) return;
  }
  cf.busy = true;
  banner($("#cf-result"), "");
  try {
    const d = playing ? await api("coinflip/flip", { side }) : await api("coinflip/start", { bet, side });
    if (!playing) setBalance(d.balance);
    const last = d.game.flips[d.game.flips.length - 1];
    // Rotation : un nombre entier de tours, plus un demi-tour pour finir sur pile.
    cf.turns += 5;
    const angle = cf.turns * 360 + (last.result === "tails" ? 180 : 0);
    const inner = $("#cf-inner");
    inner.style.transform = `rotateY(${angle}deg)`;
    await sleep(1050);
    apply(d);
    const ok = last.side === last.result;
    if (d.game.status === "lost") {
      banner($("#cf-result"), `${SIDE[last.result]} : mise perdue`, "lose");
      refreshHistory("coinflip");
    } else if (d.game.status === "won") {
      banner($("#cf-result"), `<b>+${fmt(d.game.payout)}</b> jetons`, "win");
      flare();
      refreshHistory("coinflip");
    } else if (ok) banner($("#cf-result"), `${SIDE[last.result]} : bien vu, ${mult(d.game.multiplier)}`, "win");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    cf.busy = false;
  }
}

async function cashout() {
  if (cf.busy || cf.game?.status !== "playing") return;
  cf.busy = true;
  try {
    const d = await api("coinflip/cashout", {});
    apply(d);
    banner($("#cf-result"), `<b>+${fmt(d.game.payout)}</b> jetons encaissés`, "win");
    if (d.game.multiplier >= 7) flare();
    refreshHistory("coinflip");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    cf.busy = false;
  }
}

gamePage("coinflip", render);
