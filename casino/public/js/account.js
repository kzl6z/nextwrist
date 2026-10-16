/* =========================================================
   Compte : solde, paris, historique, classement
   ========================================================= */
import { $, $$, api, esc, fmt, hhmm, hue, initials, page, shortDay, state, toast, tok, view } from "./core.js";
import { gameName } from "./casino.js";
import { icon } from "./icons.js";
import { betCard, hooks as sportsHooks, loadBets, sp } from "./sports.js";

const KIND = {
  welcome_bonus: ["gift", "Bonus de bienvenue"],
  daily_bonus: ["gift", "Bonus quotidien"],
  sport_bet: ["ticket", "Pari sportif"],
  sport_win: ["ticket", "Gain de pari sportif"],
  sport_refund: ["ticket", "Pari sportif remboursé"],
  sport_cashout: ["ticket", "Cash out"],
};
function kindLabel(kind) {
  if (KIND[kind]) return KIND[kind];
  const m = kind.match(/^(.+)_(bet|win)$/);
  if (m) return ["casino", `${m[2] === "bet" ? "Mise" : "Gain"} ${gameName(m[1])}`];
  return ["spark", kind];
}

let tab = "bets";
const acc = { txs: [], board: [] };

async function renderAccount() {
  const me = state.me;
  view().innerHTML = `
    <div class="profile">
      <span class="avatar avatar-lg" style="--h:${hue(me.username)}">${esc(initials(me.username))}</span>
      <div><h1 class="display">${esc(me.username)}</h1><p>Membre PilotCasino</p></div>
      <button class="btn btn-quiet" data-action="logout">${icon("logout", { size: 18 })}Se déconnecter</button>
    </div>
    <div class="kpis" id="kpis">${'<div class="kpi skeleton"></div>'.repeat(4)}</div>
    <div class="tabs" id="acc-tabs">
      <button data-acc="bets">Mes paris</button><button data-acc="history">Mouvements du solde</button><button data-acc="ranking">Classement</button>
    </div>
    <div id="acc-body">${'<div class="skeleton"></div>'.repeat(4)}</div>`;
  $("#acc-tabs").addEventListener("click", (e) => {
    const t = e.target.closest("[data-acc]")?.dataset.acc;
    if (!t) return;
    tab = t;
    paint();
  });
  try {
    const [txs, board] = await Promise.all([api("transactions"), api("leaderboard"), loadBets()]);
    if (state.page !== "compte") return;
    acc.txs = txs;
    acc.board = board;
    const rank = board.findIndex((u) => u.username === me.username);
    const bestWin = Math.max(0, ...txs.filter((t) => /_win$|cashout/.test(t.kind)).map((t) => t.amount));
    const open = sp.bets.filter((b) => b.status === "open");
    $("#kpis").innerHTML = `
      <div class="kpi"><small>Solde</small><b>${tok(state.balance)}</b></div>
      <div class="kpi"><small>Paris en cours</small><b>${open.length}</b></div>
      <div class="kpi"><small>Meilleur gain récent</small><b class="${bestWin ? "pos" : ""}">${bestWin ? `+${fmt(bestWin)}` : "Aucun"}</b></div>
      <div class="kpi"><small>Classement</small><b>${rank >= 0 ? `${rank + 1}<sup>${rank ? "e" : "er"}</sup>` : "Hors top 10"}</b></div>`;
    paint();
  } catch (err) {
    toast(err.message, "error");
  }
}

function paint() {
  if (state.page !== "compte") return;
  $$("#acc-tabs [data-acc]").forEach((b) => b.classList.toggle("active", b.dataset.acc === tab));
  const body = $("#acc-body");
  if (tab === "bets") {
    body.innerHTML = sp.bets.length
      ? `<div class="bets-grid">${sp.bets.map(betCard).join("")}</div>`
      : `<div class="empty">${icon("ticket")}<b>Aucun pari pour l'instant</b><a class="btn btn-gold btn-sm" href="#/sports">Voir les matchs</a></div>`;
  } else if (tab === "history") {
    body.innerHTML = acc.txs.length
      ? `<div class="tx-list">${acc.txs
          .map((t) => {
            const [ico, label] = kindLabel(t.kind);
            return `<div class="tx"><span class="tx-ico">${icon(ico, { size: 18 })}</span><div><b>${esc(label)}</b><small>${esc(shortDay(t.created_at))}, ${hhmm(t.created_at)}</small></div>
              <div class="amt ${t.amount > 0 ? "pos" : ""}">${t.amount > 0 ? "+" : "−"}${fmt(Math.abs(t.amount))}<small>solde ${fmt(t.balance_after)}</small></div></div>`;
          })
          .join("")}</div>`
      : `<div class="empty">${icon("history")}<b>Aucun mouvement</b></div>`;
  } else {
    const b = acc.board;
    body.innerHTML = `<div class="ranking">${b
      .map(
        (u, i) => `<div class="rank-row ${u.username === state.me.username ? "me" : ""}">
          <span class="rank-n display">${i + 1}</span>
          <span class="avatar" style="--h:${hue(u.username)}">${esc(initials(u.username))}</span>
          <b>${esc(u.username)}</b>
          <span class="rank-bal">${tok(u.balance)}</span>
        </div>`,
      )
      .join("")}</div>`;
  }
}

sportsHooks.onBets = () => state.page === "compte" && tab === "bets" && !$(".cashout-btn.confirm") && paint();

page("compte", renderAccount, {
  sidebar: () => {
    $("#sidebar").innerHTML = `<div class="side-group">
      <a class="side-link" href="#/sports">${icon("football", { size: 18 })}<span class="lbl">Paris sportifs</span></a>
      <a class="side-link" href="#/live"><span class="live-dot"></span><span class="lbl">En direct</span></a>
      <a class="side-link" href="#/casino">${icon("casino", { size: 18 })}<span class="lbl">Casino</span></a></div>`;
  },
});
