/* Fléchettes : la zone touchée fixe le multiplicateur */
import { $, $$, api, fmt, mult, onSpace, readStake, setBalance, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";

const RISKS = { low: "Faible", medium: "Moyen", high: "Élevé" };
const FALLBACK = {
  low: [[5, 20], [2, 80], [1.5, 170], [1.2, 250], [0.6, 280], [0, 200]],
  medium: [[12, 15], [4, 50], [2, 120], [1.2, 230], [0.3, 280], [0, 305]],
  high: [[60, 5], [12, 20], [3, 70], [1.5, 135], [0.3, 100], [0, 670]],
};
/** Rayons extérieurs des six anneaux (cible de 130 de rayon). */
const RADII = [14, 34, 56, 80, 104, 128];
const da = { bet: 10, risk: "medium", busy: false, table: FALLBACK, recent: [] };

const ringFill = (m) => (m >= 10 ? "#c9a96a" : m >= 2 ? "#8f7543" : m >= 1 ? "#2b302c" : m > 0 ? "#1b1f1c" : "#101311");

function boardSvg() {
  const zones = da.table[da.risk];
  const rings = RADII.map((r, i) => ({ r, inner: i ? RADII[i - 1] : 0, m: zones[i][0] }));
  const sectors = Array.from({ length: 20 }, (_, k) => {
    const a = (k / 20) * Math.PI * 2;
    return `<path d="M${(150 + 14 * Math.cos(a)).toFixed(1)} ${(150 + 14 * Math.sin(a)).toFixed(1)}L${(150 + 128 * Math.cos(a)).toFixed(1)} ${(150 + 128 * Math.sin(a)).toFixed(1)}" stroke="rgba(236,230,214,.07)"/>`;
  }).join("");
  return `<svg viewBox="0 0 300 300" class="dart-board" aria-hidden="true">
    <circle cx="150" cy="150" r="146" fill="#0a0c0b" stroke="rgba(201,169,106,.35)" stroke-width="1.5"/>
    ${rings
      .slice()
      .reverse()
      .map(({ r, m }, j) => `<circle cx="150" cy="150" r="${r}" fill="${ringFill(m)}" stroke="rgba(201,169,106,.4)" stroke-width="1" data-ring="${RADII.length - 1 - j}"/>`)
      .join("")}
    ${sectors}
    ${rings
      .map(({ r, inner, m }, i) => (i === 0 ? "" : `<text x="150" y="${150 - (r + inner) / 2 + 4}" text-anchor="middle" font-size="11" font-weight="600" fill="${m >= 10 ? "#1a1408" : "rgba(236,230,214,.75)"}">${m ? mult(m) : "0"}</text>`))
      .join("")}
    <text x="150" y="154" text-anchor="middle" font-size="9" font-weight="700" fill="#1a1408">${mult(rings[0].m)}</text>
    <g id="da-hits"></g>
    <g id="da-dart" class="dart" style="opacity:0"><path d="M0 0l26 -26" stroke="#ece6d6" stroke-width="2.6" stroke-linecap="round"/><path d="M22 -30l10 -2 -2 10 -6 -2z M26 -22l8 -1" fill="#c9a96a" stroke="#c9a96a" stroke-width="1.2"/><circle r="2.4" fill="#ece6d6"/></g>
  </svg>`;
}

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "darts",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("da-bet", da.bet)}</div>
      <div><div class="label">Risque</div><div class="seg" id="da-risk">${Object.entries(RISKS).map(([k, l]) => `<button data-risk="${k}">${l}</button>`).join("")}</div></div>
      <div class="paytable" id="da-pays"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="da-throw">Lancer la fléchette</button><p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="da-stage">
        <div class="da-recent" id="da-recent"></div>
        <div class="da-wrap" id="da-wrap">${boardSvg()}</div>
        <div class="result-line" id="da-result"></div>
      </div>`,
    rules: `<p>Lance la fléchette : l'anneau touché donne le multiplicateur de ta mise. Plus l'anneau est proche du centre, plus il paie, et plus il est difficile à atteindre.</p>
      <p>Le niveau de risque change la répartition des gains : en risque élevé, la cible est surtout vide, mais le centre paie ×60.</p>`,
  });
  $("#da-bet").addEventListener("input", (e) => (da.bet = e.target.value));
  $("#da-risk").addEventListener("click", (e) => {
    const b = e.target.closest("[data-risk]");
    if (!b || da.busy) return;
    da.risk = b.dataset.risk;
    paint();
  });
  $("#da-throw").addEventListener("click", play);
  onSpace(play);
  paint();
  casinoConfig()
    .then((c) => {
      if (c.darts) da.table = c.darts;
      if (state.page === "darts") paint();
    })
    .catch(() => {});
}

function paint() {
  $$("#da-risk [data-risk]").forEach((b) => b.classList.toggle("active", b.dataset.risk === da.risk));
  $("#da-wrap").innerHTML = boardSvg();
  const zones = da.table[da.risk];
  const total = zones.reduce((s, [, w]) => s + w, 0);
  // Une ligne par multiplicateur distinct (les anneaux vides sont regroupés).
  const rows = new Map();
  for (const [m, w] of zones) rows.set(m, (rows.get(m) ?? 0) + w);
  $("#da-pays").innerHTML = [...rows]
    .map(([m, w]) => `<div class="pay-row" data-m="${m}"><span>${m ? mult(m) : "Raté"}</span><em>${((w / total) * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %</em></div>`)
    .join("");
  paintRecent();
}

function paintRecent() {
  $("#da-recent").innerHTML = da.recent.map((m) => `<span class="hpill ${m >= 2 ? "high" : m >= 1 ? "mid" : "low"}">${mult(m)}</span>`).join("");
}

async function play() {
  if (da.busy) return;
  const bet = readStake("da-bet");
  if (!bet) return;
  da.busy = true;
  $("#da-throw").disabled = true;
  banner($("#da-result"), "");
  $$("#da-pays .pay-row").forEach((r) => r.classList.remove("on"));
  try {
    const r = await api("darts", { bet, risk: da.risk });
    setBalance(r.balance - r.payout);
    // Point d'impact : au hasard dans l'anneau indiqué par le serveur.
    const inner = r.ring ? RADII[r.ring - 1] : 0;
    const rad = inner + 3 + Math.random() * (RADII[r.ring] - inner - 6);
    const a = (r.angle * Math.PI) / 180;
    const x = 150 + rad * Math.cos(a);
    const y = 150 + rad * Math.sin(a);
    const dart = $("#da-dart");
    dart.style.transition = "none";
    dart.style.opacity = "0";
    dart.style.transform = `translate(${x + 120}px, ${y - 140}px) scale(1.8)`;
    void dart.getBoundingClientRect();
    dart.style.transition = "transform .42s cubic-bezier(.3,.7,.3,1), opacity .12s";
    dart.style.opacity = "1";
    dart.style.transform = `translate(${x}px, ${y}px) scale(1)`;
    await sleep(460);
    if (state.page !== "darts") return;
    $("#da-hits").insertAdjacentHTML("beforeend", `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.2" fill="#ece6d6" opacity=".55"/>`);
    $(`#da-wrap [data-ring="${r.ring}"]`)?.classList.add("hit");
    setBalance(r.balance);
    $(`#da-pays [data-m="${r.multiplier}"]`)?.classList.add("on");
    da.recent = [r.multiplier, ...da.recent].slice(0, 10);
    paintRecent();
    if (r.payout > bet) banner($("#da-result"), `<b>+${fmt(r.payout)}</b> jetons, ${mult(r.multiplier)}`, "win");
    else if (r.payout) banner($("#da-result"), `${mult(r.multiplier)} : ${fmt(r.payout)} jetons rendus`, "lose");
    else banner($("#da-result"), "Zone vide : mise perdue", "lose");
    if (r.multiplier >= 10) flare();
    refreshHistory("darts");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    da.busy = false;
    if (state.page === "darts") $("#da-throw").disabled = false;
  }
}

gamePage("darts", render);
