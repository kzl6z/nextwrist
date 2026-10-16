/* Ballon : gonfle, le multiplicateur grimpe, encaisse avant qu'il n'éclate */
import { $, $$, api, fmt, mult, onSpace, readStake, setBalance, setStakeDisabled, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const MODES = { low: ["Faible", 1], medium: ["Moyen", 3], high: ["Élevé", 5], expert: ["Expert", 10] };
const bl = { bet: 10, mode: "medium", game: null, busy: false };

function multiplier(mode, pumps) {
  const m = MODES[mode][1];
  let x = 0.98;
  for (let i = 0; i < pumps; i++) x *= (25 - i) / (25 - m - i);
  return pumps ? Math.floor(x * 10_000) / 10_000 : 1;
}

const balloonSvg = () => `<svg viewBox="0 0 200 260" class="bl-svg" aria-hidden="true">
  <defs>
    <radialGradient id="bl-g" cx="38%" cy="32%" r="70%"><stop offset="0" stop-color="#f3dfa9"/><stop offset=".45" stop-color="#c9a96a"/><stop offset="1" stop-color="#6e5527"/></radialGradient>
  </defs>
  <path class="bl-string" d="M100 214c-8 12 8 20 0 32" stroke="rgba(236,230,214,.5)" stroke-width="1.6" fill="none"/>
  <g class="bl-body">
    <path d="M100 18c-46 0-74 36-74 80 0 50 40 86 68 104l-4 10h20l-4-10c28-18 68-54 68-104 0-44-28-80-74-80z" fill="url(#bl-g)" stroke="#3a2c12" stroke-width="1.5"/>
    <path d="M62 56c-12 12-16 28-14 44" stroke="rgba(255,248,225,.7)" stroke-width="6" stroke-linecap="round" fill="none"/>
  </g>
  <g class="bl-shards">${Array.from({ length: 10 }, (_, i) => {
    const a = (i / 10) * Math.PI * 2;
    return `<path d="M100 104l${(Math.cos(a) * 14).toFixed(1)} ${(Math.sin(a) * 14).toFixed(1)}l${(Math.cos(a + 0.5) * 10).toFixed(1)} ${(Math.sin(a + 0.5) * 10).toFixed(1)}z" fill="#c9a96a" style="--dx:${(Math.cos(a) * 90).toFixed(0)}px;--dy:${(Math.sin(a) * 90).toFixed(0)}px"/>`;
  }).join("")}</g>
</svg>`;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "balloon",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("bl-bet", bl.bet)}</div>
      <div><div class="label">Risque</div><div class="seg seg-wrap" id="bl-mode">${Object.entries(MODES).map(([k, [l]]) => `<button data-m="${k}">${l}</button>`).join("")}</div></div>
      <div class="info-list" id="bl-info"></div>`,
    action: `<div class="bj-actions" id="bl-actions"></div><p class="hint"><kbd>Espace</kbd> pour gonfler</p>`,
    stage: `
      <div class="bl-stage">
        <div class="bl-sky">
          <div class="bl-wrap" id="bl-wrap">${balloonSvg()}<div class="bl-mult display" id="bl-mult">×1</div></div>
        </div>
        <div class="cf-ladder" id="bl-ladder"></div>
        <div class="result-line" id="bl-result"></div>
      </div>`,
    rules: `<p>Chaque coup de pompe gonfle le ballon et augmente le multiplicateur. Mais à chaque coup, il peut éclater : la mise est alors perdue.</p>
      <p>Le risque fixe la fragilité du ballon : le moment de l'éclatement est tiré au départ, comme s'il y avait 1, 3, 5 ou 10 cases piégées sur 25. Encaisse quand tu veux.</p>`,
  });
  $("#bl-bet").addEventListener("input", (e) => (bl.bet = e.target.value));
  $("#bl-mode").addEventListener("click", (e) => {
    const b = e.target.closest("[data-m]");
    if (!b || bl.game?.status === "playing") return;
    bl.mode = b.dataset.m;
    bl.game = null;
    paint();
  });
  $("#bl-actions").addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (b) act(b.dataset.act);
  });
  onSpace(() => act("pump"));
  paint();
  api("balloon")
    .then((d) => {
      if (state.page !== "balloon") return;
      setBalance(d.balance);
      bl.game = d.game;
      if (d.game) bl.mode = d.game.mode;
      paint();
    })
    .catch((err) => toast(err.message, "error"));
}

function paint(animate = false) {
  const g = bl.game?.mode === bl.mode ? bl.game : null;
  const playing = g?.status === "playing";
  const traps = MODES[bl.mode][1];
  const max = 25 - traps;
  const steps = g?.steps ?? 0;
  $$("#bl-mode [data-m]").forEach((b) => {
    b.classList.toggle("active", b.dataset.m === bl.mode);
    b.disabled = playing;
  });
  setStakeDisabled("bl-bet", playing);
  $("#bl-actions").innerHTML = playing
    ? `<button class="btn btn-gold btn-lg" data-act="pump">Gonfler</button><button class="btn btn-win btn-lg" data-act="cash" ${steps ? "" : "disabled"}>${steps ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Encaisser"}</button>`
    : `<button class="btn btn-gold btn-lg btn-line" data-act="pump">Gonfler</button>`;
  const chance = playing ? g.chance : (25 - traps) / 25;
  const next = playing ? g.next : multiplier(bl.mode, 1);
  $("#bl-info").innerHTML = `<div><span>Chance au prochain coup</span><b>${Math.round(chance * 1000) / 10} %</b></div><div><span>Prochain multiplicateur</span><b>${next ? mult(next) : "—"}</b></div><div><span>Maximum</span><b>${mult(multiplier(bl.mode, max))}</b></div>`;
  // Taille du ballon : grandit avec les coups de pompe.
  const wrap = $("#bl-wrap");
  const burst = g?.status === "lost";
  wrap.classList.toggle("burst", burst && animate);
  wrap.classList.toggle("gone", burst && !animate);
  wrap.classList.toggle("won", g?.status === "won");
  const scale = 0.62 + 0.38 * Math.min(1, Math.sqrt(steps / Math.min(max, 12)));
  wrap.style.setProperty("--s", scale.toFixed(3));
  $("#bl-mult").textContent = mult(g ? (burst ? 0 : g.multiplier) : 1);
  const from = Math.max(0, steps - 3);
  $("#bl-ladder").innerHTML = Array.from({ length: Math.min(8, max - from) }, (_, k) => {
    const i = from + k;
    return `<span class="${i < steps ? "on" : i === steps && playing ? "next" : ""}">${mult(multiplier(bl.mode, i + 1))}</span>`;
  }).join("");
  if (g && !playing && animate) {
    if (g.status === "won") {
      banner($("#bl-result"), `<b>+${fmt(g.payout)}</b> jetons, ${mult(g.multiplier)}`, "win");
      if (g.multiplier >= 5) flare();
    } else banner($("#bl-result"), `Éclaté au coup n° ${g.burstAt} : mise perdue`, "lose");
  } else if (playing) banner($("#bl-result"), steps ? `${steps} coup${steps > 1 ? "s" : ""} de pompe` : "Gonfle pour commencer");
}

async function act(what) {
  if (bl.busy) return;
  const playing = bl.game?.status === "playing" && bl.game.mode === bl.mode;
  bl.busy = true;
  try {
    if (what === "pump") {
      if (!playing) {
        const bet = readStake("bl-bet");
        if (!bet) return;
        banner($("#bl-result"), "");
        const d = await api("balloon/start", { bet, mode: bl.mode });
        setBalance(d.balance);
        bl.game = d.game;
      }
      const d = await api("balloon/pump", {});
      setBalance(d.balance);
      bl.game = d.game;
      paint(true);
      if (d.game.status !== "playing") refreshHistory("balloon");
    } else if (what === "cash" && playing) {
      const d = await api("balloon/cashout", {});
      setBalance(d.balance);
      bl.game = d.game;
      paint(true);
      refreshHistory("balloon");
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    bl.busy = false;
  }
}

gamePage("balloon", render);
