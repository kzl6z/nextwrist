/* =========================================================
   PilotCasino — démarrage, connexion, événements globaux
   ========================================================= */
import { $, $$, adjustStake, api, DAY, flare, hooks, initials, hue, route, runCleanups, setBalance, state, toast } from "./core.js";
import { chip, guillocheSvg, guillocheUrl, icon } from "./icons.js";
import { closeSheet, loadBets, loadEvents, loadSlip, renderSlip, sportsClick, startBetsPolling } from "./sports.js";
import "./casino.js";
import "./account.js";
import "./games/index.js";

/* ---------- Motif gravé partagé ---------- */
document.documentElement.style.setProperty(
  "--guilloche",
  guillocheUrl({ size: 600, layers: 16, petals: 22, base: 0.12, depth: 0.09, twist: 0.42, steps: 260 }, "#c9a96a", 0.55),
);
$("#auth-rosace").innerHTML = guillocheSvg({ size: 900, layers: 26, petals: 28, base: 0.08, depth: 0.08, twist: 0.33, steps: 360 }, "#c9a96a", 0.45);
$("#wallet-tok").innerHTML = chip();
$("#auth-perks").innerHTML = [
  ["gift", "1 000 jetons offerts à l'inscription, puis 500 chaque jour"],
  ["live", "Paris en direct et cash out sur six sports"],
  ["casino", "Quinze jeux, dont Plinko, Mines, Crash et Blackjack"],
]
  .map(([ico, text]) => `<li>${icon(ico)}${text}</li>`)
  .join("");

$("#bottombar").innerHTML = `
  <a href="#/sports" data-nav="sports">${icon("football")}Sports</a>
  <a href="#/live" data-nav="live">${icon("live")}Direct</a>
  <a href="#/casino" data-nav="casino">${icon("casino")}Casino</a>
  <button id="bb-slip">${icon("ticket")}Ticket<i class="bb-badge hidden" id="bb-badge">0</i></button>
  <a href="#/compte" data-nav="compte">${icon("user")}Compte</a>`;

hooks.onUnauthorized = () => showAuth();
hooks.beforeRoute = () => closeSheet();

/* ---------- Bonus quotidien ---------- */
function renderBonus() {
  if (!state.me) return;
  const wait = (state.me.nextBonusAt ?? 0) - Date.now();
  const btn = $("#bonus-btn");
  btn.classList.toggle("ready", wait <= 0);
  const h = Math.floor(wait / 3_600_000);
  const m = Math.floor((wait % 3_600_000) / 60_000);
  btn.innerHTML = `${icon("gift", { size: 18 })}<span>${wait <= 0 ? "Bonus disponible" : `Bonus dans ${h} h ${String(m).padStart(2, "0")}`}</span>`;
  btn.title = wait <= 0 ? "Récupérer le bonus quotidien" : "Prochain bonus quotidien";
}

async function claimBonus() {
  if ((state.me.nextBonusAt ?? 0) > Date.now()) {
    renderBonus();
    return toast("Ton bonus quotidien est déjà récupéré. Reviens après le compte à rebours.", "info");
  }
  try {
    const { balance } = await api("bonus", {});
    setBalance(balance);
    state.me.nextBonusAt = Date.now() + DAY;
    renderBonus();
    toast(`Bonus récupéré : +${state.me.dailyBonus ?? 500} jetons`, "win");
    flare();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Connexion ---------- */
let authMode = "login";
function setAuthMode(mode) {
  authMode = mode;
  $$("#auth .seg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("#auth-title").textContent = mode === "login" ? "Bon retour" : "Créer un compte";
  $("#auth-sub").textContent =
    mode === "login" ? "Connecte-toi pour retrouver ton solde et tes paris." : "Choisis un pseudo : 1 000 jetons t'attendent.";
  $("#auth-submit").textContent = mode === "login" ? "Se connecter" : "Créer mon compte";
  $("#auth-form [name=password]").autocomplete = mode === "login" ? "current-password" : "new-password";
  $("#auth-error").textContent = "";
}
$$("#auth .seg button").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.mode)));

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
      toast("Compte créé : 1 000 jetons offerts", "win");
      flare();
    }
  } catch (err) {
    $("#auth-error").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

function showAuth() {
  runCleanups();
  state.me = null;
  $("#app").classList.add("hidden");
  $("#auth").classList.remove("hidden");
}

export async function logout() {
  await api("logout", {}).catch(() => {});
  showAuth();
}
hooks.logout = logout;

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
  renderSlip();
  if (!["sports", "live"].includes(state.page)) loadEvents();
  startBetsPolling();
}

/* ---------- Événements globaux (délégation) ---------- */
document.addEventListener("click", (e) => {
  if (sportsClick(e)) return;
  const amount = e.target.closest("[data-amt]");
  if (amount) return adjustStake(amount.dataset.amt, amount.dataset.op);
  const action = e.target.closest("[data-action]")?.dataset.action;
  if (action === "bonus" || e.target.closest("#bonus-btn")) return claimBonus();
  if (action === "logout") return logout();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeSheet();
});
window.addEventListener("hashchange", () => state.me && route());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && state.me) {
    loadEvents();
    loadBets();
  }
});
setInterval(renderBonus, 30_000);

boot();
