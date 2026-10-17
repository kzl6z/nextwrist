/* Diamonds : cinq gemmes tirées parmi sept, la main forme le multiplicateur */
import { $, $$, api, fmt, mult, onSpace, readStake, setBalance, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { gemSvg } from "../icons.js";

const PAYS = [
  ["five", "Cinq identiques", 50, [0, 0, 0, 0, 0]],
  ["four", "Quatre identiques", 5, [0, 0, 0, 0, 1]],
  ["full", "Full", 4, [0, 0, 0, 1, 1]],
  ["three", "Trois identiques", 3, [0, 0, 0, 1, 2]],
  ["twopair", "Deux paires", 2, [0, 0, 1, 1, 2]],
  ["pair", "Une paire", 0.1, [0, 0, 1, 2, 3]],
];
const dm = { bet: 10, busy: false, gems: [4, 1, 6, 2, 0] };

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "diamonds",
    controls: `<div><div class="label">Mise</div>${stakeInput("dm-bet", dm.bet)}</div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="dm-play">Tirer les gemmes</button><p class="hint"><kbd>Espace</kbd> pour jouer</p>`,
    stage: `
      <div class="dm-stage">
        <div class="dm-row" id="dm-row">${dm.gems.map((g) => `<div class="dm-slot">${gemSvg(g, 64)}</div>`).join("")}</div>
        <div class="result-line" id="dm-result"></div>
        <div class="paytable dm-pays" id="dm-pays">
          ${PAYS.map(([k, label, m, shape]) => `<div class="pay-row" data-hand="${k}"><span class="dm-shape">${shape.map((i) => `<i style="--gc:var(--gem-${i})"></i>`).join("")}</span><span>${label}</span><b>${mult(m)}</b></div>`).join("")}
        </div>
      </div>`,
    rules: `<p>Cinq gemmes sont tirées, chacune parmi sept couleurs (chaque couleur a sa propre taille de pierre). Les gemmes identiques forment une main, comme au poker : paire, deux paires, brelan, full, carré ou cinq identiques.</p>
      <p>L'ordre ne compte pas. Une paire seule rembourse un dixième de la mise.</p>`,
  });
  $("#dm-bet").addEventListener("input", (e) => (dm.bet = e.target.value));
  $("#dm-play").addEventListener("click", play);
  onSpace(play);
}

async function play() {
  if (dm.busy) return;
  const bet = readStake("dm-bet");
  if (!bet) return;
  dm.busy = true;
  $("#dm-play").disabled = true;
  banner($("#dm-result"), "");
  $$("#dm-pays .pay-row").forEach((r) => r.classList.remove("on"));
  const slots = $$("#dm-row .dm-slot");
  slots.forEach((s) => s.classList.remove("match", "in"));
  slots.forEach((s) => s.classList.add("out"));
  try {
    const r = await api("diamonds", { bet });
    setBalance(r.balance - r.payout);
    await sleep(160);
    // Les gemmes identiques sont mises en valeur.
    const counts = r.gems.reduce((m, g) => m.set(g, (m.get(g) ?? 0) + 1), new Map());
    for (let i = 0; i < 5; i++) {
      if (state.page !== "diamonds") return;
      slots[i].innerHTML = gemSvg(r.gems[i], 64);
      slots[i].classList.remove("out");
      slots[i].classList.add("in");
      await sleep(150);
    }
    slots.forEach((s, i) => counts.get(r.gems[i]) > 1 && s.classList.add("match"));
    dm.gems = r.gems;
    setBalance(r.balance);
    $(`#dm-pays [data-hand="${r.hand}"]`)?.classList.add("on");
    const name = PAYS.find(([k]) => k === r.hand)?.[1];
    if (r.payout > bet) banner($("#dm-result"), `${name} : <b>+${fmt(r.payout)}</b> jetons, ${mult(r.multiplier)}`, "win");
    else if (r.payout) banner($("#dm-result"), `${name} : ${fmt(r.payout)} jeton${r.payout > 1 ? "s" : ""} rendu${r.payout > 1 ? "s" : ""}`, "lose");
    else banner($("#dm-result"), "Aucune gemme identique", "lose");
    if (r.multiplier >= 5) flare();
    refreshHistory("diamonds");
  } catch (err) {
    slots.forEach((s) => s.classList.remove("out"));
    toast(err.message, "error");
  } finally {
    dm.busy = false;
    if (state.page === "diamonds") $("#dm-play").disabled = false;
  }
}

gamePage("diamonds", render);
