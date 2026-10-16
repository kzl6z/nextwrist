/* Dragon Tiger : une carte pour chaque côté, la plus haute gagne */
import { $, $$, api, fmt, setBalance, sleep, state, toast, tok, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { cardHtml } from "./cards.js";
import { chipsHtml } from "./chips.js";

const dt = { chip: 10, bets: { dragon: 0, tie: 0, tiger: 0 }, busy: false, road: [] };
const LABEL = { dragon: "Dragon", tiger: "Tigre", tie: "Égalité" };
const NOTE = { dragon: "paie 1 pour 1", tie: "paie 12 pour 1", tiger: "paie 1 pour 1" };
const total = () => dt.bets.dragon + dt.bets.tie + dt.bets.tiger;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "dragontiger",
    stageClass: "felt-stage",
    controls: `
      <div><div class="label">Jeton</div>${chipsHtml("dt-chips", dt.chip)}</div>
      <div class="rl-actions"><button class="btn btn-sm" id="dt-clear">Effacer les mises</button></div>
      <div class="info-list"><div><span>Mise totale</span><b id="dt-total">0</b></div></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="dt-deal">Distribuer</button>`,
    stage: `
      <div class="table-felt dt-table">
        <div class="dt-duel">
          <div class="dt-side" id="dt-d"><div class="dt-title display">Dragon</div><div class="cards dt-slot" id="dt-dc">${cardHtml("??")}</div></div>
          <div class="dt-vs display">contre</div>
          <div class="dt-side" id="dt-t"><div class="dt-title display">Tigre</div><div class="cards dt-slot" id="dt-tc">${cardHtml("??")}</div></div>
        </div>
        <div class="bj-banner display" id="dt-banner"></div>
        <div class="bac-zones" id="dt-zones">
          ${["dragon", "tie", "tiger"].map((k) => `<button class="bac-zone" data-zone="${k}"><b>${LABEL[k]}</b><small>${NOTE[k]}</small><span class="zone-chip" id="dt-z-${k}"></span></button>`).join("")}
        </div>
        <div class="bac-road" id="dt-road"></div>
      </div>
      <div class="result-line" id="dt-result"></div>`,
    rules: `<p>Une seule carte est tirée pour le Dragon et une pour le Tigre, depuis un sabot de huit jeux. La plus haute gagne ; l'as est la plus basse, le roi la plus haute. Les couleurs ne comptent pas.</p>
      <p>En cas d'égalité, les mises Dragon et Tigre perdent la moitié ; la mise Égalité paie 12 pour 1.</p>`,
  });
  $("#dt-chips").addEventListener("click", (e) => {
    const c = e.target.closest("[data-chip]");
    if (!c) return;
    dt.chip = Number(c.dataset.chip);
    $$("#dt-chips .chip-token").forEach((x) => x.classList.toggle("active", x === c));
  });
  $("#dt-zones").addEventListener("click", (e) => {
    const z = e.target.closest("[data-zone]");
    if (!z || dt.busy) return;
    if (total() + dt.chip > state.balance) return toast("Solde insuffisant pour ajouter ce jeton", "error");
    if (total() + dt.chip > 10_000) return toast("La mise totale est limitée à 10 000 jetons", "error");
    dt.bets[z.dataset.zone] += dt.chip;
    paintBets();
  });
  $("#dt-clear").addEventListener("click", () => {
    if (dt.busy) return;
    dt.bets = { dragon: 0, tie: 0, tiger: 0 };
    paintBets();
  });
  $("#dt-deal").addEventListener("click", deal);
  paintBets();
  paintRoad();
}

function paintBets() {
  for (const k of ["dragon", "tie", "tiger"]) {
    const el = $(`#dt-z-${k}`);
    el.textContent = dt.bets[k] ? fmt(dt.bets[k]) : "";
    el.classList.toggle("on", !!dt.bets[k]);
  }
  $("#dt-total").innerHTML = tok(total());
  const btn = $("#dt-deal");
  btn.disabled = !total() || dt.busy;
  btn.textContent = total() ? `Distribuer pour ${fmt(total())} jetons` : "Place une mise sur le tapis";
}

function paintRoad() {
  $("#dt-road").innerHTML = dt.road.map((w) => `<span class="road ${w === "dragon" ? "banker" : w === "tiger" ? "player" : "tie"}">${w === "dragon" ? "D" : w === "tiger" ? "T" : "É"}</span>`).join("");
}

async function deal() {
  if (dt.busy || !total()) return;
  dt.busy = true;
  paintBets();
  banner($("#dt-result"), "");
  const bannerEl = $("#dt-banner");
  bannerEl.textContent = "";
  bannerEl.className = "bj-banner display";
  $$(".dt-side").forEach((h) => h.classList.remove("winner"));
  $("#dt-dc").innerHTML = cardHtml("??");
  $("#dt-tc").innerHTML = cardHtml("??");
  try {
    const r = await api("dragontiger", { bets: dt.bets });
    setBalance(r.balance - r.payout);
    await sleep(250);
    $("#dt-dc").innerHTML = cardHtml(r.dragon, { animate: true });
    await sleep(520);
    if (state.page !== "dragontiger") return;
    $("#dt-tc").innerHTML = cardHtml(r.tiger, { animate: true });
    await sleep(480);
    setBalance(r.balance);
    if (r.winner !== "tie") $(r.winner === "dragon" ? "#dt-d" : "#dt-t").classList.add("winner");
    bannerEl.textContent = r.winner === "tie" ? "Égalité" : `${LABEL[r.winner]} gagne`;
    bannerEl.className = `bj-banner display ${r.payout > r.total ? "win" : r.payout ? "" : "lose"}`;
    banner($("#dt-result"), r.payout ? `Retour : <b>${fmt(r.payout)}</b> jetons pour ${fmt(r.total)} misés` : `Mise de ${fmt(r.total)} jetons perdue`, r.payout > r.total ? "win" : "lose");
    dt.road = [...dt.road, r.winner].slice(-24);
    paintRoad();
    refreshHistory("dragontiger");
    if (r.winner === "tie" && dt.bets.tie) flare();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    dt.busy = false;
    if (state.page === "dragontiger") paintBets();
  }
}

gamePage("dragontiger", render);
