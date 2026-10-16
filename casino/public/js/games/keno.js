/* Keno : 40 numéros, 10 tirés ; choisis de 1 à 10 numéros */
import { $, $$, api, fmt, mult, onSpace, readStake, setBalance, sleep, stakeInput, state, toast, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";

const kn = { bet: 10, picks: new Set(), busy: false, table: null, drawn: [], hits: [] };

async function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "keno",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("kn-bet", kn.bet)}</div>
      <div class="rl-actions"><button class="btn btn-sm" id="kn-auto">Choix au hasard</button><button class="btn btn-sm" id="kn-clear">Effacer</button></div>
      <div><div class="label">Gains <span id="kn-count"></span></div><div class="keno-pays" id="kn-pays"></div></div>
`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="kn-play">Lancer le tirage</button>
      <p class="hint"><kbd>Espace</kbd> pour lancer</p>`,
    stage: `
      <div class="keno-stage">
        <div class="keno-grid" id="kn-grid">${Array.from({ length: 40 }, (_, i) => `<button class="kn" data-n="${i + 1}">${i + 1}</button>`).join("")}</div>
        <div class="result-line" id="kn-result"></div>
      </div>`,
    rules: `<p>Choisis de 1 à 10 numéros, puis lance le tirage : 10 numéros sur 40 sortent. Plus tu trouves de numéros, plus le multiplicateur grimpe.</p>
      <p>La table des gains s'adapte au nombre de numéros choisis.</p>`,
  });
  $("#kn-bet").addEventListener("input", (e) => (kn.bet = e.target.value));
  $("#kn-grid").addEventListener("click", (e) => {
    const b = e.target.closest("[data-n]");
    if (!b || kn.busy) return;
    const n = Number(b.dataset.n);
    if (kn.picks.has(n)) kn.picks.delete(n);
    else if (kn.picks.size >= 10) return toast("Dix numéros au maximum", "info");
    else kn.picks.add(n);
    clearDraw();
    paint();
  });
  $("#kn-auto").addEventListener("click", () => {
    if (kn.busy) return;
    const count = kn.picks.size || 5;
    const pool = Array.from({ length: 40 }, (_, i) => i + 1);
    kn.picks = new Set();
    while (kn.picks.size < count) kn.picks.add(pool.splice(Math.floor(Math.random() * pool.length), 1)[0]);
    clearDraw();
    paint();
  });
  $("#kn-clear").addEventListener("click", () => {
    if (kn.busy) return;
    kn.picks.clear();
    clearDraw();
    paint();
  });
  $("#kn-play").addEventListener("click", play);
  onSpace(play);
  try {
    kn.table = (await casinoConfig()).keno;
    paint();
  } catch (err) {
    toast(err.message, "error");
  }
}

function clearDraw() {
  kn.drawn = [];
  kn.hits = [];
  banner($("#kn-result"), "");
}

function paint() {
  if (state.page !== "keno") return;
  $$("#kn-grid .kn").forEach((b) => {
    const n = Number(b.dataset.n);
    b.classList.toggle("picked", kn.picks.has(n));
    b.classList.toggle("drawn", kn.drawn.includes(n));
    b.classList.toggle("hit", kn.hits.includes(n));
  });
  const k = kn.picks.size;
  $("#kn-count").textContent = k ? `${k} numéro${k > 1 ? "s" : ""}` : "";
  $("#kn-pays").innerHTML =
    k && kn.table
      ? kn.table[k]
          .map((m, hits) => ({ m, hits }))
          .filter((x) => x.m > 0)
          .map((x) => `<div class="kp ${kn.drawn.length && kn.hits.length === x.hits ? "on" : ""}"><span>${x.hits} trouvé${x.hits > 1 ? "s" : ""}</span><b>${mult(x.m)}</b></div>`)
          .join("")
      : `<p class="muted" style="margin:0">Choisis tes numéros sur la grille.</p>`;
  $("#kn-play").disabled = kn.busy || !k;
}

async function play() {
  if (kn.busy || !kn.picks.size) return;
  const bet = readStake("kn-bet");
  if (!bet) return;
  kn.busy = true;
  clearDraw();
  paint();
  try {
    const r = await api("keno", { bet, picks: [...kn.picks] });
    setBalance(r.balance - r.payout);
    for (const n of r.drawn) {
      if (state.page !== "keno") return;
      kn.drawn.push(n);
      if (r.hits.includes(n)) kn.hits.push(n);
      paint();
      await sleep(110);
    }
    setBalance(r.balance);
    banner(
      $("#kn-result"),
      r.payout ? `${r.hits.length} trouvé${r.hits.length > 1 ? "s" : ""} : <b>+${fmt(r.payout)}</b> jetons` : `${r.hits.length} trouvé${r.hits.length > 1 ? "s" : ""} : pas de gain`,
      r.payout >= bet ? "win" : "lose",
    );
    refreshHistory("keno");
    if (r.multiplier >= 20) flare();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    kn.busy = false;
    paint();
  }
}

gamePage("keno", render);
