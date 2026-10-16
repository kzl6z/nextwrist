/* =========================================================
   PilotCasino — socle partagé (état, API, routeur, utilitaires)
   ========================================================= */
import { chip, icon } from "./icons.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const fmt = (n) => Number(n).toLocaleString("fr-FR");
export const fmtDec = (n, d = 2) => Number(n).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export const view = () => $("#view");
/** Montant suivi du jeton. */
export const tok = (n) => `<span class="amount-tok">${fmt(n)}${chip()}</span>`;
/** Multiplicateur lisible, sans zéros inutiles : ×2, ×0,4, ×1,98 */
export const mult = (m) => `×${Number(m).toLocaleString("fr-FR", { maximumFractionDigits: m >= 100 ? 0 : 2 })}`;

export const state = {
  me: null,
  balance: 0,
  page: null,
  params: [],
};

/* ---------- API ---------- */
export async function api(path, body) {
  const res = await fetch(
    `/api/${path}`,
    body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "login" && path !== "register") hooks.onUnauthorized?.();
  if (!res.ok) {
    const err = new Error(data.error ?? "Connexion au serveur impossible. Réessaie dans un instant.");
    err.data = data;
    err.status = res.status;
    throw err;
  }
  return data;
}
export const hooks = {};

/* ---------- Notifications ---------- */
const TOAST_ICON = { info: "spark", success: "check", error: "close", win: "star" };
export function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", type === "error" ? "alert" : "status");
  el.innerHTML = `${icon(TOAST_ICON[type] ?? "spark", { size: 18 })}<span>${esc(message)}</span>`;
  $("#toasts").append(el);
  setTimeout(() => {
    el.classList.add("out");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, 3800);
}

/** Éclat doré discret pour les gros gains. */
export function flare() {
  const el = document.createElement("div");
  el.className = "flare";
  document.body.append(el);
  setTimeout(() => el.remove(), 1300);
}

/* ---------- Solde animé ---------- */
let balanceFrame = 0;
export function setBalance(value) {
  if (value === undefined || value === null) return;
  const el = $("#balance");
  const from = state.balance;
  state.balance = value;
  cancelAnimationFrame(balanceFrame);
  if (from === value || !el) {
    if (el) el.textContent = fmt(value);
    return;
  }
  el.classList.remove("up", "down");
  el.classList.add(value > from ? "up" : "down");
  const start = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - start) / 600);
    el.textContent = fmt(Math.round(from + (value - from) * (1 - (1 - k) ** 3)));
    if (k < 1) balanceFrame = requestAnimationFrame(step);
    else setTimeout(() => el.classList.remove("up", "down"), 600);
  };
  balanceFrame = requestAnimationFrame(step);
}

/* ---------- Identité des équipes ---------- */
export function hue(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 360;
}
export function initials(name) {
  const words = String(name).replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  // « J. Sinner » → JS ; « Real Madrid » → RM ; « Lyon » → LY
  return (words.length > 1 ? words[0][0] + words[words.length - 1][0] : words[0].slice(0, 2)).toUpperCase();
}
export const crest = (name, cls = "") => `<span class="crest ${cls}" style="--h:${hue(name)}">${esc(initials(name))}</span>`;

export const SPORTS = {
  football: "Football",
  basketball: "Basketball",
  tennis: "Tennis",
  rugby: "Rugby",
  hockey: "Hockey sur glace",
  mma: "MMA",
  americanfootball: "Football américain",
  baseball: "Baseball",
};
export const sportName = (s) => SPORTS[s] ?? s;

/* ---------- Dates ---------- */
export const DAY = 86_400_000;
const dayStart = (ms) => new Date(ms).setHours(0, 0, 0, 0);
export const dayDiff = (ms) => Math.round((dayStart(ms) - dayStart(Date.now())) / DAY);
export const hhmm = (ms) => new Date(ms).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
export function shortDay(ms) {
  const d = dayDiff(ms);
  if (d === 0) return "Aujourd'hui";
  if (d === 1) return "Demain";
  if (d === -1) return "Hier";
  return new Date(ms).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
}
export function startsIn(ms) {
  const min = Math.round((ms - Date.now()) / 60_000);
  if (min <= 0) return "Imminent";
  if (min < 60) return `Dans ${min} min`;
  return dayDiff(ms) === 0 ? hhmm(ms) : `${shortDay(ms)} ${hhmm(ms)}`;
}
export function countBy(items, key) {
  const m = new Map();
  for (const x of items) m.set(key(x), (m.get(key(x)) ?? 0) + 1);
  return m;
}
export function groupBy(items, key) {
  const m = new Map();
  for (const x of items) (m.get(key(x)) ?? m.set(key(x), []).get(key(x))).push(x);
  return m;
}

/* =========================================================
   Routeur : #/page/param
   ========================================================= */
const ROUTES = {};
let cleanups = [];
/** Nettoyage à exécuter en quittant la page (minuteries, écouteurs). */
export const onLeave = (fn) => cleanups.push(fn);
export const runCleanups = () => cleanups.splice(0).forEach((fn) => fn());

/**
 * Déclare une page. `slip` : affiche le ticket à droite ; `nav` : entrée de navigation active ;
 * `sidebar` : fonction qui remplit la barre latérale.
 */
export function page(name, render, opts = {}) {
  ROUTES[name] = { render, slip: false, nav: name, ...opts };
}

export function route() {
  runCleanups();
  const [wanted, ...params] = location.hash.replace(/^#\/?/, "").split("/");
  const name = ROUTES[wanted] ? wanted : "sports";
  const r = ROUTES[name];
  state.page = name;
  state.params = params.map(decodeURIComponent);
  document.body.dataset.page = name;
  document.body.classList.toggle("with-slip", !!r.slip);
  $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === r.nav));
  hooks.beforeRoute?.(r);
  window.scrollTo({ top: 0, behavior: "instant" });
  r.render(...state.params);
  r.sidebar?.();
}

/* ---------- Clavier : barre d'espace = action principale ---------- */
export function onSpace(fn) {
  const handler = (e) => {
    if (e.code !== "Space" || e.repeat) return;
    if (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(document.activeElement?.tagName ?? "")) return;
    e.preventDefault();
    fn();
  };
  window.addEventListener("keydown", handler);
  onLeave(() => window.removeEventListener("keydown", handler));
}

/* ---------- Champ de mise ---------- */
export function stakeInput(id, value, max = 10_000) {
  return `<div class="stake-input" id="${id}-box">
    ${chip()}
    <input id="${id}" type="number" inputmode="numeric" min="1" max="${max}" value="${value}" aria-label="Mise" />
    <button type="button" data-amt="${id}" data-op="half" aria-label="Diviser la mise par deux">½</button>
    <button type="button" data-amt="${id}" data-op="double" aria-label="Doubler la mise">×2</button>
    <button type="button" data-amt="${id}" data-op="max">Max</button>
  </div>`;
}

export function adjustStake(id, op) {
  const input = $(`#${id}`);
  if (!input || input.disabled) return;
  const max = Number(input.max) || 10_000;
  const v = Math.floor(Number(input.value)) || 1;
  const next = op === "half" ? Math.floor(v / 2) : op === "double" ? v * 2 : state.balance;
  input.value = Math.max(1, Math.min(next, max, Math.max(1, state.balance)));
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

export function readStake(id, max = 10_000) {
  const v = Math.floor(Number($(`#${id}`)?.value));
  if (!Number.isFinite(v) || v < 1) return toast("Indique une mise d'au moins 1 jeton", "error"), 0;
  if (v > max) return toast(`La mise maximum est de ${fmt(max)} jetons`, "error"), 0;
  if (v > state.balance) return toast("Solde insuffisant pour cette mise", "error"), 0;
  return v;
}

export function setStakeDisabled(id, disabled) {
  const box = $(`#${id}-box`);
  if (!box) return;
  box.classList.toggle("disabled", disabled);
  $(`#${id}`).disabled = disabled;
}
