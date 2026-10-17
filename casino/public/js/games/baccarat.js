/* Baccarat (punto banco) : joueur, banquier ou égalité */
import { $, $$, api, fmt, setBalance, sleep, state, toast, tok, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { cardHtml } from "./cards.js";

const CHIPS = [
  [5, "#9c3a30"],
  [10, "#3d5a73"],
  [25, "#2f6b4f"],
  [100, "#1d1f1e"],
  [500, "#b8955a"],
];
const bc = { chip: 10, bets: { player: 0, tie: 0, banker: 0 }, busy: false, road: [] };
const LABEL = { player: "Joueur", banker: "Banquier", tie: "Égalité" };
const total = () => bc.bets.player + bc.bets.tie + bc.bets.banker;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "baccarat",
    stageClass: "felt-stage",
    controls: `
      <div><div class="label">Jeton</div><div class="chips-row" id="bc-chips">${CHIPS.map(([v, c]) => `<button class="chip-token ${v === bc.chip ? "active" : ""}" style="--c:${c}" data-chip="${v}">${v}</button>`).join("")}</div></div>
      <div class="rl-actions"><button class="btn btn-sm" id="bc-clear">Effacer les mises</button></div>
      <div class="info-list"><div><span>Mise totale</span><b id="bc-total">0</b></div></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="bc-deal">Distribuer</button>`,
    stage: `
      <div class="table-felt bac">
        <div class="bac-hands">
          <div class="bac-hand" id="bc-p"><div class="hand-label">Joueur <span class="hand-value" id="bc-pt"></span></div><div class="cards" id="bc-pc"></div></div>
          <div class="bac-hand" id="bc-b"><div class="hand-label">Banquier <span class="hand-value" id="bc-bt"></span></div><div class="cards" id="bc-bc"></div></div>
        </div>
        <div class="bj-banner display" id="bc-banner"></div>
        <div class="bac-zones" id="bc-zones">
          ${["player", "tie", "banker"].map((k) => `<button class="bac-zone" data-zone="${k}"><b>${LABEL[k]}</b><small>${k === "tie" ? "paie 8 pour 1" : k === "banker" ? "paie 0,95 pour 1" : "paie 1 pour 1"}</small><span class="zone-chip" id="bc-z-${k}"></span></button>`).join("")}
        </div>
        <div class="bac-road" id="bc-road"></div>
      </div>
      <div class="result-line" id="bc-result"></div>`,
    rules: `<p>Mise sur la main qui finira le plus près de 9 : joueur ou banquier, ou sur l'égalité. Les figures et les 10 valent 0, l'as vaut 1 ; seul le chiffre des unités compte.</p>
      <p>Une troisième carte est tirée selon les règles officielles. En cas d'égalité, les mises sur joueur et banquier sont rendues.</p>`,
  });
  $("#bc-chips").addEventListener("click", (e) => {
    const c = e.target.closest("[data-chip]");
    if (!c) return;
    bc.chip = Number(c.dataset.chip);
    $$("#bc-chips .chip-token").forEach((x) => x.classList.toggle("active", x === c));
  });
  $("#bc-zones").addEventListener("click", (e) => {
    const z = e.target.closest("[data-zone]");
    if (!z || bc.busy) return;
    if (total() + bc.chip > state.balance) return toast("Solde insuffisant pour ajouter ce jeton", "error");
    if (total() + bc.chip > 10_000) return toast("La mise totale est limitée à 10 000 jetons", "error");
    bc.bets[z.dataset.zone] += bc.chip;
    paintBets();
  });
  $("#bc-clear").addEventListener("click", () => {
    if (bc.busy) return;
    bc.bets = { player: 0, tie: 0, banker: 0 };
    paintBets();
  });
  $("#bc-deal").addEventListener("click", deal);
  paintBets();
  paintRoad();
}

function paintBets() {
  for (const k of ["player", "tie", "banker"]) {
    const el = $(`#bc-z-${k}`);
    el.textContent = bc.bets[k] ? fmt(bc.bets[k]) : "";
    el.classList.toggle("on", !!bc.bets[k]);
  }
  $("#bc-total").innerHTML = tok(total());
  const btn = $("#bc-deal");
  btn.disabled = !total() || bc.busy;
  btn.textContent = total() ? `Distribuer pour ${fmt(total())} jetons` : "Place une mise sur le tapis";
}

function paintRoad() {
  $("#bc-road").innerHTML = bc.road.map((w) => `<span class="road ${w}">${w === "player" ? "J" : w === "banker" ? "B" : "É"}</span>`).join("");
}

async function deal() {
  if (bc.busy || !total()) return;
  bc.busy = true;
  paintBets();
  banner($("#bc-result"), "");
  const bannerEl = $("#bc-banner");
  bannerEl.textContent = "";
  bannerEl.className = "bj-banner display";
  $$(".bac-hand").forEach((h) => h.classList.remove("winner"));
  ["#bc-pc", "#bc-bc"].forEach((s) => ($(s).innerHTML = ""));
  ["#bc-pt", "#bc-bt"].forEach((s) => ($(s).textContent = ""));
  try {
    const r = await api("baccarat", { bets: bc.bets });
    setBalance(r.balance - r.payout);
    // Distribution dans l'ordre : joueur, banquier, joueur, banquier, puis troisièmes cartes.
    const order = [
      ["#bc-pc", r.player[0]],
      ["#bc-bc", r.banker[0]],
      ["#bc-pc", r.player[1]],
      ["#bc-bc", r.banker[1]],
    ];
    if (r.player[2]) order.push(["#bc-pc", r.player[2]]);
    if (r.banker[2]) order.push(["#bc-bc", r.banker[2]]);
    for (const [sel, card] of order) {
      if (state.page !== "baccarat") return;
      $(sel).insertAdjacentHTML("beforeend", cardHtml(card, { animate: true }));
      await sleep(330);
    }
    $("#bc-pt").textContent = r.playerTotal;
    $("#bc-bt").textContent = r.bankerTotal;
    setBalance(r.balance);
    if (r.winner !== "tie") $(r.winner === "player" ? "#bc-p" : "#bc-b").classList.add("winner");
    bannerEl.textContent = r.winner === "tie" ? "Égalité" : `${LABEL[r.winner]} gagne`;
    bannerEl.className = `bj-banner display ${r.payout > r.total ? "win" : r.payout ? "" : "lose"}`;
    banner($("#bc-result"), r.payout ? `Retour : <b>${fmt(r.payout)}</b> jetons pour ${fmt(r.total)} misés` : `Mise de ${fmt(r.total)} jetons perdue`, r.payout > r.total ? "win" : "lose");
    bc.road = [...bc.road, r.winner].slice(-24);
    paintRoad();
    refreshHistory("baccarat");
    if (r.winner === "tie" && bc.bets.tie) flare();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    bc.busy = false;
    if (state.page === "baccarat") paintBets();
  }
}

gamePage("baccarat", render);
