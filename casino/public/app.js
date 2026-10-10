/* =========================================================
   PilotCasino — application cliente (aucune dépendance)
   ========================================================= */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const fmt = (n) => Number(n).toLocaleString("fr-FR");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const view = $("#view");

const state = {
  me: null,
  balance: 0,
  events: [],
  live: [],
  results: [],
  loadedAt: 0,
  bets: [],
  slip: new Map(), // eventId -> sélection
  stake: 10,
  slipTab: "slip",
  filter: { sport: "all", league: null, day: "all" },
  page: null,
};

// Nettoyages à exécuter en quittant la page courante (timers, écouteurs…).
let cleanups = [];
const onLeave = (fn) => cleanups.push(fn);

/* ---------- API ---------- */
async function api(path, body) {
  const res = await fetch(
    `/api/${path}`,
    body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "login" && path !== "register") showAuth();
  if (!res.ok) throw new Error(data.error ?? "Erreur réseau");
  return data;
}

/* ---------- Notifications ---------- */
function toast(message, type = "info") {
  const icons = { info: "ℹ️", success: "✅", error: "⚠️", win: "🎉" };
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] ?? ""}</span><span>${esc(message)}</span>`;
  $("#toasts").append(el);
  setTimeout(() => {
    el.classList.add("out");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, 3800);
}

function celebrate() {
  const wrap = document.createElement("div");
  wrap.className = "confetti";
  const colors = ["#7c5cff", "#00d1ff", "#ffc940", "#22d37f", "#ff4d5e"];
  for (let i = 0; i < 70; i++) {
    const p = document.createElement("i");
    p.style.cssText = `left:${Math.random() * 100}%;background:${colors[i % colors.length]};animation-delay:${Math.random() * 0.4}s;animation-duration:${1.6 + Math.random() * 1.4}s`;
    wrap.append(p);
  }
  document.body.append(wrap);
  setTimeout(() => wrap.remove(), 3600);
}

/* ---------- Solde (animé) ---------- */
let balanceFrame = 0;
function setBalance(value) {
  if (value === undefined || value === null) return;
  const el = $("#balance");
  const from = state.balance;
  state.balance = value;
  cancelAnimationFrame(balanceFrame);
  if (from === value) {
    el.textContent = fmt(value);
    return;
  }
  el.classList.remove("up", "down");
  el.classList.add(value > from ? "up" : "down");
  const start = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - start) / 650);
    el.textContent = fmt(Math.round(from + (value - from) * (1 - (1 - k) ** 3)));
    if (k < 1) balanceFrame = requestAnimationFrame(step);
    else setTimeout(() => el.classList.remove("up", "down"), 500);
  };
  balanceFrame = requestAnimationFrame(step);
}

/* ---------- Identité visuelle ---------- */
function hue(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 360;
}
function initials(name) {
  const words = String(name).replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return (words.length > 1 ? words[0][0] + words[1][0] : words[0].slice(0, 2)).toUpperCase();
}
const crest = (name, cls = "") => `<span class="crest ${cls}" style="--h:${hue(name)}">${esc(initials(name))}</span>`;
function flag(league) {
  const l = String(league).toLowerCase();
  if (/france|ligue 1/.test(l)) return "🇫🇷";
  if (/epl|premier|england/.test(l)) return "🏴󠁧󠁢󠁥󠁮󠁧󠁿";
  if (/spain|la ?liga/.test(l)) return "🇪🇸";
  if (/ital|serie a/.test(l)) return "🇮🇹";
  if (/german|bundesliga/.test(l)) return "🇩🇪";
  if (/champions|uefa|europa/.test(l)) return "⭐";
  if (/nba|basket/.test(l)) return "🏀";
  return "🏆";
}
const SPORT_ICON = { football: "⚽", basketball: "🏀" };
const SPORT_NAME = { football: "Football", basketball: "Basketball" };
const OUT_LABEL = { home: "1", draw: "N", away: "2" };

/* ---------- Dates ---------- */
const DAY = 86_400_000;
const dayStart = (ms) => new Date(ms).setHours(0, 0, 0, 0);
const dayDiff = (ms) => Math.round((dayStart(ms) - dayStart(Date.now())) / DAY);
const hhmm = (ms) => new Date(ms).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
function shortDay(ms) {
  const d = dayDiff(ms);
  if (d === 0) return "Auj.";
  if (d === 1) return "Demain";
  if (d === -1) return "Hier";
  return new Date(ms).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" });
}
function countBy(items, key) {
  const m = new Map();
  for (const x of items) m.set(key(x), (m.get(key(x)) ?? 0) + 1);
  return m;
}
function groupBy(items, key) {
  const m = new Map();
  for (const x of items) (m.get(key(x)) ?? m.set(key(x), []).get(key(x))).push(x);
  return m;
}

/* =========================================================
   Routeur
   ========================================================= */
const ROUTES = {
  sports: renderSports,
  casino: renderCasino,
  crash: renderCrash,
  roulette: renderRoulette,
  slots: renderSlots,
  blackjack: renderBlackjack,
  compte: renderAccount,
};
const CASINO_PAGES = new Set(["casino", "crash", "roulette", "slots", "blackjack"]);
let sheetAfterRoute = false;

function route() {
  cleanups.splice(0).forEach((fn) => fn());
  const wanted = location.hash.replace(/^#\/?/, "").split("/")[0] || "sports";
  const page = ROUTES[wanted] ? wanted : "sports";
  state.page = page;
  document.body.dataset.page = page;
  $$(".mainnav [data-nav]").forEach((a) =>
    a.classList.toggle("active", a.dataset.nav === page || (a.dataset.nav === "casino" && CASINO_PAGES.has(page) && page !== "crash")),
  );
  $$(".bottombar [data-nav]").forEach((a) =>
    a.classList.toggle("active", a.dataset.nav === page || (a.dataset.nav === "casino" && CASINO_PAGES.has(page))),
  );
  closeSheet();
  window.scrollTo({ top: 0, behavior: "instant" });
  ROUTES[page]();
  if (sheetAfterRoute) {
    sheetAfterRoute = false;
    openSheet();
  }
}
window.addEventListener("hashchange", () => state.me && route());

/* =========================================================
   Paris sportifs
   ========================================================= */
async function loadEvents() {
  try {
    const d = await api("sports/events");
    state.events = d.events;
    state.live = d.live ?? [];
    state.results = d.results ?? [];
    state.loadedAt = Date.now();
    syncSlipWithEvents();
    renderSportsData();
  } catch {
    /* nouvel essai au prochain rafraîchissement */
  }
}

const feedTag = () =>
  state.me?.feed === "demo"
    ? `<span class="feed-tag">🎲 Démo · matchs simulés</span>`
    : `<span class="feed-tag real">● Cotes en direct</span>`;

function renderSports() {
  view.innerHTML = `
    ${heroHtml()}
    <section class="section" id="live-section"></section>
    <section class="section" id="top-section"></section>
    <section class="section" id="all-matches">
      <div class="section-head"><h3>Tous les matchs <span class="muted count-note" id="match-count"></span></h3>${feedTag()}</div>
      <div class="toolbar" id="day-chips"></div>
      <div class="toolbar league-chips" id="league-chips"></div>
      <div id="match-list">${'<div class="skeleton"></div>'.repeat(6)}</div>
    </section>
    <section class="section" id="results-section"></section>`;
  startHero();
  renderSidebar();
  if (state.loadedAt) renderSportsData();
  if (Date.now() - state.loadedAt > 15_000) loadEvents();
  renderSlip();
}

function heroHtml() {
  return `<div class="hero" id="hero">
    <div class="slide s1 active">
      <span class="eyebrow">Bonus quotidien</span>
      <h2>500 jetons offerts chaque jour</h2>
      <p>Reviens toutes les 24 h pour recharger ton solde gratuitement.</p>
      <button class="btn btn-gold" data-action="bonus">Récupérer mon bonus</button>
      <div class="slide-art">🎁</div>
    </div>
    <div class="slide s2">
      <span class="eyebrow">Jeu original</span>
      <h2>Crash : encaisse avant l'explosion</h2>
      <p>Le multiplicateur grimpe jusqu'à ×1000. À toi de choisir quand sortir.</p>
      <a class="btn btn-primary" href="#/crash">Jouer au Crash</a>
      <div class="slide-art">🚀</div>
    </div>
    <div class="slide s3">
      <span class="eyebrow">Paris combinés</span>
      <h2>Jusqu'à 10 matchs, cotes multipliées</h2>
      <p>Ajoute plusieurs sélections à ton ticket et fais grimper ta cote totale.</p>
      <button class="btn btn-primary" data-action="scroll-matches">Voir les matchs</button>
      <div class="slide-art">⚡</div>
    </div>
    <div class="dots"><button class="active" data-dot="0" aria-label="Diapo 1"></button><button data-dot="1" aria-label="Diapo 2"></button><button data-dot="2" aria-label="Diapo 3"></button></div>
  </div>`;
}

function startHero() {
  const hero = $("#hero");
  let current = 0;
  const show = (n) => {
    current = n;
    $$(".slide", hero).forEach((s, i) => s.classList.toggle("active", i === n));
    $$(".dots button", hero).forEach((d, i) => d.classList.toggle("active", i === n));
  };
  let timer = setInterval(() => show((current + 1) % 3), 6500);
  hero.addEventListener("click", (e) => {
    const dot = e.target.closest("[data-dot]");
    if (!dot) return;
    show(Number(dot.dataset.dot));
    clearInterval(timer);
    timer = setInterval(() => show((current + 1) % 3), 6500);
  });
  onLeave(() => clearInterval(timer));
}

function renderSportsData() {
  if (state.page !== "sports") return;
  renderSidebar();
  renderDayChips();
  renderLeagueChips();
  renderLive();
  renderTop();
  renderMatchList();
  renderResults();
}

const sideLink = ({ attr, value, ico, label, n, active }) =>
  `<button class="side-link ${active ? "active" : ""}" ${attr}="${esc(value)}"><span class="ico">${ico}</span><span class="lbl">${esc(label)}</span><span class="n">${n}</span></button>`;

function renderSidebar() {
  const { sport, league } = state.filter;
  const bySport = countBy(state.events, (e) => e.sport);
  const byLeague = countBy(
    state.events.filter((e) => sport === "all" || e.sport === sport),
    (e) => e.league,
  );
  $("#sidebar").innerHTML = `
    <div class="side-group"><h4>Sports</h4>
      ${sideLink({ attr: "data-filter-sport", value: "all", ico: "🔥", label: "Tous les sports", n: state.events.length, active: sport === "all" && !league })}
      ${[...bySport].map(([s, n]) => sideLink({ attr: "data-filter-sport", value: s, ico: SPORT_ICON[s] ?? "🏆", label: SPORT_NAME[s] ?? s, n, active: sport === s && !league })).join("")}
    </div>
    <div class="side-group"><h4>Compétitions</h4>
      ${[...byLeague].map(([l, n]) => sideLink({ attr: "data-filter-league", value: l, ico: flag(l), label: l, n, active: league === l })).join("")}
    </div>
    <div class="side-group"><h4>Casino</h4>
      <a class="side-link" href="#/crash"><span class="ico">🚀</span><span class="lbl">Crash</span></a>
      <a class="side-link" href="#/roulette"><span class="ico">🎡</span><span class="lbl">Roulette</span></a>
      <a class="side-link" href="#/slots"><span class="ico">🍒</span><span class="lbl">Machine à sous</span></a>
      <a class="side-link" href="#/blackjack"><span class="ico">🃏</span><span class="lbl">Blackjack</span></a>
    </div>
    <div class="side-promo"><b>🎁 Bonus quotidien</b><p>500 jetons offerts toutes les 24 h.</p><button class="btn btn-gold btn-sm" data-action="bonus">Récupérer</button></div>`;
}

const DAYS = [
  ["all", "Tous"],
  ["soon", "⏱ Moins de 3 h"],
  ["today", "Aujourd'hui"],
  ["tomorrow", "Demain"],
];
function renderDayChips() {
  const el = $("#day-chips");
  if (el)
    el.innerHTML = DAYS.map(
      ([k, l]) => `<button class="chip ${state.filter.day === k ? "active" : ""}" data-filter-day="${k}">${l}</button>`,
    ).join("");
}
function renderLeagueChips() {
  const el = $("#league-chips");
  if (!el) return;
  el.innerHTML =
    `<button class="chip ${!state.filter.league ? "active" : ""}" data-filter-league="">Toutes</button>` +
    [...countBy(state.events, (e) => e.league)]
      .map(([l]) => `<button class="chip ${state.filter.league === l ? "active" : ""}" data-filter-league="${esc(l)}">${flag(l)} ${esc(l)}</button>`)
      .join("");
}

function filteredEvents() {
  const { sport, league, day } = state.filter;
  const now = Date.now();
  return state.events.filter((e) => {
    if (sport !== "all" && e.sport !== sport) return false;
    if (league && e.league !== league) return false;
    if (day === "soon") return e.starts_at - now < 3 * 3_600_000;
    if (day === "today") return dayDiff(e.starts_at) === 0;
    if (day === "tomorrow") return dayDiff(e.starts_at) === 1;
    return true;
  });
}

const outcomesOf = (e) => (e.odds.draw ? ["home", "draw", "away"] : ["home", "away"]);

function oddBtn(e, o) {
  const price = e.odds[o];
  if (!price) return `<button class="odd locked" disabled>🔒</button>`;
  const picked = state.slip.get(e.id)?.outcome === o;
  return `<button class="odd ${picked ? "picked" : ""}" data-ev="${esc(e.id)}" data-o="${o}"><span class="odd-label">${OUT_LABEL[o]}</span><span class="odd-price">${price.toFixed(2)}</span></button>`;
}
const oddsRow = (e) => `<div class="odds-row" style="--cols:${outcomesOf(e).length}">${outcomesOf(e).map((o) => oddBtn(e, o)).join("")}</div>`;

function renderMatchList() {
  const list = $("#match-list");
  if (!list) return;
  const events = filteredEvents();
  $("#match-count").textContent = events.length ? `· ${events.length}` : "";
  if (!events.length) {
    list.innerHTML = `<div class="empty"><div class="big">🔎</div><b>Aucun match pour ce filtre</b><button class="btn btn-sm" data-action="reset-filters">Tout afficher</button></div>`;
    return;
  }
  list.innerHTML = [...groupBy(events, (e) => e.league)]
    .map(
      ([league, items]) => `
      <div class="league-block">
        <div class="league-head">
          <div class="league-name"><span class="flag">${flag(league)}</span>${esc(league)} <small>${items.length}</small></div>
          <div class="odds-labels" style="--cols:${outcomesOf(items[0]).length}">${outcomesOf(items[0]).map((o) => `<span>${OUT_LABEL[o]}</span>`).join("")}</div>
        </div>
        ${items
          .map(
            (e) => `
          <div class="match">
            <div class="match-time"><b>${hhmm(e.starts_at)}</b><span>${shortDay(e.starts_at)}</span></div>
            <div class="match-teams">
              <div class="team">${crest(e.home)}<span>${esc(e.home)}</span></div>
              <div class="team">${crest(e.away)}<span>${esc(e.away)}</span></div>
            </div>
            ${oddsRow(e)}
          </div>`,
          )
          .join("")}
      </div>`,
    )
    .join("");
}

function topEvents() {
  const soon = state.events.filter((e) => e.starts_at - Date.now() < 2 * DAY);
  const pool = soon.length >= 4 ? soon : state.events;
  // « À la une » = les affiches les plus serrées (cotes domicile/extérieur proches).
  const gap = (e) => Math.abs(Math.log(e.odds.home ?? 1) - Math.log(e.odds.away ?? 1));
  return [...pool].sort((a, b) => gap(a) - gap(b)).slice(0, 8).sort((a, b) => a.starts_at - b.starts_at);
}

function renderTop() {
  const sec = $("#top-section");
  if (!sec) return;
  const top = topEvents();
  sec.innerHTML = top.length
    ? `<div class="section-head"><h3>🔥 À la une</h3><span class="note">Les affiches les plus serrées</span></div>
       <div class="scroller">${top
         .map(
           (e) => `
         <div class="top-card">
           <div class="top-head"><span>${flag(e.league)} ${esc(e.league)}</span><span>${shortDay(e.starts_at)} · ${hhmm(e.starts_at)}</span></div>
           <div class="top-teams">
             <div class="tt">${crest(e.home, "crest-lg")}<span>${esc(e.home)}</span></div>
             <span class="vs">VS</span>
             <div class="tt">${crest(e.away, "crest-lg")}<span>${esc(e.away)}</span></div>
           </div>
           ${oddsRow(e)}
         </div>`,
         )
         .join("")}</div>`
    : "";
}

function renderLive() {
  const sec = $("#live-section");
  if (!sec) return;
  sec.innerHTML = state.live.length
    ? `<div class="section-head"><h3><span class="live-dot"></span>En direct</h3><span class="note">Paris fermés pendant le match</span></div>
       <div class="scroller">${state.live
         .map(
           (e) => `
         <div class="top-card live-card">
           <div class="top-head"><span class="live-badge"><span class="live-dot"></span>LIVE</span><span>${flag(e.league)} ${esc(e.league)}</span></div>
           <div class="top-teams">
             <div class="tt">${crest(e.home, "crest-lg")}<span>${esc(e.home)}</span></div>
             <span class="vs">–</span>
             <div class="tt">${crest(e.away, "crest-lg")}<span>${esc(e.away)}</span></div>
           </div>
           <div class="live-note">Commencé il y a ${Math.max(1, Math.round((Date.now() - e.starts_at) / 60_000))} min</div>
         </div>`,
         )
         .join("")}</div>`
    : "";
}

function renderResults() {
  const sec = $("#results-section");
  if (!sec) return;
  const results = state.results.slice(0, 9);
  sec.innerHTML = results.length
    ? `<div class="section-head"><h3>Derniers résultats</h3></div>
       <div class="results">${results
         .map((r) => {
           if (r.status === "cancelled")
             return `<div class="result"><div class="result-league">${flag(r.league)} ${esc(r.league)}</div><div>${esc(r.home)} – ${esc(r.away)}</div><div class="result-void">Match annulé · paris remboursés</div></div>`;
           const homeWon = r.home_score > r.away_score;
           const awayWon = r.away_score > r.home_score;
           return `<div class="result">
             <div class="result-league">${flag(r.league)} ${esc(r.league)}</div>
             <div class="result-row ${awayWon ? "lose" : ""}"><span class="team">${crest(r.home)}<span>${esc(r.home)}</span></span><b>${r.home_score}</b></div>
             <div class="result-row ${homeWon ? "lose" : ""}"><span class="team">${crest(r.away)}<span>${esc(r.away)}</span></span><b>${r.away_score}</b></div>
           </div>`;
         })
         .join("")}</div>`
    : "";
}

/* =========================================================
   Ticket
   ========================================================= */
function saveSlip() {
  try {
    localStorage.setItem("pilotcasino-slip", JSON.stringify([...state.slip.values()]));
  } catch {
    /* stockage indisponible : le ticket reste en mémoire */
  }
}
function loadSlip() {
  try {
    const legs = JSON.parse(localStorage.getItem("pilotcasino-slip") ?? "[]");
    state.slip = new Map(legs.map((l) => [l.eventId, l]));
  } catch {
    state.slip = new Map();
  }
}

function toggleSelection(id, outcome) {
  const ev = state.events.find((e) => e.id === id);
  if (!ev) return;
  const current = state.slip.get(id);
  if (current?.outcome === outcome) state.slip.delete(id);
  else {
    if (!current && state.slip.size >= 10) return toast("Maximum 10 sélections par ticket", "error");
    state.slip.set(id, { eventId: id, outcome, price: ev.odds[outcome], home: ev.home, away: ev.away, league: ev.league });
    state.lastAdded = id;
  }
  if (state.slipTab !== "slip") state.slipTab = "slip";
  saveSlip();
  refreshOddButtons(id);
  renderSlip();
}

function refreshOddButtons(id) {
  $$(`.odd[data-ev="${CSS.escape(id)}"]`).forEach((b) => b.classList.toggle("picked", state.slip.get(id)?.outcome === b.dataset.o));
}

/** Met à jour les cotes du ticket et retire les matchs qui ont commencé. */
function syncSlipWithEvents() {
  let changed = false;
  let removed = 0;
  for (const [id, leg] of state.slip) {
    const ev = state.events.find((e) => e.id === id);
    const price = ev?.odds[leg.outcome];
    if (!price) {
      state.slip.delete(id);
      removed++;
      changed = true;
    } else if (price !== leg.price) {
      leg.price = price;
      leg.changed = true;
      changed = true;
    }
  }
  if (removed) toast(`${removed} match(s) ont commencé et ont été retirés du ticket`, "info");
  if (changed) {
    saveSlip();
    renderSlip();
  }
}

const totalOdds = () => Math.round([...state.slip.values()].reduce((p, l) => p * l.price, 1) * 100) / 100;
const pickLabel = (l) => (l.outcome === "draw" ? "Match nul" : l.outcome === "home" ? l.home : l.away);

function renderSlipCounts() {
  const n = state.slip.size;
  $("#slip-count").textContent = n;
  $("#bb-badge").textContent = n;
  $("#bb-badge").classList.toggle("hidden", !n);
  $("#open-count").textContent = state.bets.filter((b) => b.status === "open").length;
  $$("[data-slip-tab]").forEach((b) => b.classList.toggle("active", b.dataset.slipTab === state.slipTab));
  const fab = $("#slip-fab");
  fab.classList.toggle("hidden", !n || document.body.classList.contains("sheet-open"));
  if (n)
    fab.innerHTML = `<span><i class="fab-count">${n}</i>${n > 1 ? "Combiné" : "Simple"}</span><span>Cote ${totalOdds().toFixed(2)} · Voir le ticket →</span>`;
}

function renderSlip() {
  renderSlipCounts();
  const body = $("#slip-body");
  if (state.slipTab === "bets") {
    body.innerHTML = state.bets.length
      ? `<div class="mybets">${state.bets.map(betCard).join("")}</div>`
      : `<div class="slip-empty"><div class="ticket-ico">📋</div><b>Aucun pari pour l'instant</b><span>Tes paris en cours et terminés apparaîtront ici.</span></div>`;
    return;
  }
  const legs = [...state.slip.values()];
  if (!legs.length) {
    body.innerHTML = `<div class="slip-empty"><div class="ticket-ico">🎫</div><b>Ton ticket est vide</b><span>Clique sur une cote pour ajouter une sélection.</span></div>`;
    return;
  }
  const odds = totalOdds();
  body.innerHTML = `
    <div class="slip-type"><span>${legs.length === 1 ? "Pari simple" : `Combiné · ${legs.length} sélections`}</span><button data-action="clear-slip">Tout effacer</button></div>
    <div class="legs">${legs
      .map(
        (l) => `<div class="leg ${l.changed ? "changed" : ""} ${l.eventId === state.lastAdded ? "new" : ""}">
          <div class="leg-pick"><span>${esc(pickLabel(l))}</span><b>${l.price.toFixed(2)}</b></div>
          <div class="leg-match">${flag(l.league)} ${esc(l.home)} – ${esc(l.away)}</div>
          ${l.changed ? `<div class="leg-warn">⚠ Cote mise à jour</div>` : ""}
          <button class="leg-x" data-remove="${esc(l.eventId)}" aria-label="Retirer">✕</button>
        </div>`,
      )
      .join("")}</div>
    <div class="slip-foot">
      <div class="stake"><label for="stake">Mise</label><input id="stake" type="number" inputmode="numeric" min="1" value="${state.stake}" /><span>🪙</span></div>
      <div class="quick"><button data-stake="10">+10</button><button data-stake="50">+50</button><button data-stake="100">+100</button><button data-stake="max">Max</button></div>
      <div class="slip-sum">
        <div><span>Cote totale</span><b>${odds.toFixed(2)}</b></div>
        <div class="potential"><span>Gain potentiel</span><b id="sum-win">${fmt(Math.floor(state.stake * odds))} 🪙</b></div>
      </div>
      <button class="btn btn-primary btn-lg btn-block" id="place-bet">Parier ${fmt(state.stake)} 🪙</button>
    </div>`;
  state.lastAdded = null;
}

function updateSlipTotals() {
  const win = $("#sum-win");
  if (win) win.textContent = `${fmt(Math.floor(state.stake * totalOdds()))} 🪙`;
  const btn = $("#place-bet");
  if (btn) btn.textContent = `Parier ${fmt(state.stake)} 🪙`;
}

async function placeBet(btn) {
  if (!state.slip.size) return;
  if (state.stake < 1) return toast("Mise invalide", "error");
  if (state.stake > state.balance) return toast("Solde insuffisant", "error");
  btn.disabled = true;
  btn.textContent = "Validation…";
  try {
    const legs = [...state.slip.values()].map(({ eventId, outcome, price }) => ({ eventId, outcome, price }));
    const r = await api("sports/bets", { legs, stake: state.stake });
    setBalance(r.balance);
    toast(`Pari validé ! Gain potentiel : ${fmt(r.potentialWin)} 🪙`, "success");
    const ids = [...state.slip.keys()];
    state.slip.clear();
    saveSlip();
    ids.forEach(refreshOddButtons);
    state.slipTab = "bets";
    await loadBets();
    renderSlip();
  } catch (err) {
    toast(err.message, "error");
    await loadEvents();
    renderSlip();
  }
}

const BET_STATUS = { open: "En cours", won: "Gagné", lost: "Perdu", void: "Remboursé" };
function betCard(b) {
  const mark = { won: "✓", lost: "✕", void: "–", pending: "" };
  const gain =
    b.status === "open"
      ? `Gain pot. <b>${fmt(b.potential_win)}</b>`
      : b.status === "lost"
        ? `<b class="neg">0</b>`
        : `<b class="pos">+${fmt(b.payout)}</b>`;
  return `<div class="bet-card">
    <div class="bet-card-head"><span>${b.legs.length > 1 ? `Combiné ×${b.legs.length}` : "Simple"} · ${shortDay(b.created_at)} ${hhmm(b.created_at)}</span><span class="tag ${b.status}">${BET_STATUS[b.status]}</span></div>
    <div class="bet-legs">${b.legs
      .map(
        (l) => `<div class="bet-leg">
          <span class="st ${l.result}">${mark[l.result] ?? ""}</span>
          <div><b>${esc(l.outcome === "draw" ? "Match nul" : l.outcome === "home" ? l.home : l.away)}</b>
            <small>${esc(l.home)} – ${esc(l.away)}${l.home_score !== null ? ` · ${l.home_score}-${l.away_score}` : ""}</small></div>
          <b>${l.price.toFixed(2)}</b>
        </div>`,
      )
      .join("")}</div>
    <div class="bet-card-foot"><span>Mise <b>${fmt(b.stake)}</b> · Cote <b>${b.total_odds.toFixed(2)}</b></span><span>${gain}</span></div>
  </div>`;
}

async function loadBets() {
  try {
    const { bets, balance } = await api("sports/bets");
    const before = new Map(state.bets.map((b) => [b.id, b.status]));
    for (const b of bets) {
      if (before.get(b.id) !== "open" || b.status === "open") continue;
      if (b.status === "won") {
        toast(`Pari gagné ! +${fmt(b.payout)} 🪙`, "win");
        celebrate();
      } else if (b.status === "void") toast(`Pari remboursé : +${fmt(b.payout)} 🪙`, "info");
    }
    state.bets = bets;
    setBalance(balance);
    if (state.slipTab === "bets") renderSlip();
    else renderSlipCounts();
  } catch {
    /* nouvel essai plus tard */
  }
}

function openSheet() {
  if (state.page !== "sports") {
    sheetAfterRoute = true;
    location.hash = "#/sports";
    return;
  }
  document.body.classList.add("sheet-open");
  renderSlip();
}
function closeSheet() {
  document.body.classList.remove("sheet-open");
  renderSlipCounts();
}

/* =========================================================
   Casino — lobby
   ========================================================= */
const GAMES = [
  { id: "crash", name: "Crash", desc: "Encaisse avant l'explosion", art: "🚀", cls: "g-crash", ribbon: "🔥 HOT", meta: "RTP ≈ 96,5 %" },
  { id: "roulette", name: "Roulette", desc: "Européenne, un seul zéro", art: "🎡", cls: "g-roulette", ribbon: "CLASSIQUE", meta: "RTP 97,3 %" },
  { id: "slots", name: "Fruit Frenzy", desc: "Machine à sous 3 rouleaux", art: "🍒", cls: "g-slots", ribbon: "JACKPOT ×500", meta: "RTP 93,5 %" },
  { id: "blackjack", name: "Blackjack", desc: "Bats le croupier sans dépasser 21", art: "🃏", cls: "g-blackjack", ribbon: "STRATÉGIE", meta: "Blackjack 3:2" },
];
const SOON = [
  { name: "Plinko", art: "🔻" },
  { name: "Mines", art: "💣" },
  { name: "Poker", art: "♠️" },
];

function renderCasino() {
  view.innerHTML = `
    <div class="page-head"><div><h1>Casino</h1><p>Des jeux originaux, des parties instantanées.</p></div></div>
    <div class="games">
      ${GAMES.map(
        (g) => `<a class="game-tile ${g.cls}" href="#/${g.id}">
          <span class="ribbon">${g.ribbon}</span>
          <div class="art">${g.art}</div>
          <h3>${g.name}</h3><p>${g.desc}</p>
          <div class="meta"><span>${g.meta}</span></div>
        </a>`,
      ).join("")}
      ${SOON.map(
        (g) => `<div class="game-tile g-soon soon"><span class="ribbon">BIENTÔT</span><div class="art">${g.art}</div><h3>${g.name}</h3><p>Bientôt disponible</p></div>`,
      ).join("")}
    </div>`;
}

const gameBar = (title, tag) =>
  `<div class="game-bar"><a href="#/casino" class="back" aria-label="Retour au casino">←</a><h1>${title}</h1>${tag ? `<span class="rtp">${tag}</span>` : ""}</div>`;

function amountHtml(id, value, max = 10_000) {
  return `<div class="amount">
    <input id="${id}" type="number" inputmode="numeric" min="1" max="${max}" value="${value}" />
    <button data-amt="${id}" data-op="half">½</button><button data-amt="${id}" data-op="double">×2</button><button data-amt="${id}" data-op="max">Max</button>
  </div>`;
}

function adjustAmount(id, op) {
  const input = $(`#${id}`);
  if (!input || input.disabled) return;
  const max = Number(input.max) || 10_000;
  const v = Math.floor(Number(input.value)) || 1;
  const next = op === "half" ? Math.floor(v / 2) : op === "double" ? v * 2 : state.balance;
  input.value = Math.max(1, Math.min(next, max, Math.max(1, state.balance)));
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function readAmount(id, max = 10_000) {
  const v = Math.floor(Number($(`#${id}`)?.value));
  if (!Number.isFinite(v) || v < 1) return toast("Mise invalide", "error"), 0;
  if (v > max) return toast(`Mise maximum : ${fmt(max)}`, "error"), 0;
  if (v > state.balance) return toast("Solde insuffisant", "error"), 0;
  return v;
}

/** Barre d'espace = action principale du jeu (hors champs de saisie et boutons). */
function onSpace(fn) {
  const handler = (e) => {
    if (e.code !== "Space" || e.repeat) return;
    if (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(document.activeElement?.tagName ?? "")) return;
    e.preventDefault();
    fn();
  };
  window.addEventListener("keydown", handler);
  onLeave(() => window.removeEventListener("keydown", handler));
}

/* =========================================================
   Crash
   ========================================================= */
const cr = { growth: 0.00006, round: null, startedLocal: 0, raf: 0, poll: 0, auto: false, autoVal: "2.00", bet: 10, redraw: null };
const crashChance = (m) => Math.min(100, 97 / (m + 0.01));

function renderCrash() {
  view.innerHTML = `<div class="game-page">
    ${gameBar("Crash", "RTP ≈ 96,5 %")}
    <div class="crash-hist" id="cr-hist"></div>
    <div class="game-grid">
      <div class="crash-stage">
        <canvas id="cr-canvas"></canvas>
        <div class="crash-mult" id="cr-mult"><div><b id="cr-m">1.00×</b><small id="cr-sub">Place ta mise et décolle</small></div></div>
      </div>
      <div class="panel controls">
        <div><div class="ctrl-label">Mise</div>${amountHtml("cr-bet", cr.bet)}</div>
        <div>
          <div class="toggle-row"><span class="ctrl-label">Encaissement auto</span><button class="switch ${cr.auto ? "on" : ""}" id="cr-auto-toggle" role="switch" aria-checked="${cr.auto}" aria-label="Encaissement automatique"></button></div>
          <div class="amount ${cr.auto ? "" : "disabled"}" id="cr-auto-box" style="margin-top:9px"><input id="cr-auto" type="number" inputmode="decimal" step="0.01" min="1.01" max="1000" value="${cr.autoVal}" /><span class="suffix">×</span></div>
        </div>
        <button class="btn btn-primary btn-lg btn-block" id="cr-main" data-mode="start">Lancer</button>
        <div class="info-list" id="cr-info"></div>
        <p class="muted" style="margin:0;font-size:12px;text-align:center"><span class="kbd">Espace</span> pour lancer ou encaisser</p>
      </div>
    </div>
  </div>`;
  $("#cr-main").addEventListener("click", crashMain);
  $("#cr-auto-toggle").addEventListener("click", (e) => {
    cr.auto = !cr.auto;
    e.currentTarget.classList.toggle("on", cr.auto);
    e.currentTarget.setAttribute("aria-checked", cr.auto);
    $("#cr-auto-box").classList.toggle("disabled", !cr.auto);
    paintCrashInfo();
  });
  $("#cr-bet").addEventListener("input", (e) => {
    cr.bet = e.target.value;
    paintCrashButton();
    paintCrashInfo();
  });
  $("#cr-auto").addEventListener("input", (e) => {
    cr.autoVal = e.target.value;
    paintCrashInfo();
  });
  onSpace(crashMain);
  const onResize = () => cr.redraw?.();
  window.addEventListener("resize", onResize);
  onLeave(() => {
    cancelAnimationFrame(cr.raf);
    clearInterval(cr.poll);
    window.removeEventListener("resize", onResize);
  });
  paintCrashInfo();
  api("crash")
    .then(applyCrash)
    .catch((err) => toast(err.message, "error"));
}

function applyCrash(d) {
  if (state.page !== "crash") return;
  setBalance(d.balance);
  cr.growth = d.growth;
  cr.round = d.round;
  $("#cr-hist").innerHTML =
    d.history.map((m) => `<span class="hpill ${m < 2 ? "low" : m < 10 ? "mid" : "high"}">${m.toFixed(2)}×</span>`).join("") ||
    `<span class="muted">Aucune manche jouée pour l'instant</span>`;
  cancelAnimationFrame(cr.raf);
  clearInterval(cr.poll);
  const r = d.round;
  const box = $("#cr-mult");
  if (r?.status === "playing") {
    cr.startedLocal = performance.now() - r.elapsedMs;
    cr.redraw = null;
    box.className = "crash-mult";
    cr.raf = requestAnimationFrame(crashFrame);
    // Seul le serveur connaît le point de crash : on lui demande l'état en continu.
    cr.poll = setInterval(async () => {
      const next = await api("crash").catch(() => null);
      if (!next || next.round?.status === "playing") return;
      applyCrash(next);
      if (next.round?.status === "won" && next.round.cashoutAt >= 5) celebrate();
    }, 250);
  } else if (r) {
    const end = Math.log(r.crashPoint) / cr.growth;
    const won = r.status === "won";
    cr.redraw = () => drawCrash(end, won ? "won" : "lost", won ? r.cashoutAt : null);
    cr.redraw();
    box.className = `crash-mult ${won ? "won" : "crashed"}`;
    $("#cr-m").textContent = won ? `+${fmt(r.payout)}` : `${r.crashPoint.toFixed(2)}×`;
    $("#cr-sub").textContent = won
      ? `🪙 gagnés · encaissé à ${r.cashoutAt.toFixed(2)}× (crash à ${r.crashPoint.toFixed(2)}×)`
      : `💥 Crash ! Mise perdue : ${fmt(r.bet)} 🪙`;
  } else {
    cr.redraw = () => drawCrash(0, "idle");
    cr.redraw();
  }
  paintCrashButton();
}

function crashFrame() {
  const r = cr.round;
  if (state.page !== "crash" || r?.status !== "playing") return;
  const elapsed = performance.now() - cr.startedLocal;
  const m = Math.floor(Math.exp(cr.growth * elapsed) * 100) / 100;
  const shown = r.autoCashout ? Math.min(m, r.autoCashout) : m;
  drawCrash(elapsed, "fly");
  $("#cr-m").textContent = `${shown.toFixed(2)}×`;
  $("#cr-sub").textContent = `Gain actuel : ${fmt(Math.floor(r.bet * shown))} 🪙`;
  if (!r.autoCashout) $("#cr-main").textContent = `Encaisser ${fmt(Math.floor(r.bet * m))} 🪙`;
  cr.raf = requestAnimationFrame(crashFrame);
}

function paintCrashButton() {
  const btn = $("#cr-main");
  if (!btn) return;
  const r = cr.round;
  const playing = r?.status === "playing";
  btn.disabled = false;
  if (playing && r.autoCashout) {
    btn.className = "btn btn-ghost btn-lg btn-block";
    btn.dataset.mode = "wait";
    btn.disabled = true;
    btn.textContent = `En vol · encaissement auto à ${r.autoCashout.toFixed(2)}×`;
  } else if (playing) {
    btn.className = "btn btn-win btn-lg btn-block";
    btn.dataset.mode = "cashout";
    btn.textContent = "Encaisser";
  } else {
    btn.className = "btn btn-primary btn-lg btn-block";
    btn.dataset.mode = "start";
    btn.textContent = `Lancer · ${fmt(Math.max(0, Math.floor(Number($("#cr-bet").value) || 0)))} 🪙`;
  }
  $("#cr-bet").disabled = playing;
  $("#cr-auto").disabled = playing;
  $("#cr-auto-toggle").disabled = playing;
}

function paintCrashInfo() {
  const el = $("#cr-info");
  if (!el) return;
  const bet = Math.max(0, Math.floor(Number($("#cr-bet").value) || 0));
  const auto = Number($("#cr-auto").value);
  const pct = (m) => `${crashChance(m).toFixed(1).replace(".", ",")} %`;
  el.innerHTML =
    cr.auto && auto >= 1.01
      ? `<div><span>Gain à ×${auto.toFixed(2)}</span><b>${fmt(Math.floor(bet * auto))} 🪙</b></div><div><span>Chance d'y arriver</span><b>${pct(auto)}</b></div>`
      : `<div><span>Chance d'atteindre ×2</span><b>${pct(2)}</b></div><div><span>Chance d'atteindre ×10</span><b>${pct(10)}</b></div>`;
}

async function crashMain() {
  const btn = $("#cr-main");
  if (!btn || btn.disabled) return;
  if (btn.dataset.mode === "cashout") {
    btn.disabled = true;
    try {
      const d = await api("crash/cashout", {});
      applyCrash(d);
      if (d.round?.status === "won" && d.round.cashoutAt >= 5) celebrate();
    } catch (err) {
      toast(err.message, "error");
      paintCrashButton();
    }
    return;
  }
  if (btn.dataset.mode !== "start") return;
  const bet = readAmount("cr-bet");
  if (!bet) return;
  let auto = null;
  if (cr.auto) {
    auto = Number($("#cr-auto").value);
    if (!(auto >= 1.01)) return toast("Encaissement auto minimum : ×1.01", "error");
  }
  btn.disabled = true;
  try {
    applyCrash(await api("crash/start", { bet, autoCashout: auto }));
  } catch (err) {
    toast(err.message, "error");
    paintCrashButton();
  }
}

function crashCtx() {
  const c = $("#cr-canvas");
  if (!c) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (!w || !h) return null;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}
function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const f = x / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}
function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}

function drawCrash(elapsed, mode, cashAt = null) {
  const cv = crashCtx();
  if (!cv) return;
  const { ctx, w, h } = cv;
  const g = cr.growth;
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 48, r: 28, t: 28, b: 32 };
  const mult = Math.exp(g * Math.max(0, elapsed));
  const tMax = Math.max(8000, elapsed * 1.22);
  const mMax = Math.max(2, 1 + (mult - 1) * 1.28);
  const X = (t) => pad.l + (t / tMax) * (w - pad.l - pad.r);
  const Y = (m) => h - pad.b - ((m - 1) / (mMax - 1)) * (h - pad.t - pad.b);

  // Grille
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  ctx.fillStyle = "rgba(255,255,255,0.38)";
  ctx.font = "600 11px Inter, system-ui, sans-serif";
  const sm = niceStep((mMax - 1) / 4);
  for (let k = 0; 1 + k * sm <= mMax + 1e-9; k++) {
    const m = 1 + k * sm;
    const y = Y(m);
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
    ctx.fillText(`${m < 10 ? m.toFixed(1) : Math.round(m)}×`, 8, y + 4);
  }
  const st = niceStep(tMax / 1000 / 5) * 1000;
  for (let t = st; t <= tMax; t += st) ctx.fillText(`${Math.round(t / 1000)}s`, X(t) - 8, h - 10);
  if (elapsed <= 0) return;

  // Courbe + remplissage
  const color = mode === "lost" ? "#ff4d5e" : mode === "won" ? "#22d37f" : "#7c5cff";
  const curve = new Path2D();
  for (let i = 0; i <= 100; i++) {
    const t = (elapsed * i) / 100;
    const x = X(t);
    const y = Y(Math.exp(g * t));
    if (i) curve.lineTo(x, y);
    else curve.moveTo(x, y);
  }
  const area = new Path2D(curve);
  area.lineTo(X(elapsed), Y(1));
  area.lineTo(X(0), Y(1));
  area.closePath();
  const fill = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
  fill.addColorStop(0, rgba(color, 0.42));
  fill.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = fill;
  ctx.fill(area);
  let stroke = color;
  if (mode === "fly") {
    stroke = ctx.createLinearGradient(X(0), 0, X(elapsed), 0);
    stroke.addColorStop(0, "#00d1ff");
    stroke.addColorStop(1, "#7c5cff");
  }
  ctx.save();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 4;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = color;
  ctx.shadowBlur = 16;
  ctx.stroke(curve);
  ctx.restore();

  // Point d'encaissement
  if (cashAt) {
    const x = X(Math.log(cashAt) / g);
    const y = Y(cashAt);
    ctx.beginPath();
    ctx.arc(x, y, 7, 0, Math.PI * 2);
    ctx.fillStyle = "#22d37f";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#090c14";
    ctx.stroke();
    ctx.font = "700 12px 'Space Grotesk', system-ui, sans-serif";
    ctx.fillText(`${cashAt.toFixed(2)}×`, x + 11, y - 10);
  }

  // Fusée ou explosion au bout de la courbe
  ctx.font = "30px system-ui, 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(mode === "fly" ? "🚀" : "💥", X(elapsed), Y(mult));
  ctx.textAlign = "start";
  ctx.textBaseline = "alphabetic";
}

/* =========================================================
   Roulette
   ========================================================= */
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const CHIPS = [
  [1, "#7d869b"],
  [5, "#e3344a"],
  [10, "#2f7bff"],
  [25, "#13a865"],
  [100, "#23263a"],
  [500, "#8b5cf6"],
];
const COLOR_FR = { red: "Rouge", black: "Noir", green: "Vert" };
const rl = { bets: new Map(), undo: [], chip: 10, rot: 0, spinning: false, history: [], last: null };
const numColor = (n) => (n === 0 ? "green" : RED.has(n) ? "red" : "black");
const rlTotal = () => [...rl.bets.values()].reduce((s, b) => s + b.amount, 0);
const chipColor = (amount) => CHIPS.reduce((c, [v, col]) => (amount >= v ? col : c), CHIPS[0][1]);
const shortAmt = (n) => (n >= 1000 ? `${Math.round(n / 100) / 10}k` : String(n));

function wheelSvg() {
  const c = 160;
  const R = 150;
  const r0 = 104;
  const seg = 360 / 37;
  const xy = (rad, deg) => {
    const a = (deg * Math.PI) / 180;
    return [(c + rad * Math.sin(a)).toFixed(2), (c - rad * Math.cos(a)).toFixed(2)];
  };
  const pt = (rad, deg) => xy(rad, deg).join(" ");
  const sectors = WHEEL.map((n, i) => {
    const a0 = i * seg - seg / 2;
    const a1 = i * seg + seg / 2;
    const fill = n === 0 ? "#12a05c" : RED.has(n) ? "#d42a3c" : "#151820";
    return `<path d="M${pt(R, a0)}A${R} ${R} 0 0 1 ${pt(R, a1)}L${pt(r0, a1)}A${r0} ${r0} 0 0 0 ${pt(r0, a0)}Z" fill="${fill}" stroke="#c9a24a" stroke-width=".6"/>`;
  }).join("");
  const labels = WHEEL.map(
    (n, i) =>
      `<text x="${c}" y="${c - 133}" transform="rotate(${(i * seg).toFixed(2)} ${c} ${c})" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="700" fill="#fff" font-family="Space Grotesk, sans-serif">${n}</text>`,
  ).join("");
  const spokes = [0, 45, 90, 135]
    .map((a) => {
      const [x1, y1] = xy(r0 - 4, a);
      const [x2, y2] = xy(r0 - 4, a + 180);
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#c9a24a" stroke-width="3" stroke-linecap="round" opacity=".7"/>`;
    })
    .join("");
  return `<svg viewBox="0 0 320 320" aria-hidden="true">
    <defs>
      <radialGradient id="rim" cx="50%" cy="50%" r="50%"><stop offset="86%" stop-color="#6b4420"/><stop offset="100%" stop-color="#26160a"/></radialGradient>
      <radialGradient id="cone" cx="40%" cy="35%" r="75%"><stop offset="0%" stop-color="#4a3420"/><stop offset="100%" stop-color="#140c05"/></radialGradient>
    </defs>
    <circle cx="${c}" cy="${c}" r="159" fill="url(#rim)"/>
    <circle cx="${c}" cy="${c}" r="151.5" fill="none" stroke="#e0b95c" stroke-width="2"/>
    ${sectors}${labels}
    <circle cx="${c}" cy="${c}" r="${r0}" fill="url(#cone)" stroke="#e0b95c" stroke-width="2"/>
    ${spokes}
  </svg>`;
}

const MOBILE = matchMedia("(max-width: 860px)");
const OUTSIDE_BETS = [
  ["low", "1-18", "out"],
  ["even", "Pair", "out"],
  ["red", "Rouge", "red small"],
  ["black", "Noir", "black small"],
  ["odd", "Impair", "out"],
  ["high", "19-36", "out"],
];
const DOZENS = ["1re 12", "2e 12", "3e 12"];

/** Tapis horizontal (desktop) ou vertical (mobile), comme sur les applis de casino. */
function rouletteBoardHtml(vertical = MOBILE.matches) {
  const cell = (cls, key, col, row, label) =>
    `<button class="cell ${cls}" data-key="${key}" style="grid-column:${col};grid-row:${row}">${label}</button>`;
  const cells = [];
  if (vertical) {
    cells.push(cell("green", "number:0", "3/6", 1, "0"));
    for (let row = 0; row < 12; row++)
      for (let col = 0; col < 3; col++) {
        const n = row * 3 + col + 1;
        cells.push(cell(numColor(n), `number:${n}`, col + 3, row + 2, n));
      }
    [1, 2, 3].forEach((column, i) => cells.push(cell("out", `column:${column}`, i + 3, 14, "2:1")));
    DOZENS.forEach((label, i) => cells.push(cell("out", `dozen:${i + 1}`, 2, `${2 + i * 4}/span 4`, `<span class="vlabel">${label}</span>`)));
    OUTSIDE_BETS.forEach(([key, label, cls], i) => cells.push(cell(cls, key, 1, `${2 + i * 2}/span 2`, `<span class="vlabel">${label}</span>`)));
  } else {
    cells.push(cell("green", "number:0", 1, "1/4", "0"));
    for (let col = 0; col < 12; col++)
      for (let row = 0; row < 3; row++) {
        const n = col * 3 + (3 - row);
        cells.push(cell(numColor(n), `number:${n}`, col + 2, row + 1, n));
      }
    [3, 2, 1].forEach((column, row) => cells.push(cell("out", `column:${column}`, 14, row + 1, "2:1")));
    DOZENS.forEach((label, i) => cells.push(cell("out", `dozen:${i + 1}`, `${2 + i * 4}/span 4`, 4, label)));
    OUTSIDE_BETS.forEach(([key, label, cls], i) => cells.push(cell(cls, key, `${2 + i * 2}/span 2`, 5, label)));
  }
  return cells.join("");
}

function renderRoulette() {
  const last = rl.last;
  view.innerHTML = `<div class="game-page">
    ${gameBar("Roulette", "RTP 97,3 %")}
    <div class="roulette-grid">
      <div class="panel wheel-panel">
        <div class="wheel-wrap">
          <div class="wheel-pointer"></div>
          <div class="wheel-spin" id="wheel-spin" style="transform:rotate(${rl.rot}deg)">${wheelSvg()}</div>
          <div class="wheel-center ${last ? last.color : ""}" id="wheel-center">${last ? last.n : "?"}</div>
        </div>
        <div class="result-banner" id="rl-result"></div>
        <div><div class="ctrl-label">Derniers numéros</div><div class="history" id="rl-history"></div></div>
      </div>
      <div class="panel">
        <div class="board-scroll"><div class="board ${MOBILE.matches ? "vertical" : ""}" id="board">${rouletteBoardHtml()}</div></div>
        <div class="roulette-controls">
          <div><div class="ctrl-label">Jeton</div><div class="chips" id="chips">${CHIPS.map(
            ([v, col]) => `<button class="chip-token ${v === rl.chip ? "active" : ""}" style="--c:${col}" data-chip="${v}">${v}</button>`,
          ).join("")}</div></div>
          <div class="rl-actions">
            <button class="btn" id="rl-undo">↶ Annuler</button>
            <button class="btn" id="rl-double">×2</button>
            <button class="btn" id="rl-clear">Effacer</button>
          </div>
          <div class="rl-bottom">
            <div class="rl-total">Mise totale<b id="rl-total">0</b></div>
            <button class="btn btn-primary btn-lg" id="rl-spin">Lancer la roue</button>
          </div>
        </div>
      </div>
    </div>
  </div>`;

  $("#chips").addEventListener("click", (e) => {
    const chip = e.target.closest("[data-chip]");
    if (!chip) return;
    rl.chip = Number(chip.dataset.chip);
    $$("#chips .chip-token").forEach((c) => c.classList.toggle("active", c === chip));
  });
  $("#board").addEventListener("click", (e) => {
    const cell = e.target.closest("[data-key]");
    if (!cell || rl.spinning) return;
    const total = rlTotal();
    if (total + rl.chip > state.balance) return toast("Solde insuffisant", "error");
    if (total + rl.chip > 100_000) return toast("Mise totale maximum : 100 000", "error");
    const key = cell.dataset.key;
    const [type, value] = key.split(":");
    const bet = rl.bets.get(key) ?? { type, value: value === undefined ? undefined : Number(value), amount: 0 };
    bet.amount += rl.chip;
    rl.bets.set(key, bet);
    rl.undo.push([key, rl.chip]);
    paintCell(cell);
    paintRouletteTotals();
  });
  $("#rl-undo").addEventListener("click", () => {
    if (rl.spinning) return;
    const last = rl.undo.pop();
    if (!last) return;
    const [key, amount] = last;
    const bet = rl.bets.get(key);
    if (bet) {
      bet.amount -= amount;
      if (bet.amount <= 0) rl.bets.delete(key);
    }
    paintAllCells();
  });
  $("#rl-clear").addEventListener("click", () => {
    if (rl.spinning) return;
    rl.bets.clear();
    rl.undo = [];
    paintAllCells();
  });
  $("#rl-double").addEventListener("click", () => {
    if (rl.spinning || !rl.bets.size) return;
    const total = rlTotal();
    if (total * 2 > state.balance) return toast("Solde insuffisant pour doubler", "error");
    if (total * 2 > 100_000) return toast("Mise totale maximum : 100 000", "error");
    for (const [key, bet] of rl.bets) {
      rl.undo.push([key, bet.amount]);
      bet.amount *= 2;
    }
    paintAllCells();
  });
  $("#rl-spin").addEventListener("click", spinRoulette);
  onSpace(spinRoulette);
  const onLayoutChange = () => {
    const board = $("#board");
    board.className = `board ${MOBILE.matches ? "vertical" : ""}`;
    board.innerHTML = rouletteBoardHtml();
    paintAllCells();
  };
  MOBILE.addEventListener("change", onLayoutChange);
  onLeave(() => MOBILE.removeEventListener("change", onLayoutChange));
  paintAllCells();
  paintRouletteHistory();
}

function paintCell(cell) {
  const bet = rl.bets.get(cell.dataset.key);
  let chip = cell.querySelector(".chip-on");
  if (!bet) return chip?.remove();
  if (!chip) {
    chip = document.createElement("span");
    chip.className = cell.dataset.key.startsWith("number:") ? "chip-on" : "chip-on side";
    cell.append(chip);
  }
  chip.style.setProperty("--c", chipColor(bet.amount));
  chip.textContent = shortAmt(bet.amount);
}
function paintAllCells() {
  $$("#board [data-key]").forEach(paintCell);
  paintRouletteTotals();
}
function paintRouletteTotals() {
  const total = rlTotal();
  $("#rl-total").textContent = `${fmt(total)} 🪙`;
  const btn = $("#rl-spin");
  btn.disabled = !total || rl.spinning;
  btn.textContent = rl.spinning ? "La roue tourne…" : total ? `Lancer · ${fmt(total)} 🪙` : "Place tes jetons";
}
function paintRouletteHistory() {
  const el = $("#rl-history");
  if (el)
    el.innerHTML =
      rl.history.map((h) => `<span class="hnum ${h.color}">${h.n}</span>`).join("") || `<span class="muted">Aucun tirage pour l'instant</span>`;
}

async function spinRoulette() {
  if (rl.spinning || !rl.bets.size) return;
  rl.spinning = true;
  paintRouletteTotals();
  const banner = $("#rl-result");
  banner.textContent = "";
  banner.className = "result-banner";
  $$("#board .hit").forEach((c) => c.classList.remove("hit"));
  const center = $("#wheel-center");
  center.className = "wheel-center";
  center.textContent = "";
  if (MOBILE.matches) $(".wheel-wrap").scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    const r = await api("roulette/spin", { bets: [...rl.bets.values()] });
    setBalance(r.balance - r.totalWin);
    const seg = 360 / 37;
    const target = (((-WHEEL.indexOf(r.number) * seg) % 360) + 360) % 360;
    const jitter = (Math.random() - 0.5) * seg * 0.6;
    rl.rot = Math.ceil(rl.rot / 360) * 360 + 360 * 6 + target + jitter;
    $("#wheel-spin").style.transform = `rotate(${rl.rot}deg)`;
    await sleep(5100);
    rl.last = { n: r.number, color: r.color };
    rl.history = [rl.last, ...rl.history].slice(0, 14);
    setBalance(r.balance);
    if (state.page !== "roulette") return;
    center.textContent = r.number;
    center.className = `wheel-center ${r.color}`;
    paintRouletteHistory();
    $(`#board [data-key="number:${r.number}"]`)?.classList.add("hit");
    if (r.totalWin > 0) {
      banner.textContent = `+${fmt(r.totalWin)} 🪙`;
      banner.className = "result-banner win";
      if (r.totalWin >= r.totalBet * 10) celebrate();
    } else {
      banner.textContent = `${r.number} ${COLOR_FR[r.color]} · pas de gain`;
      banner.className = "result-banner lose";
    }
  } catch (err) {
    toast(err.message, "error");
    if (state.page === "roulette") center.textContent = rl.last ? rl.last.n : "?";
  } finally {
    rl.spinning = false;
    if (state.page === "roulette") paintRouletteTotals();
  }
}

/* =========================================================
   Machine à sous
   ========================================================= */
const SYMS = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎"];
const PAYS = [
  ["💎", 500],
  ["🔔", 100],
  ["🍇", 50],
  ["🍊", 25],
  ["🍋", 15],
  ["🍒", 8],
];
const sl = { bet: 10, last: ["🍒", "💎", "🍋"], spinning: false };

function renderSlots() {
  view.innerHTML = `<div class="game-page">
    ${gameBar("Fruit Frenzy", "RTP 93,5 %")}
    <div class="game-grid">
      <div class="slots-machine" id="machine">
        <div class="slots-title">★ FRUIT FRENZY ★</div>
        <div class="bulbs">${"<i></i>".repeat(14)}</div>
        <div class="reels" id="reels">
          ${sl.last.map((s) => `<div class="reel"><div class="strip"><div class="sym">${s}</div></div></div>`).join("")}
          <div class="payline"></div>
        </div>
        <div class="result-banner" id="sl-result"></div>
      </div>
      <div class="panel controls">
        <div><div class="ctrl-label">Mise</div>${amountHtml("sl-bet", sl.bet)}</div>
        <button class="btn btn-gold btn-lg btn-block" id="sl-spin">Tourner</button>
        <div>
          <div class="ctrl-label">Table des gains <span>3 symboles identiques</span></div>
          <div class="paytable">
            ${PAYS.map(([s, m]) => `<div class="pay-row"><span>${s}${s}${s}</span><b>×${m}</b></div>`).join("")}
            <div class="pay-row"><span>🍒🍒 <small>deux cerises</small></span><b>×0,5</b></div>
          </div>
        </div>
        <p class="muted" style="margin:0;font-size:12px;text-align:center"><span class="kbd">Espace</span> pour tourner</p>
      </div>
    </div>
  </div>`;
  $("#sl-bet").addEventListener("input", (e) => (sl.bet = e.target.value));
  $("#sl-spin").addEventListener("click", spinSlots);
  onSpace(spinSlots);
}

function spinReel(reel, final, height, duration) {
  return new Promise((resolve) => {
    const strip = reel.querySelector(".strip");
    const current = strip.lastElementChild?.textContent ?? final;
    // Symboles de défilement purement décoratifs : le résultat vient du serveur.
    const filler = Array.from({ length: 16 + Math.round(duration / 110) }, () => SYMS[Math.floor(Math.random() * SYMS.length)]);
    const seq = [current, ...filler, final];
    strip.style.transition = "none";
    strip.style.transform = "translateY(0)";
    strip.innerHTML = seq.map((s) => `<div class="sym">${s}</div>`).join("");
    void strip.offsetHeight;
    reel.classList.add("spinning");
    strip.style.transition = `transform ${duration}ms cubic-bezier(.12,.8,.22,1)`;
    strip.style.transform = `translateY(-${(seq.length - 1) * height}px)`;
    setTimeout(() => reel.classList.remove("spinning"), duration - 250);
    setTimeout(() => {
      strip.style.transition = "none";
      strip.style.transform = "translateY(0)";
      strip.innerHTML = `<div class="sym">${final}</div>`;
      resolve();
    }, duration + 40);
  });
}

async function spinSlots() {
  if (sl.spinning) return;
  const bet = readAmount("sl-bet");
  if (!bet) return;
  sl.spinning = true;
  $("#sl-spin").disabled = true;
  const banner = $("#sl-result");
  banner.textContent = "";
  banner.className = "result-banner";
  $$("#reels .reel").forEach((r) => r.classList.remove("win"));
  $("#machine").classList.add("spinning");
  try {
    const r = await api("slots/spin", { bet });
    setBalance(r.balance - r.win);
    const reels = $$("#reels .reel");
    const height = reels[0].querySelector(".sym").offsetHeight;
    await Promise.all(reels.map((reel, i) => spinReel(reel, r.reels[i], height, 1100 + i * 420)));
    sl.last = r.reels;
    setBalance(r.balance);
    if (state.page !== "slots") return;
    if (r.win > 0) {
      banner.textContent = `+${fmt(r.win)} 🪙 · ×${String(r.multiplier).replace(".", ",")}`;
      banner.className = "result-banner win";
      const triple = r.reels.every((s) => s === r.reels[0]);
      reels.forEach((reel, i) => (triple || r.reels[i] === "🍒") && reel.classList.add("win"));
      if (r.multiplier >= 25) celebrate();
    } else {
      banner.textContent = "Pas de chance… retente !";
      banner.className = "result-banner lose";
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    sl.spinning = false;
    if (state.page === "slots") {
      $("#sl-spin").disabled = false;
      $("#machine").classList.remove("spinning");
    }
  }
}

/* =========================================================
   Blackjack
   ========================================================= */
const bj = { bet: 10, prev: { player: [], dealer: [] }, busy: false };

function renderBlackjack() {
  view.innerHTML = `<div class="game-page">
    ${gameBar("Blackjack", "Blackjack payé 3:2")}
    <div class="game-grid">
      <div class="table">
        <div class="hand"><div class="hand-label">Croupier <span class="hand-value" id="bj-dv">–</span></div><div class="cards" id="bj-dealer"></div></div>
        <div class="bj-banner" id="bj-banner"></div>
        <div class="table-text">Le croupier tire jusqu'à 16 et reste à 17<br />Blackjack payé 3 pour 2</div>
        <div class="hand"><div class="cards" id="bj-player"></div><div class="hand-label">Toi <span class="hand-value" id="bj-pv">–</span></div></div>
      </div>
      <div class="panel controls">
        <div id="bj-bet-zone">
          <div class="ctrl-label">Mise</div>${amountHtml("bj-bet", bj.bet)}
          <button class="btn btn-primary btn-lg btn-block" id="bj-deal" style="margin-top:12px">Distribuer</button>
        </div>
        <div id="bj-play-zone" class="hidden">
          <div class="ctrl-label">À toi de jouer <span id="bj-cur-bet"></span></div>
          <div class="bj-actions">
            <button class="btn btn-lg btn-win" data-bj="hit">Carte</button>
            <button class="btn btn-lg btn-gold" data-bj="stand">Rester</button>
            <button class="btn btn-lg" data-bj="double">Doubler</button>
          </div>
        </div>
        <ul class="rules">
          <li>Approche-toi de 21 sans le dépasser.</li>
          <li>Les figures valent 10, l'As 1 ou 11.</li>
          <li>Doubler : mise ×2 et une seule carte de plus.</li>
        </ul>
      </div>
    </div>
  </div>`;
  $("#bj-bet").addEventListener("input", (e) => (bj.bet = e.target.value));
  $("#bj-deal").addEventListener("click", dealBlackjack);
  $(".bj-actions").addEventListener("click", (e) => {
    const action = e.target.closest("[data-bj]")?.dataset.bj;
    if (action) blackjackAction(action);
  });
  onSpace(() => $("#bj-play-zone").classList.contains("hidden") && dealBlackjack());
  bj.prev = { player: [], dealer: [] };
  api("blackjack")
    .then((d) => drawBlackjack(d, false))
    .catch((err) => toast(err.message, "error"));
}

function cardHtml(card, delay, animate) {
  const deal = animate ? " deal" : "";
  const style = animate ? ` style="animation-delay:${delay}ms"` : "";
  if (card === "??") return `<div class="pcard back${deal}"${style}></div>`;
  const rank = card.slice(0, -1);
  const suit = card.slice(-1);
  const red = suit === "♥" || suit === "♦" ? " red" : "";
  return `<div class="pcard${red}${deal}"${style}><span class="tl">${rank}<br />${suit}</span><span class="mid">${suit}</span><span class="br">${rank}<br />${suit}</span></div>`;
}

function drawBlackjack({ hand, balance }, animate = true) {
  if (state.page !== "blackjack") return;
  setBalance(balance);
  const playing = hand?.status === "playing";
  $("#bj-bet-zone").classList.toggle("hidden", playing);
  $("#bj-play-zone").classList.toggle("hidden", !playing);
  if (!hand) return;
  let order = 0;
  const paint = (el, cards, prev) => {
    el.innerHTML = cards
      .map((c, i) => {
        const fresh = animate && (i >= prev.length || (prev[i] === "??" && c !== "??"));
        return cardHtml(c, fresh ? order++ * 170 : 0, fresh);
      })
      .join("");
  };
  paint($("#bj-player"), hand.player, bj.prev.player);
  paint($("#bj-dealer"), hand.dealer, bj.prev.dealer);
  bj.prev = { player: hand.player, dealer: hand.dealer };

  const pv = $("#bj-pv");
  pv.textContent = hand.playerValue;
  pv.className = `hand-value ${hand.playerValue > 21 ? "bust" : hand.status === "blackjack" ? "bj" : ""}`;
  const dv = $("#bj-dv");
  dv.textContent = hand.dealerValue;
  dv.className = `hand-value ${hand.dealerValue > 21 ? "bust" : ""}`;
  $("[data-bj=double]").disabled = !hand.canDouble;
  $("#bj-cur-bet").textContent = `Mise ${fmt(hand.bet)} 🪙`;

  const banner = $("#bj-banner");
  const messages = {
    playing: ["", ""],
    blackjack: [`Blackjack ! +${fmt(hand.payout)} 🪙`, "gold"],
    won: [`Gagné ! +${fmt(hand.payout)} 🪙`, "win"],
    push: ["Égalité · mise rendue", ""],
    lost: [hand.playerValue > 21 ? "Tu dépasses 21…" : "Le croupier gagne", "lose"],
  };
  const [text, cls] = messages[hand.status];
  banner.textContent = "";
  banner.className = "bj-banner";
  const show = () => {
    if (state.page !== "blackjack") return;
    banner.textContent = text;
    banner.className = `bj-banner ${cls}`;
    if (hand.status === "blackjack" && animate) celebrate();
  };
  if (animate && text) setTimeout(show, order * 170 + 380);
  else show();
}

async function dealBlackjack() {
  if (bj.busy) return;
  const bet = readAmount("bj-bet");
  if (!bet) return;
  bj.busy = true;
  try {
    bj.prev = { player: [], dealer: [] };
    drawBlackjack(await api("blackjack/start", { bet }));
  } catch (err) {
    toast(err.message, "error");
  } finally {
    bj.busy = false;
  }
}

async function blackjackAction(action) {
  if (bj.busy) return;
  bj.busy = true;
  try {
    drawBlackjack(await api(`blackjack/${action}`, {}));
  } catch (err) {
    toast(err.message, "error");
  } finally {
    bj.busy = false;
  }
}

/* =========================================================
   Compte
   ========================================================= */
const KIND = {
  welcome_bonus: ["🎉", "Bonus de bienvenue"],
  daily_bonus: ["🎁", "Bonus quotidien"],
  roulette_bet: ["🎡", "Roulette · mise"],
  roulette_win: ["🎡", "Roulette · gain"],
  slots_bet: ["🍒", "Machine à sous · mise"],
  slots_win: ["🍒", "Machine à sous · gain"],
  blackjack_bet: ["🃏", "Blackjack · mise"],
  blackjack_win: ["🃏", "Blackjack · gain"],
  crash_bet: ["🚀", "Crash · mise"],
  crash_win: ["🚀", "Crash · gain"],
  sport_bet: ["⚽", "Pari sportif"],
  sport_win: ["⚽", "Pari sportif · gain"],
  sport_refund: ["⚽", "Pari sportif · remboursement"],
};
let accTab = "bets";

async function renderAccount() {
  const me = state.me;
  view.innerHTML = `
    <div class="profile">
      <span class="avatar" style="--h:${hue(me.username)}">${esc(initials(me.username))}</span>
      <div><h1>${esc(me.username)}</h1><p>Membre PilotCasino · solde de <b>${fmt(state.balance)} 🪙</b></p></div>
      <button class="btn btn-ghost" data-action="logout">Se déconnecter</button>
    </div>
    <div class="kpis" id="kpis">${'<div class="kpi skeleton" style="height:84px;margin:0"></div>'.repeat(4)}</div>
    <div class="tabs" id="acc-tabs">
      <button data-acc="bets">Mes paris</button><button data-acc="history">Historique</button><button data-acc="ranking">Classement</button>
    </div>
    <div id="acc-body">${'<div class="skeleton"></div>'.repeat(4)}</div>`;
  $("#acc-tabs").addEventListener("click", (e) => {
    const tab = e.target.closest("[data-acc]")?.dataset.acc;
    if (!tab) return;
    accTab = tab;
    paintAccount();
  });
  try {
    const [txs, board] = await Promise.all([api("transactions"), api("leaderboard"), loadBets()]);
    if (state.page !== "compte") return;
    account.txs = txs;
    account.board = board;
    const rank = board.findIndex((u) => u.username === me.username);
    const bestWin = Math.max(0, ...txs.filter((t) => t.kind.endsWith("_win")).map((t) => t.amount));
    const open = state.bets.filter((b) => b.status === "open");
    $("#kpis").innerHTML = `
      <div class="kpi"><small>Solde</small><b>${fmt(state.balance)} 🪙</b></div>
      <div class="kpi"><small>Paris en cours</small><b>${open.length}</b></div>
      <div class="kpi"><small>Meilleur gain récent</small><b class="pos">${bestWin ? `+${fmt(bestWin)}` : "–"}</b></div>
      <div class="kpi"><small>Classement</small><b>${rank >= 0 ? `#${rank + 1}` : "–"}</b></div>`;
    paintAccount();
  } catch (err) {
    toast(err.message, "error");
  }
}
const account = { txs: [], board: [] };

function paintAccount() {
  $$("#acc-tabs [data-acc]").forEach((b) => b.classList.toggle("active", b.dataset.acc === accTab));
  const body = $("#acc-body");
  if (accTab === "bets") {
    body.innerHTML = state.bets.length
      ? `<div class="bets-grid">${state.bets.map(betCard).join("")}</div>`
      : `<div class="empty"><div class="big">🎫</div><b>Aucun pari</b><a class="btn btn-primary btn-sm" href="#/sports">Voir les matchs</a></div>`;
  } else if (accTab === "history") {
    body.innerHTML = `<div class="tx-list">${
      account.txs
        .map((t) => {
          const [ico, label] = KIND[t.kind] ?? ["•", t.kind];
          return `<div class="tx"><span class="tx-ico">${ico}</span><div><b>${label}</b><small>${shortDay(t.created_at)} · ${hhmm(t.created_at)}</small></div>
            <div class="amt ${t.amount > 0 ? "pos" : ""}">${t.amount > 0 ? "+" : ""}${fmt(t.amount)}<small class="muted" style="display:block">solde ${fmt(t.balance_after)}</small></div></div>`;
        })
        .join("") || `<div class="empty">Aucune opération</div>`
    }</div>`;
  } else {
    const b = account.board;
    const pod = (u, place) =>
      u
        ? `<div class="pod p${place}"><span class="medal">${["🥇", "🥈", "🥉"][place - 1]}</span><span class="avatar" style="--h:${hue(u.username)}">${esc(initials(u.username))}</span><strong>${esc(u.username)}</strong><b>${fmt(u.balance)} 🪙</b></div>`
        : `<div></div>`;
    body.innerHTML = `
      <div class="podium">${pod(b[1], 2)}${pod(b[0], 1)}${pod(b[2], 3)}</div>
      <div class="tx-list">${b
        .slice(3)
        .map(
          (u, i) => `<div class="tx ${u.username === state.me.username ? "me" : ""}"><span class="tx-ico rank">#${i + 4}</span><div><b>${esc(u.username)}</b></div><div class="amt">${fmt(u.balance)} 🪙</div></div>`,
        )
        .join("")}</div>`;
  }
}

/* =========================================================
   Bonus, connexion, démarrage
   ========================================================= */
function renderBonus() {
  if (!state.me) return;
  const wait = (state.me.nextBonusAt ?? 0) - Date.now();
  $("#bonus-btn").classList.toggle("ready", wait <= 0);
  const h = Math.floor(wait / 3_600_000);
  const m = Math.floor((wait % 3_600_000) / 60_000);
  $("#bonus-label").textContent = wait <= 0 ? "Bonus dispo" : `${h} h ${String(m).padStart(2, "0")}`;
}

async function claimBonus() {
  try {
    const { balance } = await api("bonus", {});
    setBalance(balance);
    state.me.nextBonusAt = Date.now() + DAY;
    renderBonus();
    toast(`+${state.me.dailyBonus ?? 500} jetons ! Prochain bonus dans 24 h.`, "win");
    celebrate();
  } catch (err) {
    toast(err.message, "error");
  }
}

let authMode = "login";
function setAuthMode(mode) {
  authMode = mode;
  $$(".seg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("#auth-title").textContent = mode === "login" ? "Bon retour 👋" : "Crée ton compte 🎉";
  $("#auth-submit").textContent = mode === "login" ? "Se connecter" : "Créer mon compte · 1 000 🪙 offerts";
  $("#auth-form [name=password]").autocomplete = mode === "login" ? "current-password" : "new-password";
  $("#auth-error").textContent = "";
}
$$(".seg button").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.mode)));

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const btn = $("#auth-submit");
  btn.disabled = true;
  try {
    await api(authMode, { username: form.get("username"), password: form.get("password") });
    $("#auth-error").textContent = "";
    await boot();
    if (authMode === "register") {
      toast("Bienvenue sur PilotCasino ! 1 000 jetons offerts", "win");
      celebrate();
    }
  } catch (err) {
    $("#auth-error").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

function showAuth() {
  cleanups.splice(0).forEach((fn) => fn());
  state.me = null;
  $("#app").classList.add("hidden");
  $("#auth").classList.remove("hidden");
}

async function logout() {
  await api("logout", {}).catch(() => {});
  state.bets = [];
  showAuth();
}

async function boot() {
  try {
    state.me = await api("me");
  } catch {
    showAuth();
    return;
  }
  $("#auth").classList.add("hidden");
  $("#app").classList.remove("hidden");
  setBalance(state.me.balance);
  const avatar = $("#avatar");
  avatar.textContent = initials(state.me.username);
  avatar.style.setProperty("--h", hue(state.me.username));
  renderBonus();
  loadSlip();
  route();
  if (state.page !== "sports") loadEvents();
  loadBets();
}

/* ---------- Événements globaux (délégation) ---------- */
document.addEventListener("click", (e) => {
  const t = e.target;
  const odd = t.closest(".odd[data-ev]");
  if (odd) return toggleSelection(odd.dataset.ev, odd.dataset.o);

  const remove = t.closest("[data-remove]");
  if (remove) {
    const id = remove.dataset.remove;
    state.slip.delete(id);
    saveSlip();
    refreshOddButtons(id);
    return renderSlip();
  }

  const sport = t.closest("[data-filter-sport]");
  if (sport) {
    state.filter.sport = sport.dataset.filterSport;
    state.filter.league = null;
    return renderSportsData();
  }
  const league = t.closest("[data-filter-league]");
  if (league) {
    const l = league.dataset.filterLeague;
    state.filter.league = !l || state.filter.league === l ? null : l;
    return renderSportsData();
  }
  const day = t.closest("[data-filter-day]");
  if (day) {
    state.filter.day = day.dataset.filterDay;
    return renderSportsData();
  }

  const tab = t.closest("[data-slip-tab]");
  if (tab) {
    state.slipTab = tab.dataset.slipTab;
    return renderSlip();
  }
  const stake = t.closest("[data-stake]");
  if (stake) {
    const v = stake.dataset.stake;
    state.stake = v === "max" ? Math.max(1, Math.min(state.balance, 100_000)) : state.stake + Number(v);
    return renderSlip();
  }
  const amount = t.closest("[data-amt]");
  if (amount) return adjustAmount(amount.dataset.amt, amount.dataset.op);

  const action = t.closest("[data-action]")?.dataset.action;
  if (action === "bonus") return claimBonus();
  if (action === "logout") return logout();
  if (action === "scroll-matches") return $("#all-matches")?.scrollIntoView({ behavior: "smooth" });
  if (action === "reset-filters") {
    state.filter = { sport: "all", league: null, day: "all" };
    return renderSportsData();
  }
  if (action === "clear-slip") {
    const ids = [...state.slip.keys()];
    state.slip.clear();
    saveSlip();
    ids.forEach(refreshOddButtons);
    return renderSlip();
  }

  const place = t.closest("#place-bet");
  if (place) return placeBet(place);
  if (t.closest("#bonus-btn")) return claimBonus();
  if (t.closest("#bb-slip") || t.closest("#slip-fab")) return openSheet();
  if (t.closest("#scrim") || t.closest("#sheet-close")) return closeSheet();
});

document.addEventListener("input", (e) => {
  if (e.target.id !== "stake") return;
  state.stake = Math.max(0, Math.floor(Number(e.target.value) || 0));
  updateSlipTotals();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeSheet();
});

setInterval(() => state.me && !document.hidden && loadEvents(), 30_000);
setInterval(() => state.me && !document.hidden && loadBets(), 45_000);
setInterval(renderBonus, 30_000);

boot();
