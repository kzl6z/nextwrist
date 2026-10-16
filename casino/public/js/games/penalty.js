/* Penalty : choisis un coin du but, le gardien plonge */
import { $, $$, api, fmt, mult, readStake, setBalance, setStakeDisabled, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const MODES = { normal: { label: "Normal", keepers: 1, kicks: 10 }, hard: { label: "Difficile", keepers: 2, kicks: 8 } };
/** Centres des cinq zones dans le but (viewBox 400×220) : haut gauche, haut droite, centre, bas gauche, bas droite. */
const ZONES = [
  [78, 62, "en haut à gauche"],
  [322, 62, "en haut à droite"],
  [200, 112, "au centre"],
  [78, 160, "en bas à gauche"],
  [322, 160, "en bas à droite"],
];
const pn = { bet: 10, mode: "normal", game: null, busy: false };
const chance = (m) => (5 - MODES[m].keepers) / 5;
const ladder = (m) => Array.from({ length: MODES[m].kicks }, (_, i) => Math.floor((0.97 / chance(m) ** (i + 1)) * 10_000) / 10_000);

const KEEPER = `<g class="pn-keeper" id="pn-keeper">
  <circle cx="0" cy="-46" r="11" fill="#ece6d6"/>
  <path d="M-16 -34h32l4 34h-40z" fill="#c9a96a" stroke="#070807" stroke-width="1.5"/>
  <path d="M-16 -30l-20 -20M16 -30l20 -20" stroke="#c9a96a" stroke-width="7" stroke-linecap="round"/>
  <circle cx="-38" cy="-52" r="6" fill="#ece6d6"/><circle cx="38" cy="-52" r="6" fill="#ece6d6"/>
  <path d="M-10 0l-4 30M10 0l4 30" stroke="#1b1f1c" stroke-width="8" stroke-linecap="round"/>
</g>`;

function goalSvg() {
  const net = [];
  for (let x = 20; x <= 380; x += 20) net.push(`<path d="M${x} 20V210"/>`);
  for (let y = 30; y <= 210; y += 20) net.push(`<path d="M20 ${y}H380"/>`);
  return `<svg viewBox="0 0 400 300" class="pn-svg" aria-hidden="false">
    <rect x="0" y="210" width="400" height="90" fill="#0f3a2c"/>
    <path d="M0 210H400" stroke="rgba(236,230,214,.35)" stroke-width="2"/>
    <ellipse cx="200" cy="268" rx="5" ry="2.4" fill="rgba(236,230,214,.6)"/>
    <g stroke="rgba(236,230,214,.12)" stroke-width="1">${net.join("")}</g>
    <path d="M14 212V14H386V212" fill="none" stroke="#ece6d6" stroke-width="7" stroke-linejoin="round"/>
    ${ZONES.map(([x, y, label], i) => `<g class="pn-zone" data-z="${i}" role="button" tabindex="0" aria-label="Tirer ${label}"><circle cx="${x}" cy="${y}" r="34"/><circle cx="${x}" cy="${y}" r="5" class="dot"/></g>`).join("")}
    <g transform="translate(200 206)" id="pn-keeper-pos">${KEEPER}</g>
    <g id="pn-ball" style="transform:translate(200px,266px)"><circle r="11" fill="#ece6d6" stroke="#070807" stroke-width="1.4"/><path d="M0 -6l5 4-2 6h-6l-2-6z" fill="#070807"/></g>
  </svg>`;
}

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "penalty",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("pn-bet", pn.bet)}</div>
      <div><div class="label">Gardien</div><div class="seg" id="pn-mode">${Object.entries(MODES).map(([k, m]) => `<button data-m="${k}">${m.label}</button>`).join("")}</div></div>
      <div class="info-list" id="pn-info"></div>`,
    action: `<p class="label" id="pn-hint">Clique sur un coin du but pour tirer</p><button class="btn btn-win btn-lg btn-block hidden" id="pn-cash">Encaisser</button>`,
    stage: `
      <div class="pn-stage">
        <div class="pn-goal" id="pn-goal">${goalSvg()}</div>
        <div class="pn-kicks" id="pn-kicks"></div>
        <div class="cf-ladder" id="pn-ladder"></div>
        <div class="result-line" id="pn-result"></div>
      </div>`,
    rules: `<p>Choisis un des cinq coins du but et tire. Le gardien plonge au hasard : en mode normal il couvre une zone (4 chances sur 5 de marquer), en mode difficile deux zones (3 chances sur 5).</p>
      <p>Chaque but augmente le multiplicateur. Encaisse quand tu veux ; un arrêt fait perdre la mise. La série s'arrête et encaisse automatiquement après 10 tirs (8 en difficile).</p>`,
  });
  $("#pn-bet").addEventListener("input", (e) => (pn.bet = e.target.value));
  $("#pn-mode").addEventListener("click", (e) => {
    const b = e.target.closest("[data-m]");
    if (!b || pn.game?.status === "playing") return;
    pn.mode = b.dataset.m;
    pn.game = null;
    paint();
  });
  $("#pn-goal").addEventListener("click", (e) => {
    const z = e.target.closest("[data-z]");
    if (z) shoot(Number(z.dataset.z));
  });
  $("#pn-goal").addEventListener("keydown", (e) => {
    const z = e.target.closest("[data-z]");
    if (z && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      shoot(Number(z.dataset.z));
    }
  });
  $("#pn-cash").addEventListener("click", cashout);
  paint();
  api("penalty")
    .then((d) => {
      if (state.page !== "penalty") return;
      setBalance(d.balance);
      pn.game = d.game;
      if (d.game) pn.mode = d.game.mode;
      paint();
    })
    .catch((err) => toast(err.message, "error"));
}

function paint() {
  const g = pn.game?.mode === pn.mode ? pn.game : null;
  const playing = g?.status === "playing";
  const m = MODES[pn.mode];
  const goals = g?.steps ?? 0;
  $$("#pn-mode [data-m]").forEach((b) => {
    b.classList.toggle("active", b.dataset.m === pn.mode);
    b.disabled = playing;
  });
  setStakeDisabled("pn-bet", playing);
  const cash = $("#pn-cash");
  cash.classList.toggle("hidden", !playing);
  cash.disabled = !goals;
  cash.textContent = goals ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Marque d'abord un but";
  $("#pn-hint").textContent = playing ? "Tir suivant : choisis un coin" : "Clique sur un coin du but pour tirer";
  $("#pn-info").innerHTML = `<div><span>Chance de marquer</span><b>${Math.round(chance(pn.mode) * 100)} %</b></div><div><span>Tirs au maximum</span><b>${m.kicks}</b></div>`;
  $("#pn-kicks").innerHTML = Array.from({ length: m.kicks }, (_, i) => {
    const k = g?.kicks[i];
    return `<span class="${k ? (k.goal ? "goal" : "miss") : ""}"></span>`;
  }).join("");
  const lad = g?.ladder ?? ladder(pn.mode);
  $("#pn-ladder").innerHTML = lad.map((x, i) => `<span class="${i < goals ? "on" : i === goals && playing ? "next" : ""}">${mult(x)}</span>`).join("");
}

function resetPitch() {
  const ball = $("#pn-ball");
  const keeper = $("#pn-keeper");
  ball.style.transition = "none";
  ball.style.transform = "translate(200px,266px)";
  keeper.style.transition = "none";
  keeper.style.transform = "none";
  $$("#pn-goal .pn-zone").forEach((z) => z.classList.remove("saved", "scored", "covered"));
  void ball.getBoundingClientRect();
  ball.style.transition = "";
  keeper.style.transition = "";
}

async function shoot(zone) {
  if (pn.busy) return;
  const playing = pn.game?.status === "playing" && pn.game.mode === pn.mode;
  pn.busy = true;
  try {
    let d;
    if (!playing) {
      const bet = readStake("pn-bet");
      if (!bet) return;
      banner($("#pn-result"), "");
      const s = await api("penalty/start", { bet, mode: pn.mode });
      setBalance(s.balance);
      pn.game = s.game;
      paint();
    }
    d = await api("penalty/shoot", { zone });
    resetPitch();
    const kick = d.game.kicks[d.game.kicks.length - 1];
    // Le gardien plonge vers sa (première) zone, le ballon part vers la zone choisie.
    const [kx, ky] = ZONES[kick.dive[0]];
    const dx = kx - 200;
    const rot = dx === 0 ? 0 : dx < 0 ? -62 : 62;
    $("#pn-keeper").style.transform = `translate(${dx * 0.92}px, ${(ky - 206) * 0.55}px) rotate(${rot}deg)`;
    kick.dive.forEach((z) => $(`#pn-goal [data-z="${z}"]`).classList.add("covered"));
    const [bx, by] = ZONES[zone];
    $("#pn-ball").style.transform = `translate(${bx}px, ${by}px) scale(.72)`;
    await sleep(520);
    if (state.page !== "penalty") return;
    $(`#pn-goal [data-z="${zone}"]`).classList.add(kick.goal ? "scored" : "saved");
    setBalance(d.balance);
    pn.game = d.game;
    paint();
    if (d.game.status === "lost") {
      banner($("#pn-result"), "Arrêt du gardien : mise perdue", "lose");
      refreshHistory("penalty");
    } else if (d.game.status === "won") {
      banner($("#pn-result"), `Série parfaite : <b>+${fmt(d.game.payout)}</b> jetons, ${mult(d.game.multiplier)}`, "win");
      flare();
      refreshHistory("penalty");
    } else banner($("#pn-result"), `But ! ${mult(d.game.multiplier)}`, "win");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    pn.busy = false;
  }
}

async function cashout() {
  if (pn.busy || pn.game?.status !== "playing") return;
  pn.busy = true;
  try {
    const d = await api("penalty/cashout", {});
    setBalance(d.balance);
    pn.game = d.game;
    paint();
    banner($("#pn-result"), `<b>+${fmt(d.game.payout)}</b> jetons encaissés, ${mult(d.game.multiplier)}`, "win");
    if (d.game.multiplier >= 5) flare();
    refreshHistory("penalty");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    pn.busy = false;
  }
}

gamePage("penalty", render);
