/* Course hippique virtuelle : six chevaux, pari gagnant ou placé */
import { $, $$, api, esc, fmt, fmtDec, onLeave, readStake, setBalance, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";

const SILKS = ["#8e2b23", "#3d5a73", "#2f6b4f", "#b8955a", "#5b4a7a", "#d9d2c3"];
const rc = { bet: 10, type: "win", horse: null, horses: null, busy: false, raf: 0, lastOrder: null };
const odds = (h) => (rc.type === "win" ? h.win : h.place);

const silk = (i) => `<span class="silk" style="--c:${SILKS[i]}"><b>${i + 1}</b></span>`;
const runner = (i) => `<svg class="runner" viewBox="0 0 64 40" aria-hidden="true">
  <path fill="currentColor" d="M15 14C20 11 32 11 39 12C42 9 45 6 49 3L50 .5L52 3C56 4 60 7 63 11L62 13.5C59 13 56 12.5 53 13.5C51 16 48.5 19 48 22L55 25.5L61 26L61 28.5L54 28.5L46 25.5L44 26L48 31.5L46 33L39 26.5C33 27.5 26 27.5 21 26.5L15 31L8 35.5L6.5 33.5L12 29.5L14.5 25C13 23 12.5 21 12.5 19L10 21.5C8 24.5 5 26 2 26.5C4.5 24 6.5 21 8 18C10 15 12.5 14 15 14Z"/>
  <path fill="currentColor" d="M21 26.5L25 32L23 33.5L18 28z"/>
  <path d="M27 12.5C28 7.5 32.5 4.5 38 5.5L39.5 8.5C36 9 33.5 11 32.5 13.5Z" fill="${SILKS[i]}" stroke="#070807" stroke-width=".8"/>
  <path d="M37 7.5L45 9.5" stroke="${SILKS[i]}" stroke-width="2.2" stroke-linecap="round"/>
  <circle cx="40.5" cy="4" r="2.6" fill="${SILKS[i]}" stroke="#070807" stroke-width=".8"/>
</svg>`;

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "race",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("rc-bet", rc.bet)}</div>
      <div><div class="label">Type de pari</div><div class="seg" id="rc-type"><button data-t="win">Gagnant</button><button data-t="place">Placé (2 premiers)</button></div></div>
      <div><div class="label">Partants</div><div class="rc-list" id="rc-list"><div class="skeleton" style="height:240px"></div></div></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="rc-go" disabled>Choisis un cheval</button>`,
    stage: `
      <div class="rc-stage">
        <div class="rc-track" id="rc-track"></div>
        <div class="rc-podium" id="rc-podium"></div>
        <div class="result-line" id="rc-result"></div>
      </div>`,
    rules: `<p>Six chevaux prennent le départ ; leurs chances sont différentes et la cote de chacun est affichée avant la course. Mise sur un cheval : <b>gagnant</b> s'il finit premier, <b>placé</b> s'il finit dans les deux premiers (cote plus faible).</p>
      <p>L'ordre d'arrivée est tiré par le serveur selon la force de chaque cheval. Une nouvelle course est proposée juste après l'arrivée.</p>`,
  });
  $("#rc-bet").addEventListener("input", (e) => {
    rc.bet = e.target.value;
    paintButton();
  });
  $("#rc-type").addEventListener("click", (e) => {
    const b = e.target.closest("[data-t]");
    if (!b || rc.busy) return;
    rc.type = b.dataset.t;
    paint();
  });
  $("#rc-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-h]");
    if (!b || rc.busy) return;
    rc.horse = Number(b.dataset.h);
    paint();
  });
  $("#rc-go").addEventListener("click", go);
  onLeave(() => cancelAnimationFrame(rc.raf));
  if (rc.horses) paint();
  api("race")
    .then((d) => {
      if (state.page !== "race") return;
      setBalance(d.balance);
      rc.horses = d.horses;
      paint();
    })
    .catch((err) => toast(err.message, "error"));
}

function trackHtml() {
  return rc.horses
    .map(
      (h, i) => `<div class="rc-lane" data-lane="${i}"><span class="rc-gate">${i + 1}</span><div class="rc-run" id="rc-h${i}" style="--x:0">${runner(i)}</div></div>`,
    )
    .join("") + `<div class="rc-finish"></div>`;
}

function paint() {
  if (!rc.horses) return;
  $$("#rc-type [data-t]").forEach((b) => b.classList.toggle("active", b.dataset.t === rc.type));
  $("#rc-list").innerHTML = rc.horses
    .map(
      (h, i) => `<button class="rc-horse ${rc.horse === i ? "active" : ""}" data-h="${i}">${silk(i)}<span class="rc-name">${esc(h.name)}</span><b class="num">${fmtDec(odds(h))}</b></button>`,
    )
    .join("");
  if (!rc.busy) $("#rc-track").innerHTML = trackHtml();
  paintButton();
}

function paintButton() {
  const btn = $("#rc-go");
  if (!btn) return;
  btn.disabled = rc.horse === null || rc.busy;
  if (rc.horse === null) btn.textContent = "Choisis un cheval";
  else {
    const h = rc.horses[rc.horse];
    const bet = Math.floor(Number(rc.bet)) || 0;
    btn.textContent = `Lancer la course · gain possible ${fmt(Math.floor(bet * odds(h)))}`;
  }
}

/** Animation : chaque cheval franchit la ligne à son tour, dans l'ordre tiré par le serveur. */
function animate(order) {
  return new Promise((resolve) => {
    const n = order.length;
    const finishAt = Array(n);
    order.forEach((h, rank) => (finishAt[h] = 6200 + rank * (240 + Math.random() * 140)));
    const wobble = Array.from({ length: n }, () => [Math.random() * 6.28, 0.6 + Math.random() * 0.8]);
    const els = Array.from({ length: n }, (_, i) => $(`#rc-h${i}`));
    const t0 = performance.now();
    const step = (now) => {
      if (state.page !== "race") return resolve(false);
      const t = now - t0;
      let done = true;
      for (let i = 0; i < n; i++) {
        const p = Math.min(1, t / finishAt[i]);
        const eased = p < 1 ? p + Math.sin(p * Math.PI * 3 * wobble[i][1] + wobble[i][0]) * 0.035 * Math.sin(p * Math.PI) : 1;
        els[i].style.setProperty("--x", Math.max(0, Math.min(1, eased)).toFixed(4));
        els[i].classList.toggle("galop", p < 1);
        if (p < 1) done = false;
      }
      if (done) return resolve(true);
      rc.raf = requestAnimationFrame(step);
    };
    rc.raf = requestAnimationFrame(step);
  });
}

async function go() {
  if (rc.busy || rc.horse === null) return;
  const bet = readStake("rc-bet");
  if (!bet) return;
  rc.busy = true;
  paintButton();
  banner($("#rc-result"), "");
  $("#rc-podium").innerHTML = "";
  $("#rc-track").innerHTML = trackHtml();
  $(`#rc-track [data-lane="${rc.horse}"]`).classList.add("mine");
  // Sur téléphone, la piste est au-dessus des réglages : on la ramène à l'écran.
  const box = $("#rc-track").getBoundingClientRect();
  if (box.top < 60 || box.bottom > innerHeight) $("#rc-track").scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    const r = await api("race/bet", { bet, horse: rc.horse, type: rc.type });
    setBalance(r.balance - r.payout);
    const finished = await animate(r.order);
    if (!finished) return;
    setBalance(r.balance);
    $("#rc-podium").innerHTML = r.order
      .slice(0, 3)
      .map((h, k) => `<span class="rc-place ${h === r.horse ? "mine" : ""}"><i>${k + 1}<sup>${k ? "e" : "er"}</sup></i>${silk(h)}${esc(r.horses[h].name)}</span>`)
      .join("");
    const name = esc(r.horses[r.horse].name);
    if (r.won) banner($("#rc-result"), `${name} ${r.type === "win" ? "gagne" : "est placé"} : <b>+${fmt(r.payout)}</b> jetons à ${fmtDec(r.odds)}`, "win");
    else banner($("#rc-result"), `${name} finit ${r.order.indexOf(r.horse) + 1}<sup>e</sup> : mise perdue`, "lose");
    if (r.won && r.odds >= 8) flare();
    refreshHistory("race");
    // Nouvelle course
    rc.horses = r.next;
    rc.horse = null;
    rc.busy = false;
    setTimeout(() => {
      if (state.page === "race" && !rc.busy) paint();
    }, 3200);
    $("#rc-list").innerHTML = rc.horses
      .map((h, i) => `<button class="rc-horse" data-h="${i}">${silk(i)}<span class="rc-name">${esc(h.name)}</span><b class="num">${fmtDec(odds(h))}</b></button>`)
      .join("");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    rc.busy = false;
    if (state.page === "race") paintButton();
  }
}

gamePage("race", render);
