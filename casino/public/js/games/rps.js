/* Pierre-feuille-ciseaux : chaque victoire double le gain, l'égalité se rejoue */
import { $, $$, api, fmt, mult, readStake, setBalance, setStakeDisabled, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { RPS_ART } from "../icons.js";

const NAME = { rock: "Pierre", paper: "Feuille", scissors: "Ciseaux" };
const MOVES = ["rock", "paper", "scissors"];
const rp = { bet: 10, game: null, busy: false };
const rpsMult = (w) => Math.floor(0.98 * 2 ** w * 10_000) / 10_000;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "rps",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("rp-bet", rp.bet)}</div>
      <div class="info-list" id="rp-info"></div>`,
    action: `<div class="label" id="rp-label">Choisis ton coup pour jouer</div>
      <div class="rp-moves" id="rp-moves">${MOVES.map((m) => `<button class="rp-move" data-m="${m}">${RPS_ART[m]}<span>${NAME[m]}</span></button>`).join("")}</div>
      <button class="btn btn-win btn-lg btn-block hidden" id="rp-cash" style="margin-top:8px">Encaisser</button>`,
    stage: `
      <div class="rp-stage">
        <div class="rp-duel">
          <div class="rp-hand" id="rp-you"><small>Toi</small><div class="rp-face">${RPS_ART.rock}</div></div>
          <div class="rp-vs display">contre</div>
          <div class="rp-hand house" id="rp-house"><small>La maison</small><div class="rp-face">${RPS_ART.rock}</div></div>
        </div>
        <div class="result-line" id="rp-result"></div>
        <div class="cf-ladder" id="rp-ladder"></div>
        <div class="rp-trail" id="rp-trail"></div>
      </div>`,
    rules: `<p>La pierre bat les ciseaux, les ciseaux battent la feuille, la feuille bat la pierre. La maison joue au hasard.</p>
      <p>Chaque victoire double ton multiplicateur ; une égalité se rejoue sans rien changer ; une défaite fait perdre la mise. Encaisse quand tu veux, 15 victoires d'affilée encaissent automatiquement.</p>`,
  });
  $("#rp-bet").addEventListener("input", (e) => (rp.bet = e.target.value));
  $("#rp-moves").addEventListener("click", (e) => {
    const b = e.target.closest("[data-m]");
    if (b) play(b.dataset.m);
  });
  $("#rp-cash").addEventListener("click", cashout);
  paint();
  api("rps")
    .then((d) => {
      if (state.page !== "rps") return;
      setBalance(d.balance);
      rp.game = d.game;
      paint();
    })
    .catch((err) => toast(err.message, "error"));
}

function paint() {
  const g = rp.game;
  const playing = g?.status === "playing";
  const wins = playing ? g.steps : 0;
  setStakeDisabled("rp-bet", playing);
  $("#rp-label").textContent = playing ? "Coup suivant" : "Choisis ton coup pour jouer";
  const cash = $("#rp-cash");
  cash.classList.toggle("hidden", !playing);
  cash.disabled = !wins;
  cash.textContent = wins ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Gagne une manche pour encaisser";
  $("#rp-info").innerHTML = playing
    ? `<div><span>Victoires</span><b>${wins}</b></div><div><span>Multiplicateur actuel</span><b>${mult(g.multiplier)}</b></div><div><span>À la prochaine victoire</span><b>${mult(g.next)}</b></div>`
    : `<div><span>Première victoire</span><b>${mult(rpsMult(1))}</b></div><div><span>Chances par coup</span><b>1/3 · 1/3 · 1/3</b></div>`;
  $("#rp-ladder").innerHTML = Array.from({ length: 8 }, (_, i) => `<span class="${i < wins ? "on" : i === wins && playing ? "next" : ""}">${mult(rpsMult(i + 1))}</span>`).join("");
  const rounds = g?.rounds?.slice(-14) ?? [];
  $("#rp-trail").innerHTML = rounds.map((r) => `<span class="rp-past ${r.result}" title="${NAME[r.you]} contre ${NAME[r.house]}">${RPS_ART[r.you]}</span>`).join("");
}

async function play(move) {
  if (rp.busy) return;
  const playing = rp.game?.status === "playing";
  let bet = 0;
  if (!playing) {
    bet = readStake("rp-bet");
    if (!bet) return;
  }
  rp.busy = true;
  $$("#rp-moves .rp-move").forEach((b) => (b.disabled = true));
  banner($("#rp-result"), "");
  const you = $("#rp-you");
  const house = $("#rp-house");
  you.className = "rp-hand";
  house.className = "rp-hand house";
  you.querySelector(".rp-face").innerHTML = RPS_ART.rock;
  house.querySelector(".rp-face").innerHTML = RPS_ART.rock;
  you.classList.add("shaking");
  house.classList.add("shaking");
  try {
    const d = playing ? await api("rps/play", { move }) : await api("rps/start", { bet, move });
    if (!playing) setBalance(d.balance - (d.game.payout ?? 0));
    await sleep(900);
    if (state.page !== "rps") return;
    const last = d.game.rounds[d.game.rounds.length - 1];
    you.classList.remove("shaking");
    house.classList.remove("shaking");
    you.querySelector(".rp-face").innerHTML = RPS_ART[last.you];
    house.querySelector(".rp-face").innerHTML = RPS_ART[last.house];
    you.classList.add(last.result === "win" ? "win" : last.result === "lose" ? "lose" : "draw");
    house.classList.add(last.result === "lose" ? "win" : last.result === "win" ? "lose" : "draw");
    setBalance(d.balance);
    rp.game = d.game;
    paint();
    if (d.game.status === "lost") {
      banner($("#rp-result"), `${NAME[last.house]} bat ${NAME[last.you].toLowerCase()} : mise perdue`, "lose");
      refreshHistory("rps");
    } else if (d.game.status === "won") {
      banner($("#rp-result"), `Quinze victoires : <b>+${fmt(d.game.payout)}</b> jetons`, "win");
      flare();
      refreshHistory("rps");
    } else if (last.result === "draw") banner($("#rp-result"), "Égalité : on rejoue");
    else banner($("#rp-result"), `${NAME[last.you]} bat ${NAME[last.house].toLowerCase()} : ${mult(d.game.multiplier)}`, "win");
  } catch (err) {
    you.classList.remove("shaking");
    house.classList.remove("shaking");
    toast(err.message, "error");
  } finally {
    rp.busy = false;
    $$("#rp-moves .rp-move").forEach((b) => (b.disabled = false));
  }
}

async function cashout() {
  if (rp.busy || rp.game?.status !== "playing") return;
  rp.busy = true;
  try {
    const d = await api("rps/cashout", {});
    setBalance(d.balance);
    rp.game = d.game;
    paint();
    banner($("#rp-result"), `<b>+${fmt(d.game.payout)}</b> jetons encaissés, ${mult(d.game.multiplier)}`, "win");
    if (d.game.multiplier >= 7) flare();
    refreshHistory("rps");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    rp.busy = false;
  }
}

gamePage("rps", render);
