/* =========================================================
   Paris sportifs : accueil, direct, fiche match, ticket, mes paris
   ========================================================= */
import {
  $,
  $$,
  api,
  countBy,
  crest,
  dayDiff,
  esc,
  flare,
  fmt,
  groupBy,
  hhmm,
  onLeave,
  page,
  setBalance,
  shortDay,
  sportName,
  startsIn,
  state,
  toast,
  tok,
  view,
} from "./core.js";
import { chip, icon, sportIcon } from "./icons.js";
import { CATEGORIES, describe, GROUP_ORDER } from "./markets.js";

export const sp = {
  events: [],
  live: [],
  results: [],
  loadedAt: 0,
  bets: [],
  slip: new Map(), // eventId -> sélection
  stake: 10,
  slipTab: "slip",
  acceptChanges: true,
  filter: { sport: "all", league: null, day: "all" },
  match: null,
  matchCat: "main",
  lastPrices: new Map(),
};
const MAIN = ["home", "draw", "away"];
const allEvents = () => [...sp.live, ...sp.events];
const findEvent = (id) => allEvents().find((e) => e.id === id) ?? (sp.match?.id === id ? sp.match : null);

/* ---------- Chargement ---------- */
export async function loadEvents() {
  try {
    const d = await api("sports/events");
    sp.events = d.events;
    sp.live = d.live;
    sp.results = d.results;
    sp.loadedAt = Date.now();
    paintLiveCount();
    syncSlip();
    if (state.page === "sports") paintSports();
    if (state.page === "live") paintLive();
    if (["sports", "live", "match"].includes(state.page)) sportsSidebar();
  } catch {
    /* nouvel essai au prochain rafraîchissement */
  }
}

function paintLiveCount() {
  const n = sp.live.filter((e) => e.open).length;
  const el = $("#nav-live-count");
  el.textContent = n;
  el.classList.toggle("hidden", !n);
}

/* ---------- Boutons de cote ---------- */
function flashClass(evId, key, price) {
  const id = `${evId}:${key}`;
  const prev = sp.lastPrices.get(id);
  sp.lastPrices.set(id, price);
  if (!prev || !price || prev === price) return "";
  return price > prev ? " up" : " down";
}

function oddBtn(ev, key, price, label) {
  if (price === null || price === undefined || !ev.open)
    return `<button class="odd locked" disabled aria-label="Cote fermée">${label ? `<span class="odd-label">${esc(label)}</span>` : ""}${icon("lock", { size: 14 })}</button>`;
  const picked = sp.slip.get(ev.id)?.key === key;
  const susp = ev.suspended ? " susp" : "";
  return `<button class="odd${picked ? " picked" : ""}${susp}${flashClass(ev.id, key, price)}" data-ev="${esc(ev.id)}" data-key="${esc(key)}" data-price="${price}">
    ${label ? `<span class="odd-label">${esc(label)}</span>` : ""}<span class="odd-price">${price.toFixed(2)}</span></button>`;
}

const mainKeys = (ev) => (ev.odds?.draw !== undefined || ["football", "hockey", "rugby"].includes(ev.sport) ? MAIN : ["home", "away"]);
const mainOdds = (ev, labels = true) =>
  `<div class="odds-row" style="--cols:${mainKeys(ev).length}">${mainKeys(ev)
    .map((k) => oddBtn(ev, k, ev.odds?.[k], labels ? (k === "draw" ? "N" : k === "home" ? "1" : "2") : ""))
    .join("")}</div>`;

/* ---------- Horloge et score ---------- */
function clockHtml(ev) {
  if (ev.status === "finished") return `<span class="clock done">Terminé</span>`;
  if (ev.live)
    return ev.virtual || ev.clock
      ? `<span class="clock live"><span class="live-dot"></span>${esc(ev.clock ?? "En cours")}</span>`
      : `<span class="clock live"><span class="live-dot"></span>En cours</span>`;
  return `<span class="clock">${dayDiff(ev.starts_at) === 0 ? hhmm(ev.starts_at) : `${esc(shortDay(ev.starts_at))}<br>${hhmm(ev.starts_at)}`}</span>`;
}

/** Détail court du score (sets au tennis, quart-temps au basket). */
function scoreNote(ev) {
  const d = ev.detail;
  if (!d) return "";
  if (ev.sport === "tennis" && (d.sets?.length || d.cur))
    return [...(d.sets ?? []).map(([a, b]) => `${a}-${b}`), d.cur ? `<b>${d.cur[0]}-${d.cur[1]}</b>` : ""].filter(Boolean).join(" ");
  return "";
}


/* =========================================================
   Accueil des paris sportifs
   ========================================================= */
function renderSports() {
  view().innerHTML = `
    <section class="feature" id="feature"></section>
    <div class="sport-tabs chips" id="sport-tabs"></div>
    <section class="section" id="live-section"></section>
    <section class="section" id="upcoming">
      <div class="section-head"><h2>Prochains matchs</h2><span class="note" id="match-count"></span></div>
      <div class="chips day-chips" id="day-chips"></div>
      <div id="match-list">${'<div class="skeleton"></div>'.repeat(6)}</div>
    </section>
    <section class="section" id="results-section"></section>`;
  if (sp.loadedAt) paintSports();
  if (Date.now() - sp.loadedAt > 4000) loadEvents();
  const timer = setInterval(() => !document.hidden && loadEvents(), 5000);
  onLeave(() => clearInterval(timer));
}

function paintSports() {
  paintFeature();
  paintSportTabs();
  paintLiveSection();
  paintDayChips();
  paintMatchList();
  paintResults();
}

function featured() {
  const live = sp.live.filter((e) => e.open && e.markets > 4);
  const pick = (list) =>
    list.find((e) => e.sport === "football") ?? list.find((e) => e.sport === "basketball") ?? list[0];
  return pick(live) ?? pick(sp.events.filter((e) => e.markets > 4)) ?? null;
}

function paintFeature() {
  const el = $("#feature");
  if (!el) return;
  const ev = featured();
  if (!ev) {
    el.innerHTML = "";
    return;
  }
  const timeline = (ev.detail?.timeline ?? []).slice(-3).reverse();
  el.innerHTML = `
    <div class="feature-card">
      <div class="feature-top">
        <span class="feature-league">${sportIcon(ev.sport, { size: 16 })}${esc(ev.league)}</span>
        ${ev.live ? clockHtml(ev) : `<span class="clock">${esc(startsIn(ev.starts_at))}</span>`}
      </div>
      <a class="feature-board" href="#/match/${encodeURIComponent(ev.id)}">
        <div class="ft-team">${crest(ev.home, "crest-xl")}<span>${esc(ev.home)}</span></div>
        <div class="ft-score display">${ev.score ? `<span>${ev.score[0]}</span><i></i><span>${ev.score[1]}</span>` : `<small>${hhmm(ev.starts_at)}</small>`}</div>
        <div class="ft-team">${crest(ev.away, "crest-xl")}<span>${esc(ev.away)}</span></div>
      </a>
      ${scoreNote(ev) ? `<div class="ft-note">${scoreNote(ev)}</div>` : ""}
      ${
        timeline.length
          ? `<ul class="ft-timeline">${timeline.map((t) => `<li><b>${esc(t.t)}</b><span>${esc(eventLabel(ev, t))}</span></li>`).join("")}</ul>`
          : ""
      }
      <div class="feature-odds">${mainOdds(ev)}</div>
      <a class="feature-more" href="#/match/${encodeURIComponent(ev.id)}">Voir les ${ev.markets} paris de ce match ${icon("next", { size: 16 })}</a>
    </div>`;
}

function eventLabel(ev, t) {
  const team = t.side === "home" ? ev.home : ev.away;
  const kinds = { goal: "But", try: "Essai", pen: "Pénalité", set: "Set gagné" };
  const k = kinds[t.kind] ?? t.kind;
  return `${k}${t.pts && t.kind !== "set" ? ` (${t.pts} pts)` : ""}, ${team}`;
}

function paintSportTabs() {
  const el = $("#sport-tabs");
  if (!el) return;
  const counts = countBy(allEvents().filter((e) => e.open), (e) => e.sport);
  const s = sp.filter.sport;
  el.innerHTML =
    `<button class="chip ${s === "all" ? "active" : ""}" data-filter-sport="all">Tous les sports <span class="n">${[...counts.values()].reduce((a, b) => a + b, 0)}</span></button>` +
    [...counts]
      .map(([k, n]) => `<button class="chip ${s === k ? "active" : ""}" data-filter-sport="${esc(k)}">${sportIcon(k, { size: 16 })}${esc(sportName(k))} <span class="n">${n}</span></button>`)
      .join("");
}

const bySport = (list) => list.filter((e) => sp.filter.sport === "all" || e.sport === sp.filter.sport);

function liveRow(ev) {
  return `<div class="match live-row">
    <a class="match-time" href="#/match/${encodeURIComponent(ev.id)}">${clockHtml(ev)}</a>
    <a class="match-teams" href="#/match/${encodeURIComponent(ev.id)}">
      <div class="team">${crest(ev.home)}<span>${esc(ev.home)}</span><b class="sc">${ev.score?.[0] ?? ""}</b></div>
      <div class="team">${crest(ev.away)}<span>${esc(ev.away)}</span><b class="sc">${ev.score?.[1] ?? ""}</b></div>
      ${scoreNote(ev) ? `<div class="match-note">${scoreNote(ev)}</div>` : ""}
    </a>
    ${ev.open ? mainOdds(ev, false) : `<div class="odds-closed">Paris fermés pendant le match</div>`}
    <a class="more" href="#/match/${encodeURIComponent(ev.id)}" aria-label="Tous les paris">${ev.open && ev.markets ? `+${ev.markets}` : icon("next", { size: 16 })}</a>
  </div>`;
}

function paintLiveSection() {
  const el = $("#live-section");
  if (!el) return;
  const live = bySport(sp.live).slice(0, 6);
  el.innerHTML = live.length
    ? `<div class="section-head"><h2><span class="live-dot"></span>En direct</h2><a class="note" href="#/live">Tout le direct (${bySport(sp.live).length})</a></div>
       <div class="match-block">${live.map(liveRow).join("")}</div>`
    : "";
}

const DAYS = [
  ["all", "Tous"],
  ["soon", "Moins de 3 h"],
  ["today", "Aujourd'hui"],
  ["tomorrow", "Demain"],
];
function paintDayChips() {
  const el = $("#day-chips");
  if (el)
    el.innerHTML = DAYS.map(([k, l]) => `<button class="chip ${sp.filter.day === k ? "active" : ""}" data-filter-day="${k}">${l}</button>`).join("");
}

function filteredEvents() {
  const { league, day } = sp.filter;
  const now = Date.now();
  return bySport(sp.events).filter((e) => {
    if (league && e.league !== league) return false;
    if (day === "soon") return e.starts_at - now < 3 * 3_600_000;
    if (day === "today") return dayDiff(e.starts_at) === 0;
    if (day === "tomorrow") return dayDiff(e.starts_at) === 1;
    return true;
  });
}

function upcomingRow(ev) {
  return `<div class="match">
    <a class="match-time" href="#/match/${encodeURIComponent(ev.id)}">${clockHtml(ev)}</a>
    <a class="match-teams" href="#/match/${encodeURIComponent(ev.id)}">
      <div class="team">${crest(ev.home)}<span>${esc(ev.home)}</span></div>
      <div class="team">${crest(ev.away)}<span>${esc(ev.away)}</span></div>
    </a>
    ${mainOdds(ev, false)}
    <a class="more" href="#/match/${encodeURIComponent(ev.id)}" aria-label="Tous les paris">+${ev.markets}</a>
  </div>`;
}

function leagueHead(league, items) {
  const keys = mainKeys(items[0]);
  return `<div class="league-head">
    <div class="league-name">${sportIcon(items[0].sport, { size: 16 })}<span>${esc(league)}</span></div>
    <div class="odds-labels" style="--cols:${keys.length}">${keys.map((k) => `<span>${k === "draw" ? "N" : k === "home" ? "1" : "2"}</span>`).join("")}</div>
    <span class="more-head"></span>
  </div>`;
}

function paintMatchList() {
  const list = $("#match-list");
  if (!list) return;
  const events = filteredEvents();
  $("#match-count").textContent = events.length ? `${events.length} matchs` : "";
  if (!events.length) {
    list.innerHTML = `<div class="empty">${icon("clock")}<b>Aucun match pour ces filtres</b><span>Les matchs virtuels sont programmés en continu : élargis ta sélection.</span><button class="btn btn-sm" data-action="reset-filters">Afficher tous les matchs</button></div>`;
    return;
  }
  list.innerHTML = [...groupBy(events, (e) => e.league)]
    .map(([league, items]) => `<div class="match-block">${leagueHead(league, items)}${items.map(upcomingRow).join("")}</div>`)
    .join("");
}

function paintResults() {
  const el = $("#results-section");
  if (!el) return;
  const results = bySport(sp.results).slice(0, 8);
  el.innerHTML = results.length
    ? `<div class="section-head"><h2>Derniers résultats</h2></div>
       <div class="results">${results.map(resultCard).join("")}</div>`
    : "";
}

function resultCard(r) {
  if (r.status === "cancelled")
    return `<div class="result"><div class="result-league">${sportIcon(r.sport, { size: 14 })}${esc(r.league)}</div><div class="result-teams">${esc(r.home)} – ${esc(r.away)}</div><div class="result-void">Annulé, paris remboursés</div></div>`;
  const [h, a] = r.score ?? [0, 0];
  return `<a class="result" href="#/match/${encodeURIComponent(r.id)}">
    <div class="result-league">${sportIcon(r.sport, { size: 14 })}${esc(r.league)}</div>
    <div class="result-row ${a > h ? "lose" : ""}"><span class="team">${crest(r.home)}<span>${esc(r.home)}</span></span><b>${h}</b></div>
    <div class="result-row ${h > a ? "lose" : ""}"><span class="team">${crest(r.away)}<span>${esc(r.away)}</span></span><b>${a}</b></div>
  </a>`;
}

/* ---------- Barre latérale des sports ---------- */
export function sportsSidebar() {
  const el = $("#sidebar");
  if (!el) return;
  const open = allEvents().filter((e) => e.open);
  const counts = countBy(open, (e) => e.sport);
  const leagues = countBy(
    open.filter((e) => sp.filter.sport === "all" || e.sport === sp.filter.sport),
    (e) => e.league,
  );
  const liveN = sp.live.filter((e) => e.open).length;
  const link = (attr, value, ico, label, n, active) =>
    `<button class="side-link ${active ? "active" : ""}" ${attr}="${esc(value)}">${ico}<span class="lbl">${esc(label)}</span><span class="n">${n}</span></button>`;
  el.innerHTML = `
    <div class="side-group">
      <a class="side-link ${state.page === "live" ? "active" : ""}" href="#/live"><span class="live-dot"></span><span class="lbl">En direct</span><span class="n">${liveN}</span></a>
    </div>
    <div class="side-group"><h4>Sports</h4>
      ${link("data-filter-sport", "all", icon("star", { size: 18 }), "Tous les sports", open.length, sp.filter.sport === "all" && !sp.filter.league && state.page === "sports")}
      ${[...counts].map(([s, n]) => link("data-filter-sport", s, sportIcon(s, { size: 18 }), sportName(s), n, sp.filter.sport === s && !sp.filter.league && state.page === "sports")).join("")}
    </div>
    <div class="side-group"><h4>Compétitions</h4>
      ${[...leagues].map(([l, n]) => link("data-filter-league", l, `<span class="side-dot"></span>`, l, n, sp.filter.league === l)).join("")}
    </div>
    <div class="side-note"><b>Bonus quotidien</b>${fmt(state.me?.dailyBonus ?? 500)} jetons offerts toutes les 24 h.<button class="btn btn-line btn-sm btn-block" data-action="bonus">Récupérer mon bonus</button></div>`;
}

/* =========================================================
   Page « En direct »
   ========================================================= */
function renderLive() {
  view().innerHTML = `
    <div class="page-head"><div><h1>En direct</h1><p>Les cotes bougent avec le score. Les marchés se suspendent quelques secondes après chaque but ou essai.</p></div></div>
    <div class="sport-tabs chips" id="live-tabs"></div>
    <div id="live-list" class="section">${'<div class="skeleton"></div>'.repeat(5)}</div>`;
  if (sp.loadedAt) paintLive();
  if (Date.now() - sp.loadedAt > 10_000) loadEvents();
  const refresh = async () => {
    if (document.hidden) return;
    try {
      const d = await api("sports/live");
      sp.live = d.live;
      paintLiveCount();
      syncSlip();
      paintLive();
      sportsSidebar();
    } catch {
      /* nouvel essai */
    }
  };
  refresh();
  const timer = setInterval(refresh, 3000);
  onLeave(() => clearInterval(timer));
}

function paintLive() {
  const list = $("#live-list");
  if (!list) return;
  const counts = countBy(sp.live, (e) => e.sport);
  $("#live-tabs").innerHTML =
    `<button class="chip ${sp.filter.sport === "all" ? "active" : ""}" data-filter-sport="all">Tous <span class="n">${sp.live.length}</span></button>` +
    [...counts]
      .map(([k, n]) => `<button class="chip ${sp.filter.sport === k ? "active" : ""}" data-filter-sport="${esc(k)}">${sportIcon(k, { size: 16 })}${esc(sportName(k))} <span class="n">${n}</span></button>`)
      .join("");
  const live = bySport(sp.live);
  if (!live.length) {
    list.innerHTML = `<div class="empty">${icon("live")}<b>Aucun match en cours dans ce sport</b><span>Le prochain coup d'envoi est dans quelques minutes.</span><a class="btn btn-sm" href="#/sports">Voir les prochains matchs</a></div>`;
    return;
  }
  list.innerHTML = [...groupBy(live, (e) => e.league)]
    .map(([league, items]) => `<div class="match-block">${leagueHead(league, items)}${items.map(liveRow).join("")}</div>`)
    .join("");
}

/* =========================================================
   Fiche match : tous les marchés
   ========================================================= */
function renderMatch(id) {
  sp.match = null;
  sp.matchCat = "main";
  view().innerHTML = `<div class="match-page"><a class="back-link" href="javascript:history.back()">${icon("back", { size: 18 })}Retour</a><div id="match-board"><div class="skeleton" style="height:200px"></div></div><div id="match-markets"></div></div>`;
  const load = async () => {
    try {
      const ev = await api(`sports/event/${encodeURIComponent(id)}`);
      if (state.page !== "match") return;
      sp.match = ev;
      syncSlip();
      paintMatch();
      return ev;
    } catch (err) {
      if (err.status === 404)
        $("#match-board").innerHTML = `<div class="empty">${icon("close")}<b>Ce match n'existe plus</b><a class="btn btn-sm" href="#/sports">Retour aux paris sportifs</a></div>`;
    }
  };
  let timer = 0;
  const loop = async () => {
    const ev = await load();
    if (state.page !== "match") return;
    timer = setTimeout(loop, ev?.live ? 3000 : 15000);
  };
  loop();
  onLeave(() => clearTimeout(timer));
}

function paintMatch() {
  const ev = sp.match;
  const board = $("#match-board");
  if (!ev || !board) return;
  const tl = [...(ev.detail?.timeline ?? [])].reverse();
  board.innerHTML = `
    <div class="board">
      <div class="board-top"><span class="feature-league">${sportIcon(ev.sport, { size: 16 })}${esc(ev.league)}</span>${
        ev.live || ev.status === "finished" ? clockHtml(ev) : `<span class="clock">${esc(shortDay(ev.starts_at))}, ${hhmm(ev.starts_at)}</span>`
      }</div>
      <div class="board-main">
        <div class="ft-team">${crest(ev.home, "crest-xl")}<span>${esc(ev.home)}</span></div>
        <div class="ft-score display">${ev.score ? `<span>${ev.score[0]}</span><i></i><span>${ev.score[1]}</span>` : `<small>${hhmm(ev.starts_at)}</small>`}</div>
        <div class="ft-team">${crest(ev.away, "crest-xl")}<span>${esc(ev.away)}</span></div>
      </div>
      ${scoreNote(ev) ? `<div class="ft-note">${scoreNote(ev)}</div>` : ""}
      ${ev.suspended ? `<div class="susp-banner">${icon("lock", { size: 15 })}Marchés suspendus quelques secondes</div>` : ""}
      ${tl.length ? `<ul class="ft-timeline full">${tl.map((t) => `<li><b>${esc(t.t)}</b><span>${esc(eventLabel(ev, t))}</span></li>`).join("")}</ul>` : ""}
    </div>`;

  const el = $("#match-markets");
  if (ev.status === "finished" || ev.status === "cancelled") {
    el.innerHTML = `<div class="empty">${icon("check")}<b>${ev.status === "finished" ? "Match terminé" : "Match annulé"}</b><span>Les paris sur ce match sont réglés automatiquement.</span></div>`;
    return;
  }
  if (!ev.open) {
    el.innerHTML = `<div class="empty">${icon("lock")}<b>Paris fermés pendant ce match</b><span>Les cotes de ce flux ne sont pas mises à jour en direct.</span></div>`;
    return;
  }
  // Regroupe les pronostics par marché.
  const groups = new Map();
  for (const [key, price] of Object.entries(ev.selections)) {
    const d = describe(key, ev);
    const g = groups.get(d.group) ?? groups.set(d.group, { market: d.market, items: [] }).get(d.group);
    g.items.push({ key, price, ...d });
  }
  for (const [name, g] of groups) if (g.items.every((i) => i.price === null)) groups.delete(name);
  const cats = CATEGORIES.filter(([, , gs]) => gs.some((g) => groups.has(g)));
  if (!cats.some(([c]) => c === sp.matchCat)) sp.matchCat = cats[0]?.[0] ?? "main";
  const cat = cats.find(([c]) => c === sp.matchCat);
  const shown = GROUP_ORDER.filter((g) => groups.has(g) && cat?.[2].includes(g));
  el.innerHTML = `
    <div class="tabs market-tabs">${cats.map(([c, label]) => `<button data-mcat="${c}" class="${c === sp.matchCat ? "active" : ""}">${label}</button>`).join("")}</div>
    ${shown.map((g) => marketGroup(ev, g, groups.get(g))).join("") || `<div class="empty">${icon("lock")}<b>Aucun pari ouvert dans cette catégorie</b></div>`}`;
}

function marketGroup(ev, g, { market, items: all }) {
  let items = all;
  const byKey = (k) => items.find((i) => i.key === k);
  const cell = (i, label = i?.short) => (i ? oddBtn(ev, i.key, i.price, label) : `<span></span>`);
  let body = "";
  const lined = (pairs) =>
    pairs
      .map(([lineLabel, a, b]) => `<div class="mk-line"><span class="mk-l">${esc(lineLabel)}</span>${cell(a)}${cell(b)}</div>`)
      .join("");
  if (["ou", "th", "ta", "games"].includes(g)) {
    const lines = [...new Set(items.map((i) => i.key.split(":")[1]))].sort((a, b) => a - b);
    body = `<div class="mk-lines">${lined(lines.map((L) => [items.find((i) => i.key.split(":")[1] === L).line, byKey(`${g}:${L}:over`), byKey(`${g}:${L}:under`)]))}</div>`;
  } else if (g === "ah") {
    const lines = [...new Set(items.map((i) => i.key.split(":")[1]))].sort((a, b) => a - b);
    body = `<div class="mk-grid" style="--cols:2">${lines
      .map((L) => cell(byKey(`ah:${L}:home`), byKey(`ah:${L}:home`)?.pick) + cell(byKey(`ah:${L}:away`), byKey(`ah:${L}:away`)?.pick))
      .join("")}</div>`;
  } else if (g === "mg") {
    const home = items.filter((i) => i.side === "h");
    const away = items.filter((i) => i.side === "a");
    const draw = byKey("mg:d");
    body = `<div class="mk-cols"><div><div class="mk-sub">${esc(ev.home)}</div>${home.map((i) => cell(i)).join("")}</div>
      <div><div class="mk-sub">${esc(ev.away)}</div>${away.map((i) => cell(i)).join("")}</div></div>${draw ? `<div class="mk-grid" style="--cols:1">${cell(draw, "Match nul")}</div>` : ""}`;
  } else if (g === "cs") {
    items = items.filter((i) => i.price !== null);
    const parse = (i) => (i.key === "cs:other:4" || i.key.startsWith("cs:other") ? [99, 99] : i.key.slice(3).split("-").map(Number));
    const homeW = items.filter((i) => !i.key.startsWith("cs:other") && parse(i)[0] > parse(i)[1]);
    const draws = items.filter((i) => !i.key.startsWith("cs:other") && parse(i)[0] === parse(i)[1]);
    const awayW = items.filter((i) => !i.key.startsWith("cs:other") && parse(i)[0] < parse(i)[1]);
    const other = items.find((i) => i.key.startsWith("cs:other"));
    const col = (title, list) => `<div><div class="mk-sub">${esc(title)}</div>${list.map((i) => cell(i)).join("")}</div>`;
    body = `<div class="mk-cols three">${col(ev.home, homeW)}${draws.length ? col("Nul", draws) : ""}${col(ev.away, awayW)}</div>${other ? `<div class="mk-grid" style="--cols:1">${cell(other)}</div>` : ""}`;
  } else if (g === "mt") {
    body = `<div class="mk-grid" style="--cols:2">${["mt:home:fin", "mt:away:fin", "mt:home:dec", "mt:away:dec"].map((k) => cell(byKey(k), byKey(k)?.pick)).join("")}</div>`;
  } else {
    const order = ["home", "draw", "away", "dc:1X", "dc:12", "dc:X2", "dnb:home", "dnb:away", "btts:yes", "btts:no", "oe:odd", "oe:even", "fin:yes", "fin:no"];
    const sorted = [...items].sort((a, b) => {
      const ka = a.key.split(":").slice(-1)[0];
      const kb = b.key.split(":").slice(-1)[0];
      const ia = order.indexOf(a.key) >= 0 ? order.indexOf(a.key) : ["home", "draw", "away"].indexOf(ka) + 100;
      const ib = order.indexOf(b.key) >= 0 ? order.indexOf(b.key) : ["home", "draw", "away"].indexOf(kb) + 100;
      return ia - ib || a.key.localeCompare(b.key);
    });
    body = `<div class="mk-grid" style="--cols:${Math.min(3, sorted.length)}">${sorted.map((i) => cell(i, i.pick)).join("")}</div>`;
  }
  return `<section class="market"><h3>${esc(market)}</h3>${body}</section>`;
}

/* =========================================================
   Ticket
   ========================================================= */
function saveSlip() {
  try {
    localStorage.setItem("pilotcasino-slip-v2", JSON.stringify([...sp.slip.values()]));
    localStorage.setItem("pilotcasino-accept", sp.acceptChanges ? "1" : "0");
  } catch {
    /* stockage indisponible : le ticket reste en mémoire */
  }
}
export function loadSlip() {
  try {
    const legs = JSON.parse(localStorage.getItem("pilotcasino-slip-v2") ?? "[]");
    sp.slip = new Map(legs.map((l) => [l.eventId, l]));
    sp.acceptChanges = localStorage.getItem("pilotcasino-accept") !== "0";
  } catch {
    sp.slip = new Map();
  }
}

function toggleSelection(evId, key, price) {
  const ev = findEvent(evId);
  if (!ev) return;
  const current = sp.slip.get(evId);
  if (current?.key === key) sp.slip.delete(evId);
  else {
    if (!current && sp.slip.size >= 10) return toast("Un ticket compte 10 sélections au maximum", "error");
    const d = describe(key, ev);
    sp.slip.set(evId, { eventId: evId, key, price, home: ev.home, away: ev.away, league: ev.league, sport: ev.sport, pick: d.pick, market: d.market, live: ev.live });
    sp.lastAdded = evId;
    if (current) toast("Sélection remplacée : un seul pronostic par match dans un ticket", "info");
  }
  sp.slipTab = "slip";
  saveSlip();
  refreshPicked();
  renderSlip();
}

function refreshPicked() {
  $$(".odd[data-ev]").forEach((b) => b.classList.toggle("picked", sp.slip.get(b.dataset.ev)?.key === b.dataset.key));
}

/** Met à jour les cotes du ticket à partir des données reçues, retire ce qui n'est plus pariable. */
function syncSlip() {
  let changed = false;
  let removed = 0;
  for (const [id, leg] of sp.slip) {
    let price;
    let known = false;
    let closed = false;
    if (sp.match?.id === id) {
      known = true;
      price = sp.match.selections?.[leg.key];
      closed = !sp.match.open;
      leg.suspended = sp.match.suspended;
    } else {
      const ev = allEvents().find((e) => e.id === id);
      if (ev) {
        leg.suspended = ev.suspended;
        closed = !ev.open;
        // Les listes n'ont que le marché principal : on ne connaît la cote des autres qu'au ticket.
        if (MAIN.includes(leg.key)) {
          known = true;
          price = ev.odds?.[leg.key];
        }
      } else if (sp.loadedAt && Date.now() - sp.loadedAt < 10_000) closed = true;
    }
    if (closed) {
      sp.slip.delete(id);
      removed++;
      changed = true;
    } else if (known && price && price !== leg.price) {
      leg.price = price;
      leg.changed = true;
      changed = true;
    }
  }
  if (removed) toast(`${removed} sélection(s) retirée(s) : les paris sont fermés`, "info");
  if (changed) saveSlip();
  renderSlip();
}

const totalOdds = () => Math.round([...sp.slip.values()].reduce((p, l) => p * l.price, 1) * 100) / 100;

function renderSlipCounts() {
  const n = sp.slip.size;
  $("#slip-count").textContent = n;
  const badge = $("#bb-badge");
  if (badge) {
    badge.textContent = n;
    badge.classList.toggle("hidden", !n);
  }
  $("#open-count").textContent = sp.bets.filter((b) => b.status === "open").length;
  $$("[data-slip-tab]").forEach((b) => b.classList.toggle("active", b.dataset.slipTab === sp.slipTab));
  const fab = $("#slip-fab");
  fab.classList.toggle("hidden", !n || document.body.classList.contains("sheet-open") || !document.body.classList.contains("with-slip"));
  if (n) fab.innerHTML = `<span><i class="fab-count">${n}</i>${n > 1 ? "Combiné" : "Pari simple"}</span><span>Cote ${totalOdds().toFixed(2)}</span>`;
}

export function renderSlip() {
  renderSlipCounts();
  const body = $("#slip-body");
  if (!body) return;
  if (sp.slipTab === "bets") {
    body.innerHTML = sp.bets.length
      ? `<div class="mybets">${sp.bets.map(betCard).join("")}</div>`
      : `<div class="slip-empty">${icon("history", { size: 26 })}<b>Aucun pari pour l'instant</b><span>Tes paris en cours et terminés s'affichent ici.</span></div>`;
    return;
  }
  const legs = [...sp.slip.values()];
  if (!legs.length) {
    body.innerHTML = `<div class="slip-empty">${icon("ticket", { size: 26 })}<b>Ton ticket est vide</b><span>Touche une cote pour l'ajouter. Plusieurs matchs font un combiné.</span></div>`;
    return;
  }
  const odds = totalOdds();
  body.innerHTML = `
    <div class="slip-type"><span>${legs.length === 1 ? "Pari simple" : `Combiné de ${legs.length} sélections`}</span><button data-action="clear-slip">Tout retirer</button></div>
    <div class="legs">${legs
      .map(
        (l) => `<div class="leg ${l.changed ? "changed" : ""} ${l.eventId === sp.lastAdded ? "new" : ""} ${l.suspended ? "susp" : ""}">
          <div class="leg-pick"><span>${esc(l.pick)}</span><b class="num">${l.price.toFixed(2)}</b></div>
          <div class="leg-market">${esc(l.market)}</div>
          <div class="leg-match">${sportIcon(l.sport, { size: 13 })}${esc(l.home)} – ${esc(l.away)}${l.live ? `<span class="leg-live"><span class="live-dot"></span>Direct</span>` : ""}</div>
          ${l.suspended ? `<div class="leg-warn">${icon("lock", { size: 13 })}Marché suspendu</div>` : l.changed ? `<div class="leg-warn">Cote mise à jour</div>` : ""}
          <button class="leg-x" data-remove="${esc(l.eventId)}" aria-label="Retirer cette sélection">${icon("close", { size: 15 })}</button>
        </div>`,
      )
      .join("")}</div>
    <div class="slip-foot">
      <div class="label">Mise</div>
      <div class="stake-input">${chip()}<input id="stake" type="number" inputmode="numeric" min="1" value="${sp.stake}" aria-label="Mise du ticket" /></div>
      <div class="quick"><button data-stake="10">+10</button><button data-stake="50">+50</button><button data-stake="100">+100</button><button data-stake="max">Max</button></div>
      <label class="toggle-row accept"><span>Accepter les variations de cote</span><button type="button" class="switch ${sp.acceptChanges ? "on" : ""}" id="accept-toggle" role="switch" aria-checked="${sp.acceptChanges}"></button></label>
      <div class="slip-sum">
        <div><span>Cote totale</span><b class="num">${odds.toFixed(2)}</b></div>
        <div class="potential"><span>Gain potentiel</span><b id="sum-win">${tok(Math.floor(sp.stake * odds))}</b></div>
      </div>
      <button class="btn btn-gold btn-lg btn-block" id="place-bet">Parier ${fmt(sp.stake)} jetons</button>
    </div>`;
  sp.lastAdded = null;
}

function updateSlipTotals() {
  const win = $("#sum-win");
  if (win) win.innerHTML = tok(Math.floor(sp.stake * totalOdds()));
  const btn = $("#place-bet");
  if (btn) btn.textContent = `Parier ${fmt(sp.stake)} jetons`;
}

async function placeBet(btn) {
  if (!sp.slip.size) return;
  if (sp.stake < 1) return toast("Indique une mise d'au moins 1 jeton", "error");
  if (sp.stake > state.balance) return toast("Solde insuffisant pour cette mise", "error");
  btn.disabled = true;
  btn.textContent = "Validation…";
  try {
    const legs = [...sp.slip.values()].map(({ eventId, key, price }) => ({ eventId, key, price }));
    const r = await api("sports/bets", { legs, stake: sp.stake, acceptChanges: sp.acceptChanges });
    setBalance(r.balance);
    toast(
      r.changed
        ? `Pari validé à la cote ${r.totalOdds.toFixed(2)}, mise à jour entre-temps`
        : `Pari validé. Gain potentiel : ${fmt(r.potentialWin)} jetons`,
      "success",
    );
    sp.slip.clear();
    saveSlip();
    refreshPicked();
    sp.slipTab = "bets";
    await loadBets();
    renderSlip();
  } catch (err) {
    toast(err.message, "error");
    await loadEvents();
    renderSlip();
  }
}

/* ---------- Mes paris et cash out ---------- */
const BET_STATUS = { open: "En cours", won: "Gagné", lost: "Perdu", void: "Remboursé", cashout: "Encaissé" };
const LEG_MARK = { won: "check", lost: "close", void: "refresh" };

export function betCard(b) {
  const gain =
    b.status === "open"
      ? `<span>Gain potentiel</span><b>${tok(b.potential_win)}</b>`
      : b.status === "lost"
        ? `<span>Gain</span><b class="neg">0</b>`
        : `<span>${b.status === "cashout" ? "Encaissé" : "Gain"}</span><b class="pos">+${fmt(b.payout)}</b>`;
  return `<div class="bet-card" data-bet="${b.id}">
    <div class="bet-head"><span>${b.legs.length > 1 ? `Combiné de ${b.legs.length}` : "Simple"}, ${esc(shortDay(b.created_at).toLowerCase())} à ${hhmm(b.created_at)}</span><span class="tag ${b.status}">${BET_STATUS[b.status]}</span></div>
    <div class="bet-legs">${b.legs
      .map((l) => {
        const d = describe(l.outcome, l);
        const live = l.status === "live";
        const score = l.home_score !== null && (live || l.status === "finished") ? `${l.home_score}-${l.away_score}` : "";
        return `<div class="bet-leg">
          <span class="st ${l.result}">${LEG_MARK[l.result] ? icon(LEG_MARK[l.result], { size: 12, sw: 2.2 }) : ""}</span>
          <div><b>${esc(d.pick)}</b><small>${esc(d.market)}</small><small>${esc(l.home)} – ${esc(l.away)}${score ? `, <span class="${live ? "live-score" : ""}">${score}${live && l.clock ? ` (${esc(l.clock)})` : ""}</span>` : ""}</small></div>
          <b class="num">${l.price.toFixed(2)}</b>
        </div>`;
      })
      .join("")}</div>
    <div class="bet-foot"><div><span>Mise</span><b>${tok(b.stake)}</b></div><div><span>Cote</span><b class="num">${b.total_odds.toFixed(2)}</b></div><div class="gain">${gain}</div></div>
    ${
      b.status === "open"
        ? b.cashout
          ? `<button class="btn btn-line btn-block cashout-btn" data-cashout="${b.id}" data-value="${b.cashout}">Encaisser ${fmt(b.cashout)} jetons</button>`
          : `<div class="cashout-off">Cash out indisponible pour le moment</div>`
        : ""
    }
  </div>`;
}

export async function loadBets() {
  try {
    const { bets, balance } = await api("sports/bets");
    const before = new Map(sp.bets.map((b) => [b.id, b.status]));
    for (const b of bets) {
      if (before.get(b.id) !== "open" || b.status === "open") continue;
      if (b.status === "won") {
        toast(`Pari gagné : +${fmt(b.payout)} jetons`, "win");
        flare();
      } else if (b.status === "void") toast(`Pari remboursé : +${fmt(b.payout)} jetons`, "info");
      else if (b.status === "lost") toast("Un de tes paris est perdu", "info");
    }
    sp.bets = bets;
    setBalance(balance);
    // Ne pas écraser un bouton de cash out en attente de confirmation.
    if (sp.slipTab === "bets" && !$(".cashout-btn.confirm")) renderSlip();
    else renderSlipCounts();
    hooks.onBets?.();
  } catch {
    /* nouvel essai plus tard */
  }
}
export const hooks = {};

async function cashout(btn) {
  const id = Number(btn.dataset.cashout);
  const value = Number(btn.dataset.value);
  if (!btn.classList.contains("confirm")) {
    btn.classList.add("confirm");
    btn.textContent = `Confirmer : encaisser ${fmt(value)}`;
    setTimeout(() => {
      if (btn.isConnected && btn.classList.contains("confirm")) {
        btn.classList.remove("confirm");
        btn.textContent = `Encaisser ${fmt(value)} jetons`;
      }
    }, 4000);
    return;
  }
  btn.disabled = true;
  try {
    const r = await api("sports/cashout", { betId: id, value });
    setBalance(r.balance);
    toast(`Pari encaissé : +${fmt(r.value)} jetons`, "success");
  } catch (err) {
    toast(err.message, "error");
  }
  await loadBets();
  renderSlip();
}

/* ---------- Volet mobile du ticket ---------- */
export function openSheet() {
  if (!document.body.classList.contains("with-slip")) {
    location.hash = "#/sports";
    setTimeout(openSheet, 50);
    return;
  }
  document.body.classList.add("sheet-open");
  renderSlip();
}
export function closeSheet() {
  document.body.classList.remove("sheet-open");
  renderSlipCounts();
}

/* =========================================================
   Événements
   ========================================================= */
export function sportsClick(e) {
  const t = e.target;
  const odd = t.closest(".odd[data-ev]");
  if (odd) {
    if (odd.classList.contains("susp")) return toast("Marché suspendu quelques secondes", "info");
    toggleSelection(odd.dataset.ev, odd.dataset.key, Number(odd.dataset.price));
    return true;
  }
  const remove = t.closest("[data-remove]");
  if (remove) {
    sp.slip.delete(remove.dataset.remove);
    saveSlip();
    refreshPicked();
    renderSlip();
    return true;
  }
  const sport = t.closest("[data-filter-sport]");
  if (sport) {
    sp.filter.sport = sport.dataset.filterSport;
    sp.filter.league = null;
    if (state.page === "live") paintLive();
    else if (state.page !== "sports") location.hash = "#/sports";
    else paintSports();
    sportsSidebar();
    return true;
  }
  const league = t.closest("[data-filter-league]");
  if (league) {
    const l = league.dataset.filterLeague;
    sp.filter.league = !l || sp.filter.league === l ? null : l;
    if (state.page !== "sports") location.hash = "#/sports";
    else paintSports();
    sportsSidebar();
    $("#upcoming")?.scrollIntoView({ behavior: "smooth", block: "start" });
    return true;
  }
  const day = t.closest("[data-filter-day]");
  if (day) {
    sp.filter.day = day.dataset.filterDay;
    paintDayChips();
    paintMatchList();
    return true;
  }
  const mcat = t.closest("[data-mcat]");
  if (mcat) {
    sp.matchCat = mcat.dataset.mcat;
    paintMatch();
    return true;
  }
  const tab = t.closest("[data-slip-tab]");
  if (tab) {
    sp.slipTab = tab.dataset.slipTab;
    renderSlip();
    if (sp.slipTab === "bets") loadBets();
    return true;
  }
  const stake = t.closest("[data-stake]");
  if (stake) {
    const v = stake.dataset.stake;
    sp.stake = v === "max" ? Math.max(1, Math.min(state.balance, 100_000)) : sp.stake + Number(v);
    renderSlip();
    return true;
  }
  if (t.closest("#accept-toggle")) {
    sp.acceptChanges = !sp.acceptChanges;
    saveSlip();
    renderSlip();
    return true;
  }
  const co = t.closest("[data-cashout]");
  if (co) {
    cashout(co);
    return true;
  }
  const action = t.closest("[data-action]")?.dataset.action;
  if (action === "reset-filters") {
    sp.filter = { sport: "all", league: null, day: "all" };
    paintSports();
    sportsSidebar();
    return true;
  }
  if (action === "clear-slip") {
    sp.slip.clear();
    saveSlip();
    refreshPicked();
    renderSlip();
    return true;
  }
  const place = t.closest("#place-bet");
  if (place) {
    placeBet(place);
    return true;
  }
  if (t.closest("#bb-slip") || t.closest("#slip-fab")) {
    openSheet();
    return true;
  }
  if (t.closest("#scrim") || t.closest("#sheet-close")) {
    closeSheet();
    return true;
  }
  return false;
}

document.addEventListener("input", (e) => {
  if (e.target.id !== "stake") return;
  sp.stake = Math.max(0, Math.floor(Number(e.target.value) || 0));
  updateSlipTotals();
});

/* ---------- Pages ---------- */
page("sports", renderSports, { slip: true, sidebar: sportsSidebar });
page("live", renderLive, { slip: true, sidebar: sportsSidebar });
page("match", renderMatch, { slip: true, nav: "sports", sidebar: sportsSidebar });

// Rafraîchissement des paris : plus fréquent quand des paris sont en cours (cash out, direct).
let betsTimer = 0;
export function startBetsPolling() {
  clearTimeout(betsTimer);
  const loop = async () => {
    if (state.me && !document.hidden) await loadBets();
    const hasOpen = sp.bets.some((b) => b.status === "open");
    betsTimer = setTimeout(loop, hasOpen && document.body.classList.contains("with-slip") ? 6000 : 30000);
  };
  loop();
}
// Les listes hors pages sportives (compteur du direct) restent à jour.
setInterval(() => state.me && !document.hidden && !["sports", "live"].includes(state.page) && loadEvents(), 30_000);
