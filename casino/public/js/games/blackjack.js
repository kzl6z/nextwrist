/* Blackjack : sabot de 6 jeux, croupier reste sur 17, blackjack payé 3:2 */
import { $, api, fmt, onSpace, readStake, setBalance, setStakeDisabled, stakeInput, state, toast, flare } from "../core.js";
import { gamePage, gameShell, refreshHistory } from "../casino.js";
import { cardHtml } from "./cards.js";

const bj = { bet: 10, prev: { player: [], dealer: [] }, busy: false };

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "blackjack",
    stageClass: "felt-stage",
    controls: `
      <div><div class="label">Mise <b id="bj-cur-bet"></b></div>${stakeInput("bj-bet", bj.bet)}</div>`,
    action: `
      <div id="bj-bet-zone">
        <button class="btn btn-gold btn-lg btn-block" id="bj-deal">Distribuer</button>
        <p class="hint" style="margin-top:10px"><kbd>Espace</kbd> pour distribuer</p>
      </div>
      <div id="bj-play-zone" class="hidden">
        <div class="bj-actions">
          <button class="btn btn-lg btn-gold" data-bj="hit">Tirer</button>
          <button class="btn btn-lg" data-bj="stand">Rester</button>
          <button class="btn btn-lg btn-line" data-bj="double">Doubler</button>
        </div>
      </div>`,
    stage: `
      <div class="table-felt">
        <div class="hand"><div class="hand-label">Croupier <span class="hand-value" id="bj-dv"></span></div><div class="cards" id="bj-dealer"></div></div>
        <div class="table-text">Le croupier tire jusqu'à 16 et reste à 17. Blackjack payé 3 pour 2.</div>
        <div class="bj-banner display" id="bj-banner"></div>
        <div class="hand"><div class="cards" id="bj-player"></div><div class="hand-label">Toi <span class="hand-value" id="bj-pv"></span></div></div>
      </div>`,
    rules: `<p>Approche-toi de 21 sans le dépasser. Les figures valent 10, l'as vaut 1 ou 11.</p>
      <p>Doubler : la mise est doublée et tu reçois une seule carte de plus. Un blackjack (as et figure ou 10 d'entrée) est payé 3 pour 2.</p>`,
  });
  $("#bj-bet").addEventListener("input", (e) => (bj.bet = e.target.value));
  $("#bj-deal").addEventListener("click", deal);
  $(".bj-actions").addEventListener("click", (e) => {
    const a = e.target.closest("[data-bj]")?.dataset.bj;
    if (a) action(a);
  });
  onSpace(() => $("#bj-play-zone").classList.contains("hidden") && deal());
  bj.prev = { player: [], dealer: [] };
  api("blackjack")
    .then((d) => draw(d, false))
    .catch((err) => toast(err.message, "error"));
}

function draw({ hand, balance }, animate = true) {
  if (state.page !== "blackjack") return;
  setBalance(balance);
  const playing = hand?.status === "playing";
  $("#bj-bet-zone").classList.toggle("hidden", playing);
  $("#bj-play-zone").classList.toggle("hidden", !playing);
  if (!hand) return;
  let order = 0;
  const paint = (el, cards, prev) => {
    el.innerHTML = cards
      .map((c, i) => {
        const fresh = animate && (i >= prev.length || (prev[i] === "??" && c !== "??"));
        return cardHtml(c, { delay: fresh ? order++ * 170 : 0, animate: fresh });
      })
      .join("");
  };
  paint($("#bj-player"), hand.player, bj.prev.player);
  paint($("#bj-dealer"), hand.dealer, bj.prev.dealer);
  bj.prev = { player: hand.player, dealer: hand.dealer };

  const pv = $("#bj-pv");
  pv.textContent = hand.playerValue;
  pv.className = `hand-value ${hand.playerValue > 21 ? "bust" : hand.status === "blackjack" ? "bj" : ""}`;
  const dv = $("#bj-dv");
  dv.textContent = hand.dealerValue;
  dv.className = `hand-value ${hand.dealerValue > 21 ? "bust" : ""}`;
  document.querySelector("[data-bj=double]").disabled = !hand.canDouble;
  $("#bj-cur-bet").textContent = playing ? `en jeu : ${fmt(hand.bet)}` : "";
  setStakeDisabled("bj-bet", playing);

  const messages = {
    playing: ["", ""],
    blackjack: [`Blackjack, +${fmt(hand.payout)}`, "gold"],
    won: [`Gagné, +${fmt(hand.payout)}`, "win"],
    push: ["Égalité, mise rendue", ""],
    lost: [hand.playerValue > 21 ? "Tu dépasses 21" : "Le croupier gagne", "lose"],
  };
  const [text, cls] = messages[hand.status];
  const banner = $("#bj-banner");
  banner.textContent = "";
  banner.className = "bj-banner display";
  const show = () => {
    if (state.page !== "blackjack") return;
    banner.textContent = text;
    banner.className = `bj-banner display ${cls}`;
    if (hand.status === "blackjack" && animate) flare();
  };
  if (animate && text) setTimeout(show, order * 170 + 380);
  else show();
  if (hand.status !== "playing" && animate) refreshHistory("blackjack");
}

async function deal() {
  if (bj.busy) return;
  const bet = readStake("bj-bet");
  if (!bet) return;
  bj.busy = true;
  try {
    bj.prev = { player: [], dealer: [] };
    draw(await api("blackjack/start", { bet }));
  } catch (err) {
    toast(err.message, "error");
  } finally {
    bj.busy = false;
  }
}

async function action(a) {
  if (bj.busy) return;
  bj.busy = true;
  try {
    draw(await api(`blackjack/${a}`, {}));
  } catch (err) {
    toast(err.message, "error");
  } finally {
    bj.busy = false;
  }
}

gamePage("blackjack", render);
