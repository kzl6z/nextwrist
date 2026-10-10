const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const fmt = (n) => Number(n).toLocaleString("fr-FR");
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const time = (ms) =>
  new Date(ms).toLocaleString("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit" });

async function api(path, body) {
  const res = await fetch(`/api/${path}`, body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !path.startsWith("login") && !path.startsWith("register")) showAuth();
  if (!res.ok) throw new Error(data.error ?? "Erreur");
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3500);
}

function setBalance(b) {
  if (b !== undefined) $("#balance").textContent = fmt(b);
}

/* ---------- Auth ---------- */
function showAuth() {
  $("#app").classList.add("hidden");
  $("#auth").classList.remove("hidden");
}

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const mode = e.submitter?.dataset.mode ?? "login";
  const f = new FormData(e.target);
  try {
    await api(mode, { username: f.get("username"), password: f.get("password") });
    $("#auth-error").textContent = "";
    start();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
});

$("#logout").onclick = async () => {
  await api("logout", {});
  showAuth();
};

$("#bonus").onclick = async () => {
  try {
    const { balance } = await api("bonus", {});
    setBalance(balance);
    toast("🎁 Bonus quotidien récupéré !");
  } catch (err) {
    toast(err.message);
  }
};

/* ---------- Onglets ---------- */
const loaders = { sports: loadSports, crash: loadCrash, blackjack: loadBlackjack, account: loadAccount };
$$("#tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    $$("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
    $$("[data-view]").forEach((v) => v.classList.toggle("hidden", v.dataset.view !== b.dataset.tab));
    if (b.dataset.tab !== "crash" && crash) (clearInterval(crash.timer), clearInterval(crash.polling));
    loaders[b.dataset.tab]?.();
  }),
);

/* ---------- Paris sportifs ---------- */
const slip = new Map(); // eventId -> { eventId, outcome, price, label, match }
let events = [];
const OUTCOME_LABEL = { home: "1", draw: "N", away: "2" };

async function loadSports() {
  try {
    const data = await api("sports/events");
    events = data.events;
    renderEvents();
    $("#results").innerHTML =
      data.results
        .map((r) =>
          r.status === "cancelled"
            ? `<div>${esc(r.home)} - ${esc(r.away)} <span class="tag">annulé</span></div>`
            : `<div><span class="muted">${esc(r.league)}</span> · ${esc(r.home)} <b>${r.home_score} - ${r.away_score}</b> ${esc(r.away)}</div>`,
        )
        .join("") || `<p class="muted">Aucun résultat pour l'instant.</p>`;
    loadMyBets();
  } catch (err) {
    toast(err.message);
  }
}

function renderEvents() {
  const byLeague = Map.groupBy(events, (e) => e.league);
  $("#events").innerHTML =
    [...byLeague]
      .map(
        ([league, evs]) => `<h4 class="league">${esc(league)}</h4>` +
          evs.map((e) => `
          <div class="event">
            <div><div>${esc(e.home)} – ${esc(e.away)}</div><div class="when">${time(e.starts_at)}</div></div>
            <div class="odds">${["home", "draw", "away"]
              .filter((o) => e.odds[o])
              .map((o) => `<button data-ev="${esc(e.id)}" data-o="${o}" class="${slip.get(e.id)?.outcome === o ? "picked" : ""}">
                  <span>${OUTCOME_LABEL[o]}</span><b>${e.odds[o].toFixed(2)}</b></button>`)
              .join("")}</div>
          </div>`).join(""),
      )
      .join("") || `<p class="muted">Aucun match disponible pour le moment.</p>`;
}

$("#events").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-ev]");
  if (!btn) return;
  const ev = events.find((x) => x.id === btn.dataset.ev);
  const o = btn.dataset.o;
  if (slip.get(ev.id)?.outcome === o) slip.delete(ev.id);
  else
    slip.set(ev.id, {
      eventId: ev.id,
      outcome: o,
      price: ev.odds[o],
      match: `${ev.home} – ${ev.away}`,
      label: o === "draw" ? "Nul" : o === "home" ? ev.home : ev.away,
    });
  renderEvents();
  renderSlip();
});

function renderSlip() {
  const legs = [...slip.values()];
  $("#slip-legs").innerHTML = legs.length
    ? legs.map((l) => `<div class="leg"><span>${esc(l.match)}<br><b>${esc(l.label)}</b> @ ${l.price.toFixed(2)}</span>
        <button data-rm="${esc(l.eventId)}">✕</button></div>`).join("")
    : `<p class="muted">Clique sur une cote pour l'ajouter.</p>`;
  const odds = legs.reduce((p, l) => p * l.price, 1);
  const stake = Number($("#slip-stake").value) || 0;
  const rounded = Math.round(odds * 100) / 100;
  $("#slip-odds").textContent = legs.length ? rounded.toFixed(2) : "–";
  $("#slip-win").textContent = legs.length ? fmt(Math.floor(stake * rounded)) : "–";
}

$("#slip-legs").addEventListener("click", (e) => {
  const id = e.target.dataset.rm;
  if (!id) return;
  slip.delete(id);
  renderEvents();
  renderSlip();
});
$("#slip-stake").addEventListener("input", renderSlip);

$("#slip-place").onclick = async () => {
  if (!slip.size) return toast("Ajoute au moins une sélection");
  try {
    const r = await api("sports/bets", { legs: [...slip.values()], stake: Number($("#slip-stake").value) });
    setBalance(r.balance);
    toast(`✅ Pari validé — gain potentiel ${fmt(r.potentialWin)}`);
    slip.clear();
    renderSlip();
    loadSports();
  } catch (err) {
    toast(err.message);
    loadSports();
  }
};

async function loadMyBets() {
  const { bets, balance } = await api("sports/bets");
  setBalance(balance);
  const STATUS = { open: "en cours", won: "gagné", lost: "perdu", void: "remboursé" };
  $("#my-bets").innerHTML =
    bets
      .map((b) => `<div class="bet">
        <span class="tag ${b.status}">${STATUS[b.status]}</span>
        Mise ${fmt(b.stake)} @ ${b.total_odds.toFixed(2)} → ${fmt(b.payout ?? b.potential_win)}
        ${b.legs.map((l) => `<div class="muted">${l.result === "won" ? "✔" : l.result === "lost" ? "✘" : "•"}
          ${esc(l.home)} – ${esc(l.away)} : ${OUTCOME_LABEL[l.outcome]} @ ${l.price.toFixed(2)}
          ${l.home_score !== null ? `(${l.home_score}-${l.away_score})` : ""}</div>`).join("")}
      </div>`)
      .join("") || `<p class="muted">Aucun pari.</p>`;
}

/* ---------- Roulette ---------- */
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const color = (n) => (n === 0 ? "green" : RED.has(n) ? "red" : "black");
const rlBets = new Map(); // clé -> { type, value, amount }
const OUTSIDE = [
  ["low", "1-18"], ["even", "Pair"], ["red", "Rouge"], ["black", "Noir"], ["odd", "Impair"], ["high", "19-36"],
  ["dozen:1", "1-12"], ["dozen:2", "13-24"], ["dozen:3", "25-36"],
  ["column:1", "Col. 1"], ["column:2", "Col. 2"], ["column:3", "Col. 3"],
];

function buildRoulette() {
  const nums = [0];
  for (const row of [3, 2, 1]) for (let c = 0; c < 12; c++) nums.push(row + c * 3);
  $("#board").innerHTML = nums
    .map((n) => `<button class="${color(n)}" data-key="number:${n}">${n}</button>`)
    .join("");
  $("#outside").innerHTML = OUTSIDE.map(([k, l]) => `<button data-key="${k}">${l}</button>`).join("");
}

function renderRouletteBets() {
  $$("[data-key]").forEach((b) => {
    const bet = rlBets.get(b.dataset.key);
    b.querySelector(".chipcount")?.remove();
    if (bet) b.insertAdjacentHTML("beforeend", `<span class="chipcount">${fmt(bet.amount)}</span>`);
  });
  $("#rl-total").textContent = fmt([...rlBets.values()].reduce((s, b) => s + b.amount, 0));
}

[$("#board"), $("#outside")].forEach((el) =>
  el.addEventListener("click", (e) => {
    const key = e.target.closest("[data-key]")?.dataset.key;
    if (!key) return;
    const [type, value] = key.split(":");
    const bet = rlBets.get(key) ?? { type, value: value === undefined ? undefined : Number(value), amount: 0 };
    bet.amount += Number($("#chip").value);
    rlBets.set(key, bet);
    renderRouletteBets();
  }),
);
$("#rl-clear").onclick = () => {
  rlBets.clear();
  renderRouletteBets();
};

$("#rl-spin").onclick = async () => {
  if (!rlBets.size) return toast("Place au moins une mise");
  const wheel = $("#wheel");
  $("#rl-spin").disabled = true;
  wheel.className = "wheel spinning";
  wheel.textContent = "";
  try {
    const [r] = await Promise.all([api("roulette/spin", { bets: [...rlBets.values()] }), new Promise((ok) => setTimeout(ok, 1200))]);
    wheel.className = `wheel ${r.color}`;
    wheel.textContent = r.number;
    setBalance(r.balance);
    $("#rl-msg").textContent = r.totalWin > 0 ? `🎉 Gagné ${fmt(r.totalWin)} !` : "Perdu…";
  } catch (err) {
    wheel.className = "wheel";
    wheel.textContent = "?";
    toast(err.message);
  } finally {
    $("#rl-spin").disabled = false;
  }
};

/* ---------- Machine à sous ---------- */
const SYMS = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎"];
$("#sl-spin").onclick = async () => {
  const spans = $$("#reels span");
  $("#sl-spin").disabled = true;
  const anim = setInterval(() => spans.forEach((s) => (s.textContent = SYMS[Math.floor(Math.random() * SYMS.length)])), 80);
  try {
    const [r] = await Promise.all([api("slots/spin", { bet: Number($("#sl-bet").value) }), new Promise((ok) => setTimeout(ok, 900))]);
    clearInterval(anim);
    r.reels.forEach((s, i) => (spans[i].textContent = s));
    setBalance(r.balance);
    $("#sl-msg").textContent = r.win > 0 ? `🎉 Gagné ${fmt(r.win)} (×${r.multiplier}) !` : "Perdu…";
  } catch (err) {
    clearInterval(anim);
    toast(err.message);
  } finally {
    $("#sl-spin").disabled = false;
  }
};

/* ---------- Crash ---------- */
let crash = null; // { round, growth, startedLocal, timer, polling }

function drawCrash(mult, elapsed, state) {
  const c = $("#cr-canvas");
  const ctx = c.getContext("2d");
  const { width: w, height: h } = c;
  ctx.clearRect(0, 0, w, h);
  if (elapsed <= 0) return;
  const growth = crash?.growth ?? 0.00006;
  const span = Math.max(8000, elapsed * 1.15);
  const top = Math.max(2, mult * 1.2);
  ctx.beginPath();
  for (let i = 0; i <= 120; i++) {
    const t = (elapsed * i) / 120;
    const x = 30 + (t / span) * (w - 60);
    const y = h - 30 - ((Math.exp(growth * t) - 1) / (top - 1)) * (h - 60);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.strokeStyle = state === "lost" ? "#ff7b72" : state === "won" ? "#3fb950" : "#f5c542";
  ctx.lineWidth = 5;
  ctx.stroke();
}

function renderCrash(data) {
  setBalance(data.balance);
  crash = { ...crash, growth: data.growth, round: data.round };
  $("#cr-history").innerHTML = data.history
    .map((m) => `<span class="${m >= 2 ? "high" : ""}">${m.toFixed(2)}×</span>`)
    .join("");
  const r = data.round;
  const playing = r?.status === "playing";
  $("#cr-start").classList.toggle("hidden", playing);
  $("#cr-cashout").classList.toggle("hidden", !playing || !!r.autoCashout);
  clearInterval(crash.timer);
  clearInterval(crash.polling);
  const mult = $("#cr-mult");
  if (playing) {
    crash.startedLocal = performance.now() - r.elapsedMs;
    mult.className = "cr-mult";
    $("#cr-msg").textContent = r.autoCashout ? `Encaissement auto à ${r.autoCashout.toFixed(2)}×` : `Mise : ${fmt(r.bet)}`;
    crash.timer = setInterval(() => {
      const el = performance.now() - crash.startedLocal;
      const m = Math.floor(Math.exp(crash.growth * el) * 100) / 100;
      mult.textContent = `${m.toFixed(2)}×`;
      drawCrash(m, el, "playing");
      if (!r.autoCashout)
        $("#cr-cashout").textContent = `Encaisser ${fmt(Math.floor(r.bet * m))}`;
    }, 33);
    // Seul le serveur connaît le point de crash : on lui demande régulièrement.
    crash.polling = setInterval(async () => {
      const d = await api("crash").catch(() => null);
      if (d && d.round?.status !== "playing") renderCrash(d);
    }, 300);
  } else if (r) {
    const end = r.status === "won" ? r.cashoutAt : r.crashPoint;
    drawCrash(r.crashPoint, Math.log(r.crashPoint) / crash.growth, r.status);
    mult.className = `cr-mult ${r.status === "won" ? "won" : "crashed"}`;
    mult.textContent = r.status === "won" ? `${end.toFixed(2)}×` : `💥 ${r.crashPoint.toFixed(2)}×`;
    $("#cr-msg").textContent =
      r.status === "won"
        ? `🎉 Encaissé à ${r.cashoutAt.toFixed(2)}× : +${fmt(r.payout)} (crash à ${r.crashPoint.toFixed(2)}×)`
        : `Crash à ${r.crashPoint.toFixed(2)}×, perdu…`;
  }
}

async function loadCrash() {
  renderCrash(await api("crash"));
}

$("#cr-start").onclick = async () => {
  try {
    const auto = $("#cr-auto").value;
    renderCrash(await api("crash/start", { bet: Number($("#cr-bet").value), autoCashout: auto ? Number(auto) : null }));
  } catch (err) {
    toast(err.message);
  }
};
$("#cr-cashout").onclick = async () => {
  try {
    renderCrash(await api("crash/cashout", {}));
  } catch (err) {
    toast(err.message);
  }
};

/* ---------- Blackjack ---------- */
function cardHtml(c) {
  if (c === "??") return `<div class="playing-card back"></div>`;
  return `<div class="playing-card ${/[♥♦]/.test(c) ? "red" : ""}">${c}</div>`;
}

function renderBlackjack({ hand, balance }) {
  setBalance(balance);
  const playing = hand?.status === "playing";
  $("#bj-actions").classList.toggle("hidden", !playing);
  $("#bj-start").classList.toggle("hidden", playing);
  if (!hand) return;
  $("#bj-dealer").innerHTML = hand.dealer.map(cardHtml).join("");
  $("#bj-player").innerHTML = hand.player.map(cardHtml).join("");
  $("#bj-dv").textContent = `(${hand.dealerValue})`;
  $("#bj-pv").textContent = `(${hand.playerValue})`;
  $("[data-bj=double]").disabled = !hand.canDouble;
  const MSG = {
    playing: `Mise : ${fmt(hand.bet)}`,
    blackjack: `🃏 Blackjack ! +${fmt(hand.payout)}`,
    won: `🎉 Gagné ! +${fmt(hand.payout)}`,
    push: "Égalité, mise rendue",
    lost: "Perdu…",
  };
  $("#bj-msg").textContent = MSG[hand.status];
}

async function loadBlackjack() {
  renderBlackjack(await api("blackjack"));
}

$("#bj-deal").onclick = async () => {
  try {
    renderBlackjack(await api("blackjack/start", { bet: Number($("#bj-bet").value) }));
  } catch (err) {
    toast(err.message);
  }
};
$("#bj-actions").addEventListener("click", async (e) => {
  const action = e.target.dataset.bj;
  if (!action) return;
  try {
    renderBlackjack(await api(`blackjack/${action}`, {}));
  } catch (err) {
    toast(err.message);
  }
});

/* ---------- Compte ---------- */
const KIND = {
  welcome_bonus: "Bonus de bienvenue", daily_bonus: "Bonus quotidien",
  roulette_bet: "Roulette — mise", roulette_win: "Roulette — gain",
  slots_bet: "Machine — mise", slots_win: "Machine — gain",
  crash_bet: "Crash — mise", crash_win: "Crash — gain",
  blackjack_bet: "Blackjack — mise", blackjack_win: "Blackjack — gain",
  sport_bet: "Pari sportif", sport_win: "Pari sportif — gain", sport_refund: "Pari sportif — remboursement",
};

async function loadAccount() {
  const [txs, board] = await Promise.all([api("transactions"), api("leaderboard")]);
  $("#history").innerHTML = txs
    .map((t) => `<div class="leg"><span>${KIND[t.kind] ?? t.kind}<br><span class="muted">${time(t.created_at)}</span></span>
      <b style="color:${t.amount > 0 ? "#3fb950" : "#ff7b72"}">${t.amount > 0 ? "+" : ""}${fmt(t.amount)}</b></div>`)
    .join("");
  $("#leaderboard").innerHTML = board.map((u) => `<li>${esc(u.username)} — ${fmt(u.balance)} 🪙</li>`).join("");
}

/* ---------- Démarrage ---------- */
async function start() {
  try {
    const me = await api("me");
    $("#auth").classList.add("hidden");
    $("#app").classList.remove("hidden");
    setBalance(me.balance);
    $("#feed-note").textContent =
      me.feed === "demo" ? "Mode démo : matchs simulés. Ajoute ODDS_API_KEY pour les vrais matchs." : "Cotes et résultats réels.";
    buildRoulette();
    loadSports();
  } catch {
    showAuth();
  }
}

setInterval(() => {
  if (!$("[data-view=sports]").classList.contains("hidden") && !$("#app").classList.contains("hidden")) loadSports();
}, 30_000);

start();
