/* Coffres : choisis un coffre, il s'ouvre sur un multiplicateur */
import { $, $$, api, fmt, mult, readStake, setBalance, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";

const RISKS = { low: "Faible", medium: "Moyen", high: "Élevé" };
const FALLBACK = {
  low: [[0.2, 200], [0.5, 250], [0.9, 240], [1.2, 170], [1.8, 80], [3, 50], [10, 10]],
  medium: [[0, 423], [0.4, 200], [1, 190], [2, 110], [4, 60], [10, 15], [50, 2]],
  high: [[0, 689.6], [0.5, 200], [2, 60], [5, 40], [20, 8], [100, 2], [500, 0.4]],
};
const ch = { bet: 10, risk: "medium", busy: false, table: FALLBACK };

const chestSvg = () => `<svg viewBox="0 0 120 110" class="chest-art" aria-hidden="true">
  <g class="lid"><path d="M10 50c0-24 20-36 50-36s50 12 50 36z" fill="#1b1f1c" stroke="currentColor" stroke-width="2"/><path d="M30 22v28M90 22v28" stroke="currentColor" stroke-width="2" opacity=".55"/></g>
  <rect x="10" y="50" width="100" height="52" rx="4" fill="#141715" stroke="currentColor" stroke-width="2"/>
  <path d="M10 66h100" stroke="currentColor" stroke-width="2" opacity=".55"/><path d="M30 50v52M90 50v52" stroke="currentColor" stroke-width="2" opacity=".55"/>
  <rect x="51" y="56" width="18" height="20" rx="3" fill="#0e100f" stroke="currentColor" stroke-width="2"/><circle cx="60" cy="64" r="2.4" fill="currentColor"/>
</svg>`;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "chest",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("ch-bet", ch.bet)}</div>
      <div><div class="label">Risque</div><div class="seg" id="ch-risk">${Object.entries(RISKS).map(([k, l]) => `<button data-risk="${k}">${l}</button>`).join("")}</div></div>
      <div class="paytable" id="ch-pays"></div>`,
    action: `<p class="label">Choisis un coffre pour l'ouvrir</p><button class="btn btn-gold btn-lg btn-block" id="ch-rand">Coffre au hasard</button>`,
    stage: `
      <div class="ch-stage">
        <div class="ch-row" id="ch-row">${[0, 1, 2].map((i) => `<button class="ch-box" data-i="${i}" aria-label="Coffre ${i + 1}">${chestSvg()}<span class="ch-mult display"></span></button>`).join("")}</div>
        <div class="result-line" id="ch-result"></div>
      </div>`,
    rules: `<p>Choisis un des trois coffres : il s'ouvre sur un multiplicateur appliqué à ta mise. Le contenu est tiré par le serveur au moment de l'ouverture, selon les probabilités affichées.</p>
      <p>En risque faible, presque chaque coffre rend quelque chose. En risque élevé, la plupart sont vides, mais l'un d'eux peut contenir ×500.</p>`,
  });
  $("#ch-bet").addEventListener("input", (e) => (ch.bet = e.target.value));
  $("#ch-risk").addEventListener("click", (e) => {
    const b = e.target.closest("[data-risk]");
    if (!b || ch.busy) return;
    ch.risk = b.dataset.risk;
    paint();
  });
  $("#ch-row").addEventListener("click", (e) => {
    const b = e.target.closest("[data-i]");
    if (b) open(Number(b.dataset.i));
  });
  $("#ch-rand").addEventListener("click", () => open(Math.floor(Math.random() * 3)));
  paint();
  casinoConfig()
    .then((c) => {
      if (c.chests) ch.table = c.chests;
      if (state.page === "chest") paint();
    })
    .catch(() => {});
}

function paint() {
  $$("#ch-risk [data-risk]").forEach((b) => b.classList.toggle("active", b.dataset.risk === ch.risk));
  const t = ch.table[ch.risk];
  const total = t.reduce((s, [, w]) => s + w, 0);
  $("#ch-pays").innerHTML = t
    .slice()
    .reverse()
    .map(([m, w]) => {
      const p = (w / total) * 100;
      return `<div class="pay-row" data-m="${m}"><span>${m ? mult(m) : "Vide"}</span><em>${p < 0.1 ? p.toLocaleString("fr-FR", { maximumFractionDigits: 2 }) : p.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %</em></div>`;
    })
    .join("");
}

async function open(i) {
  if (ch.busy) return;
  const bet = readStake("ch-bet");
  if (!bet) return;
  ch.busy = true;
  $("#ch-rand").disabled = true;
  banner($("#ch-result"), "");
  $$("#ch-pays .pay-row").forEach((r) => r.classList.remove("on"));
  const boxes = $$("#ch-row .ch-box");
  boxes.forEach((b) => {
    b.classList.remove("open", "dim", "big", "empty");
    b.querySelector(".ch-mult").textContent = "";
  });
  const box = boxes[i];
  box.classList.add("shake");
  try {
    const r = await api("chest", { bet, risk: ch.risk });
    setBalance(r.balance - r.payout);
    await sleep(520);
    if (state.page !== "chest") return;
    box.classList.remove("shake");
    box.classList.add("open", r.multiplier >= 2 ? "big" : r.multiplier ? "" : "empty");
    boxes.forEach((b, k) => k !== i && b.classList.add("dim"));
    box.querySelector(".ch-mult").textContent = r.multiplier ? mult(r.multiplier) : "Vide";
    setBalance(r.balance);
    $(`#ch-pays [data-m="${r.multiplier}"]`)?.classList.add("on");
    if (r.payout > bet) banner($("#ch-result"), `<b>+${fmt(r.payout)}</b> jetons, ${mult(r.multiplier)}`, "win");
    else if (r.payout) banner($("#ch-result"), `${mult(r.multiplier)} : ${fmt(r.payout)} jetons rendus`, "lose");
    else banner($("#ch-result"), "Coffre vide : mise perdue", "lose");
    if (r.multiplier >= 10) flare();
    refreshHistory("chest");
  } catch (err) {
    box.classList.remove("shake");
    toast(err.message, "error");
  } finally {
    ch.busy = false;
    if (state.page === "chest") $("#ch-rand").disabled = false;
  }
}

gamePage("chest", render);
