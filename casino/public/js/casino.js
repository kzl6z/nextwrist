/* =========================================================
   Casino : catalogue, lobby, gabarit commun des jeux
   ========================================================= */
import { $, api, esc, fmt, hhmm, mult, onLeave, page, shortDay, state, tok, view } from "./core.js";
import { GAME_ART, icon } from "./icons.js";

export const GAMES = [
  { id: "crash", name: "Crash", cat: "originals", blurb: "Encaisse avant que la courbe ne s'effondre", meta: "RTP 96,5 %" },
  { id: "plinko", name: "Plinko", cat: "originals", blurb: "Lâche la bille, elle choisit son multiplicateur", meta: "RTP 99 %" },
  { id: "mines", name: "Mines", cat: "originals", blurb: "Retourne les cases sans toucher une mine", meta: "RTP 99 %" },
  { id: "dice", name: "Dice", cat: "originals", blurb: "Au-dessus ou en dessous de ton seuil", meta: "RTP 99 %" },
  { id: "limbo", name: "Limbo", cat: "originals", blurb: "Fixe ta cible, le tirage doit l'atteindre", meta: "RTP 99 %" },
  { id: "hilo", name: "Hi-Lo", cat: "originals", blurb: "Plus haute ou plus basse, carte après carte", meta: "RTP 99 %" },
  { id: "tower", name: "Tower", cat: "originals", blurb: "Gravis huit étages en évitant les pièges", meta: "RTP 98 %" },
  { id: "keno", name: "Keno", cat: "originals", blurb: "Choisis jusqu'à dix numéros sur quarante", meta: "RTP 97,5 à 98,6 %" },
  { id: "wheel", name: "Roue", cat: "originals", blurb: "Trente cases, trois niveaux de risque", meta: "RTP 98,3 à 98,7 %" },
  { id: "coinflip", name: "Pile ou face", cat: "originals", blurb: "Double ta mise à chaque bon choix", meta: "RTP 98 %" },
  { id: "diamonds", name: "Diamonds", cat: "originals", blurb: "Cinq gemmes, compose la meilleure main", meta: "RTP 98,3 %" },
  { id: "crossing", name: "Traversée", cat: "arcade", blurb: "Traverse voie après voie sans te faire faucher", meta: "RTP 98 %" },
  { id: "balloon", name: "Ballon", cat: "arcade", blurb: "Gonfle, encaisse avant qu'il n'éclate", meta: "RTP 98 %" },
  { id: "penalty", name: "Penalty", cat: "arcade", blurb: "Choisis ton coin, le gardien plonge", meta: "RTP 97 %" },
  { id: "rps", name: "Pierre-feuille-ciseaux", cat: "arcade", blurb: "Chaque victoire double ton gain", meta: "RTP 98 %" },
  { id: "darts", name: "Fléchettes", cat: "arcade", blurb: "Plus près du centre, plus gros le gain", meta: "RTP 98 à 98,3 %" },
  { id: "chest", name: "Coffres", cat: "arcade", blurb: "Ouvre un coffre, jusqu'à ×500", meta: "RTP 97,9 à 98 %" },
  { id: "race", name: "Course hippique", cat: "arcade", blurb: "Six chevaux, gagnant ou placé", meta: "RTP 94 %" },
  { id: "roulette", name: "Roulette", cat: "tables", blurb: "Européenne, un seul zéro", meta: "RTP 97,3 %" },
  { id: "blackjack", name: "Blackjack", cat: "tables", blurb: "Bats le croupier sans dépasser 21", meta: "Blackjack payé 3:2" },
  { id: "baccarat", name: "Baccarat", cat: "tables", blurb: "Joueur, banquier ou égalité", meta: "RTP 98,9 % sur le banquier" },
  { id: "videopoker", name: "Video poker", cat: "tables", blurb: "Jacks or Better, table 9/6", meta: "RTP 99,5 % en jeu optimal" },
  { id: "dragontiger", name: "Dragon Tiger", cat: "tables", blurb: "Une carte chacun, la plus haute gagne", meta: "RTP 96,3 %" },
  { id: "sicbo", name: "Sic Bo", cat: "tables", blurb: "Trois dés, des dizaines de paris", meta: "RTP 97,2 % sur petit / grand" },
  { id: "threecard", name: "Three Card Poker", cat: "tables", blurb: "Trois cartes contre le croupier", meta: "RTP 97,7 à 98,1 %" },
  { id: "slots", name: "Fruit Frenzy", cat: "machines", blurb: "Trois rouleaux, jusqu'à ×500", meta: "RTP 93,5 %" },
  { id: "slot5", name: "Nuit dorée", cat: "machines", blurb: "Cinq rouleaux, dix lignes, jokers et lunes", meta: "RTP 96,4 %" },
  { id: "scratch", name: "Ticket à gratter", cat: "machines", blurb: "Trois symboles identiques, jusqu'à ×1 000", meta: "RTP 95,5 %" },
];
export const gameName = (id) => GAMES.find((g) => g.id === id)?.name ?? id;
const CATS = [
  ["all", "Tous les jeux"],
  ["originals", "Originaux"],
  ["arcade", "Arcade"],
  ["tables", "Jeux de table"],
  ["machines", "Machines et tickets"],
];
let lobbyCat = "all";

/* ---------- Réglages des jeux (tables de gains servies par le serveur) ---------- */
let configPromise = null;
export const casinoConfig = () => (configPromise ??= api("casino/config").catch((e) => ((configPromise = null), Promise.reject(e))));

/* ---------- Barre latérale ---------- */
export function casinoSidebar() {
  const el = $("#sidebar");
  const link = (g) =>
    `<a class="side-link ${state.page === g.id ? "active" : ""}" href="#/${g.id}"><span class="side-art">${GAME_ART[g.id]}</span><span class="lbl">${esc(g.name)}</span></a>`;
  el.innerHTML = `
    <div class="side-group"><a class="side-link ${state.page === "casino" ? "active" : ""}" href="#/casino">${icon("casino", { size: 18 })}<span class="lbl">Tous les jeux</span></a></div>
    ${CATS.slice(1)
      .map(([c, label]) => `<div class="side-group"><h4>${label}</h4>${GAMES.filter((g) => g.cat === c).map(link).join("")}</div>`)
      .join("")}`;
}

/* ---------- Lobby ---------- */
function renderLobby() {
  view().innerHTML = `
    <div class="page-head"><div><h1>Casino</h1><p>${GAMES.length} jeux à parties instantanées. Le taux de redistribution de chaque jeu est affiché et vérifiable.</p></div></div>
    <div class="chips lobby-cats" id="lobby-cats"></div>
    <div class="games" id="games"></div>
    <section class="section">
      <div class="section-head"><h2>Derniers gros gains</h2><span class="note">Multiplicateur de ×2 et plus</span></div>
      <div class="feed" id="feed">${'<div class="skeleton" style="height:44px"></div>'.repeat(4)}</div>
    </section>`;
  paintLobby();
  const loadFeed = async () => {
    try {
      const rows = await api("casino/feed");
      const el = $("#feed");
      if (!el) return;
      el.innerHTML = rows.length
        ? rows
            .slice(0, 12)
            .map(
              (r) => `<a class="feed-row" href="#/${r.game}"><span class="feed-art">${GAME_ART[r.game] ?? ""}</span><span class="feed-game">${esc(gameName(r.game))}</span><span class="feed-user">${esc(r.username)}</span><span class="feed-mult num">${mult(r.payout / r.bet)}</span><span class="feed-pay">+${tok(r.payout)}</span><span class="feed-time">${hhmm(r.created_at)}</span></a>`,
            )
            .join("")
        : `<div class="empty">${icon("star")}<b>Aucun gros gain pour l'instant</b><span>Le premier multiplicateur de ×2 apparaîtra ici.</span></div>`;
    } catch {
      /* nouvel essai */
    }
  };
  loadFeed();
  const timer = setInterval(() => !document.hidden && loadFeed(), 10_000);
  onLeave(() => clearInterval(timer));
  $("#lobby-cats").addEventListener("click", (e) => {
    const c = e.target.closest("[data-cat]");
    if (!c) return;
    lobbyCat = c.dataset.cat;
    paintLobby();
  });
}

function paintLobby() {
  $("#lobby-cats").innerHTML = CATS.map(([c, label]) => `<button class="chip ${lobbyCat === c ? "active" : ""}" data-cat="${c}">${label}</button>`).join("");
  $("#games").innerHTML = GAMES.filter((g) => lobbyCat === "all" || g.cat === lobbyCat)
    .map(
      (g) => `<a class="game-tile" href="#/${g.id}">
        <div class="tile-art">${GAME_ART[g.id]}</div>
        <div class="tile-text"><h3>${esc(g.name)}</h3><p>${esc(g.blurb)}</p><span class="tile-meta">${esc(g.meta)}</span></div>
      </a>`,
    )
    .join("");
}

page("casino", renderLobby, { sidebar: casinoSidebar });

/* =========================================================
   Gabarit commun d'une page de jeu
   ========================================================= */
export function gameShell({ id, controls, action = "", stage, rules, stageClass = "" }) {
  const g = GAMES.find((x) => x.id === id);
  return `<div class="game" data-game="${id}">
    <div class="game-head">
      <a href="#/casino" class="icon-btn" aria-label="Retour au casino">${icon("back")}</a>
      <h1 class="display">${esc(g.name)}</h1>
      <span class="game-meta">${esc(g.meta)}</span>
    </div>
    <div class="game-body">
      <aside class="game-controls">${controls}</aside>
      <div class="game-action">${action}</div>
      <section class="game-stage ${stageClass}">${stage}</section>
    </div>
    <div class="game-below">
      <section class="game-rules"><h3>Comment jouer</h3>${rules}</section>
      <section class="game-history"><h3>Tes dernières parties</h3><div id="game-history"><div class="skeleton" style="height:36px"></div></div></section>
    </div>
  </div>`;
}

/** Recharge l'historique personnel du jeu affiché. */
export async function refreshHistory(id) {
  try {
    const rows = await api(`casino/history/${id}`);
    const el = $("#game-history");
    if (!el || state.page !== id) return;
    el.innerHTML = rows.length
      ? `<div class="hist">${rows
          .map((r) => {
            const m = r.bet ? r.payout / r.bet : 0;
            return `<div class="hist-row"><span>${esc(shortDay(r.created_at))}, ${hhmm(r.created_at)}</span><span class="num">${tok(r.bet)}</span><span class="num ${r.payout > r.bet ? "pos" : r.payout === 0 ? "muted" : ""}">${r.payout ? mult(m) : "Perdu"}</span><span class="num ${r.payout > 0 ? "pos" : "muted"}">${r.payout ? `+${fmt(r.payout)}` : "0"}</span></div>`;
          })
          .join("")}</div>`
      : `<p class="muted">Aucune partie pour l'instant. Ta première apparaîtra ici.</p>`;
  } catch {
    /* sans gravité */
  }
}

/** Déclare la page d'un jeu avec la barre latérale du casino. */
export function gamePage(id, render) {
  page(id, (...args) => {
    render(...args);
    refreshHistory(id);
  }, { nav: "casino", sidebar: casinoSidebar });
}

/** Bannière de résultat sous la scène. */
export function banner(el, text, kind = "") {
  if (!el) return;
  el.className = `result-line ${kind}`;
  // Enveloppé : la ligne est en flex, les espaces entre texte et <b> seraient avalés sinon.
  el.innerHTML = text ? `<span>${text}</span>` : "";
}
