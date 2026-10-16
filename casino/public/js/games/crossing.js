/* Traversée : avance voie après voie, encaisse avant de te faire faucher */
import { $, $$, api, fmt, mult, onSpace, readStake, setBalance, setStakeDisabled, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const MODES = {
  easy: { label: "Facile", p: 0.92, lanes: 24 },
  medium: { label: "Moyen", p: 0.84, lanes: 20 },
  hard: { label: "Difficile", p: 0.72, lanes: 16 },
  expert: { label: "Expert", p: 0.6, lanes: 12 },
};
const LANE_W = 86;
const CURB_W = 74;
const cr = { bet: 10, mode: "medium", game: null, busy: false };
const ladder = (m) => Array.from({ length: MODES[m].lanes }, (_, i) => Math.floor((0.98 / MODES[m].p ** (i + 1)) * 10_000) / 10_000);

const CAR = `<svg viewBox="0 0 40 70" class="car-art" aria-hidden="true"><rect x="4" y="4" width="32" height="62" rx="9" fill="#8e2b23" stroke="#070807" stroke-width="2"/><rect x="9" y="16" width="22" height="13" rx="3" fill="#0e100f" opacity=".85"/><rect x="9" y="44" width="22" height="10" rx="3" fill="#0e100f" opacity=".7"/><rect x="7" y="4" width="7" height="4" rx="2" fill="#f4e3b0"/><rect x="26" y="4" width="7" height="4" rx="2" fill="#f4e3b0"/></svg>`;
const TOKEN = `<svg viewBox="0 0 48 48" class="token-art" aria-hidden="true"><circle cx="24" cy="24" r="20" fill="#c9a96a" stroke="#070807" stroke-width="2"/><circle cx="24" cy="24" r="14" fill="none" stroke="#3a2c12" stroke-width="1.6" stroke-dasharray="3 3"/><path d="M18 26l6-9 6 9M24 17v15" stroke="#3a2c12" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "crossing",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("cr-bet", cr.bet)}</div>
      <div><div class="label">Difficulté</div><div class="seg seg-wrap" id="cr-mode">${Object.entries(MODES).map(([k, m]) => `<button data-m="${k}">${m.label}</button>`).join("")}</div></div>
      <div class="info-list" id="cr-info"></div>`,
    action: `<div class="bj-actions" id="cr-actions"></div><p class="hint"><kbd>Espace</kbd> pour avancer</p>`,
    stage: `
      <div class="cr-stage">
        <div class="cr-scroll" id="cr-scroll"><div class="cr-road" id="cr-road"><div class="cr-lanes" id="cr-lanes"></div><div class="cr-token" id="cr-token">${TOKEN}</div></div></div>
        <div class="result-line" id="cr-result"></div>
      </div>`,
    rules: `<p>Ton jeton doit traverser une route à plusieurs voies. À chaque voie franchie, le multiplicateur augmente ; une voiture peut surgir à chaque pas et la mise est perdue.</p>
      <p>Encaisse quand tu veux. La difficulté fixe la chance de passer chaque voie (92 %, 84 %, 72 % ou 60 %) et le nombre de voies ; arriver de l'autre côté encaisse automatiquement.</p>`,
  });
  $("#cr-bet").addEventListener("input", (e) => (cr.bet = e.target.value));
  $("#cr-mode").addEventListener("click", (e) => {
    const b = e.target.closest("[data-m]");
    if (!b || cr.game?.status === "playing") return;
    cr.mode = b.dataset.m;
    cr.game = null;
    paint();
  });
  $("#cr-actions").addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (b) act(b.dataset.act);
  });
  onSpace(() => act(cr.game?.status === "playing" ? "step" : "start"));
  paint();
  api("crossing")
    .then((d) => {
      if (state.page !== "crossing") return;
      setBalance(d.balance);
      cr.game = d.game;
      if (d.game) cr.mode = d.game.mode;
      paint();
    })
    .catch((err) => toast(err.message, "error"));
}

function paint(animate = false) {
  const g = cr.game?.mode === cr.mode ? cr.game : null;
  const playing = g?.status === "playing";
  const m = MODES[cr.mode];
  const lad = g?.ladder ?? ladder(cr.mode);
  $$("#cr-mode [data-m]").forEach((b) => {
    b.classList.toggle("active", b.dataset.m === cr.mode);
    b.disabled = playing;
  });
  setStakeDisabled("cr-bet", playing);
  const steps = g?.steps ?? 0;
  $("#cr-actions").innerHTML = playing
    ? `<button class="btn btn-gold btn-lg" data-act="step">Avancer</button><button class="btn btn-win btn-lg" data-act="cash" ${steps ? "" : "disabled"}>${steps ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Encaisser"}</button>`
    : `<button class="btn btn-gold btn-lg btn-line" data-act="start">Commencer</button>`;
  $("#cr-info").innerHTML = `<div><span>Chance par voie</span><b>${Math.round(m.p * 100)} %</b></div><div><span>Voies</span><b>${m.lanes}</b></div><div><span>De l'autre côté</span><b>${mult(lad[m.lanes - 1])}</b></div>`;
  const hitAt = g && g.status === "lost" ? g.hitAt : -1;
  $("#cr-road").style.width = `${CURB_W * 2 + m.lanes * LANE_W}px`;
  $("#cr-lanes").innerHTML = `
    <div class="cr-curb">Départ</div>
    ${lad
      .map((x, i) => {
        const cls = i < steps ? "done" : i === hitAt ? "hit" : playing && i === steps ? "next" : "";
        return `<div class="cr-lane ${cls}"><span class="cr-mult">${mult(x)}</span>${i === hitAt ? `<span class="cr-car crash">${CAR}</span>` : i >= steps && i !== hitAt ? `<span class="cr-car ambient" style="animation-delay:${((i * 0.77) % 2.4).toFixed(2)}s;animation-duration:${(2.2 + ((i * 0.53) % 1.6)).toFixed(2)}s">${CAR}</span>` : `<span class="cr-barrier"></span>`}</div>`;
      })
      .join("")}
    <div class="cr-curb end">Arrivée</div>`;
  const token = $("#cr-token");
  token.classList.toggle("lost", g?.status === "lost");
  token.classList.remove("hop");
  if (animate) {
    void token.offsetWidth;
    token.classList.add("hop");
  } else token.style.transition = "none";
  token.style.transform = `translateX(${tokenX(steps, hitAt)}px)`;
  if (!animate) {
    void token.offsetWidth;
    token.style.transition = "";
  }
  // Garde le jeton visible.
  const scroll = $("#cr-scroll");
  const target = tokenX(steps, hitAt) - scroll.clientWidth / 2 + LANE_W / 2;
  scroll.scrollTo({ left: Math.max(0, target), behavior: animate ? "smooth" : "instant" });
  if (g && !playing && animate) {
    if (g.status === "won") {
      banner($("#cr-result"), `<b>+${fmt(g.payout)}</b> jetons, ${mult(g.multiplier)}`, "win");
      if (g.multiplier >= 5) flare();
    } else banner($("#cr-result"), `Fauché à la voie ${hitAt + 1} : mise perdue`, "lose");
  } else if (playing) banner($("#cr-result"), steps ? `${steps} voie${steps > 1 ? "s" : ""} traversée${steps > 1 ? "s" : ""} · ${mult(g.multiplier)}` : "Prêt à traverser");
}

/** Position du jeton : sur le trottoir de départ, puis au milieu de la dernière voie franchie. */
function tokenX(steps, hitAt) {
  const lane = hitAt >= 0 ? hitAt : steps - 1;
  if (lane < 0) return CURB_W / 2 - 22;
  return CURB_W + lane * LANE_W + LANE_W / 2 - 22;
}

async function act(what) {
  if (cr.busy) return;
  const playing = cr.game?.status === "playing";
  cr.busy = true;
  try {
    if (what === "start" && !playing) {
      const bet = readStake("cr-bet");
      if (!bet) return;
      banner($("#cr-result"), "");
      const d = await api("crossing/start", { bet, mode: cr.mode });
      setBalance(d.balance);
      cr.game = d.game;
      paint();
    } else if (what === "step" && playing) {
      const d = await api("crossing/step", {});
      cr.game = d.game;
      if (d.game.status === "lost") {
        // Le jeton s'avance, puis la voiture arrive.
        cr.game = { ...d.game, status: "playing", steps: d.game.steps + 1 };
        paint(true);
        await sleep(260);
        cr.game = d.game;
      }
      setBalance(d.balance);
      paint(true);
      if (d.game.status !== "playing") refreshHistory("crossing");
    } else if (what === "cash" && playing) {
      const d = await api("crossing/cashout", {});
      setBalance(d.balance);
      cr.game = d.game;
      paint(true);
      refreshHistory("crossing");
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    cr.busy = false;
  }
}

gamePage("crossing", render);
