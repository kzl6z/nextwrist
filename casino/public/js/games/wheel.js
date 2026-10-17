/* Roue : 30 cases, trois niveaux de risque */
import { mult, $, api, fmt, fmtDec, onSpace, readStake, setBalance, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";

const wh = { bet: 10, risk: "medium", rot: 0, busy: false, config: null };
const RISKS = [
  ["low", "Faible"],
  ["medium", "Moyen"],
  ["high", "Élevé"],
];
/** Teinte de chaque multiplicateur : du brun mat (0) au laiton clair. */
function tint(m) {
  if (m === 0) return "#171a18";
  const k = Math.min(1, Math.log(m) / Math.log(30));
  const l = 34 + k * 34;
  return `hsl(39 ${34 + k * 18}% ${l}%)`;
}

async function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "wheel",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("wh-bet", wh.bet)}</div>
      <div><div class="label">Risque</div><div class="seg" id="wh-risk">${RISKS.map(([k, l]) => `<button data-risk="${k}">${l}</button>`).join("")}</div></div>
`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="wh-spin">Faire tourner</button>
      <p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="wheel-game">
        <div class="fw-wrap">
          <div class="fw-pointer"></div>
          <div class="fw-spin" id="wh-wheel"></div>
          <div class="fw-center display" id="wh-center"></div>
        </div>
        <div class="fw-legend" id="wh-legend"></div>
        <div class="result-line" id="wh-result"></div>
      </div>`,
    rules: `<p>La roue compte 30 cases. Celle qui s'arrête sous le repère multiplie ta mise : ×0 fait perdre la mise.</p>
      <p>En risque faible, la plupart des cases paient un peu. En risque élevé, une seule case paie, mais ×29,6.</p>`,
  });
  $("#wh-bet").addEventListener("input", (e) => (wh.bet = e.target.value));
  $("#wh-risk").addEventListener("click", (e) => {
    const b = e.target.closest("[data-risk]");
    if (!b || wh.busy) return;
    wh.risk = b.dataset.risk;
    paint();
  });
  $("#wh-spin").addEventListener("click", spin);
  onSpace(spin);
  try {
    wh.config = (await casinoConfig()).wheel;
    paint();
  } catch (err) {
    toast(err.message, "error");
  }
}

function wheelSvg(segments) {
  const n = segments.length;
  const c = 160;
  const R = 152;
  const r0 = 112;
  const seg = 360 / n;
  const pt = (rad, deg) => {
    const a = (deg * Math.PI) / 180;
    return `${(c + rad * Math.sin(a)).toFixed(2)} ${(c - rad * Math.cos(a)).toFixed(2)}`;
  };
  return `<svg viewBox="0 0 320 320" aria-hidden="true">
    <circle cx="${c}" cy="${c}" r="158" fill="#0b0c0b" stroke="#b8955a" stroke-width="1.2"/>
    ${segments
      .map((m, i) => {
        const a0 = i * seg - seg / 2 + 0.6;
        const a1 = i * seg + seg / 2 - 0.6;
        return `<path d="M${pt(R, a0)}A${R} ${R} 0 0 1 ${pt(R, a1)}L${pt(r0, a1)}A${r0} ${r0} 0 0 0 ${pt(r0, a0)}Z" fill="${tint(m)}"/>`;
      })
      .join("")}
    <circle cx="${c}" cy="${c}" r="${r0 - 6}" fill="#0e100f" stroke="#b8955a" stroke-width=".6" opacity=".9"/>
  </svg>`;
}

function paint() {
  if (state.page !== "wheel" || !wh.config) return;
  const segments = wh.config[wh.risk];
  document.querySelectorAll("#wh-risk [data-risk]").forEach((b) => b.classList.toggle("active", b.dataset.risk === wh.risk));
  $("#wh-wheel").innerHTML = wheelSvg(segments);
  $("#wh-wheel").style.transform = `rotate(${wh.rot}deg)`;
  const counts = new Map();
  for (const m of segments) counts.set(m, (counts.get(m) ?? 0) + 1);
  $("#wh-legend").innerHTML = [...counts]
    .sort((a, b) => a[0] - b[0])
    .map(([m, n]) => `<div class="fw-key" data-m="${m}"><i style="background:${tint(m)}"></i><b>${mult(m)}</b><span>${n} case${n > 1 ? "s" : ""}</span></div>`)
    .join("");
}

async function spin() {
  if (wh.busy || !wh.config) return;
  const bet = readStake("wh-bet");
  if (!bet) return;
  wh.busy = true;
  $("#wh-spin").disabled = true;
  banner($("#wh-result"), "");
  $("#wh-center").textContent = "";
  document.querySelectorAll(".fw-key").forEach((k) => k.classList.remove("hit"));
  try {
    const r = await api("wheel", { bet, risk: wh.risk });
    setBalance(r.balance - r.payout);
    const n = wh.config[wh.risk].length;
    const seg = 360 / n;
    const target = (((-r.index * seg) % 360) + 360) % 360;
    const jitter = (Math.random() - 0.5) * seg * 0.7;
    wh.rot = Math.ceil(wh.rot / 360) * 360 + 360 * 5 + target + jitter;
    $("#wh-wheel").style.transform = `rotate(${wh.rot}deg)`;
    await sleep(4200);
    setBalance(r.balance);
    if (state.page !== "wheel") return;
    $("#wh-center").textContent = mult(r.multiplier);
    document.querySelector(`.fw-key[data-m="${r.multiplier}"]`)?.classList.add("hit");
    banner($("#wh-result"), r.payout ? `<b>+${fmt(r.payout)}</b> jetons` : "Case ×0 : mise perdue", r.payout >= bet ? "win" : "lose");
    refreshHistory("wheel");
    if (r.multiplier >= 4) flare();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    wh.busy = false;
    if (state.page === "wheel") $("#wh-spin").disabled = false;
  }
}

gamePage("wheel", render);
