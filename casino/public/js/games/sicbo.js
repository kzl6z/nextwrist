/* Sic Bo : trois dés, des dizaines de paris sur un même tapis */
import { $, $$, api, fmt, setBalance, sleep, state, toast, tok, flare } from "../core.js";
import { banner, casinoConfig, gamePage, gameShell, refreshHistory } from "../casino.js";
import { chipsHtml } from "./chips.js";

const sb = { chip: 10, bets: {}, busy: false, last: [1, 3, 5], recent: [], totals: null };
const total = () => Object.values(sb.bets).reduce((s, v) => s + v, 0);
const TOTALS_FALLBACK = { 4: 60, 5: 30, 6: 17, 7: 12, 8: 8, 9: 6, 10: 6, 11: 6, 12: 6, 13: 8, 14: 12, 15: 17, 16: 30, 17: 60 };

/** Points d'un dé : positions sur une grille 3×3. */
const PIPS = { 1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8] };
export const dieHtml = (n, cls = "") =>
  `<span class="die ${cls}" aria-label="${n}">${Array.from({ length: 9 }, (_, i) => `<i class="${PIPS[n].includes(i) ? "on" : ""}"></i>`).join("")}</span>`;

const cell = (key, inner, note, cls = "") => `<button class="sb-cell ${cls}" data-key="${key}">${inner}${note ? `<small>${note}</small>` : ""}<span class="zone-chip" data-chip-for="${key}"></span></button>`;

function boardHtml() {
  const t = sb.totals ?? TOTALS_FALLBACK;
  return `
    <div class="sb-row sb-top">
      ${cell("small:", "<b>Petit</b>", "4 à 10 · 1 pour 1", "wide")}
      ${cell("odd:", "<b>Impair</b>", "1 pour 1")}
      <div class="sb-triples">
        ${[1, 2, 3, 4, 5, 6].map((n) => cell(`triple:${n}`, `<span class="mini-dice">${dieHtml(n, "xs")}${dieHtml(n, "xs")}${dieHtml(n, "xs")}</span>`, "180 pour 1", "tri")).join("")}
        ${cell("anytriple:", "<b>Tout triple</b>", "30 pour 1", "any")}
      </div>
      ${cell("even:", "<b>Pair</b>", "1 pour 1")}
      ${cell("big:", "<b>Grand</b>", "11 à 17 · 1 pour 1", "wide")}
    </div>
    <div class="sb-row sb-totals">${Object.keys(t).map((n) => cell(`total:${n}`, `<b class="display">${n}</b>`, `${t[n]} pour 1`)).join("")}</div>
    <div class="sb-row sb-doubles">${[1, 2, 3, 4, 5, 6].map((n) => cell(`double:${n}`, `<span class="mini-dice">${dieHtml(n, "xs")}${dieHtml(n, "xs")}</span>`, "10 pour 1")).join("")}</div>
    <div class="sb-row sb-singles">${[1, 2, 3, 4, 5, 6].map((n) => cell(`single:${n}`, dieHtml(n, "sm"), "1, 2 ou 3 pour 1")).join("")}</div>`;
}

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "sicbo",
    stageClass: "felt-stage",
    controls: `
      <div><div class="label">Jeton</div>${chipsHtml("sb-chips", sb.chip)}</div>
      <div class="rl-actions"><button class="btn btn-sm" id="sb-undo">Annuler le dernier</button><button class="btn btn-sm" id="sb-clear">Tout effacer</button></div>
      <div class="info-list"><div><span>Mise totale</span><b id="sb-total">0</b></div><div><span>Paris placés</span><b id="sb-count">0</b></div></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="sb-roll">Lancer les dés</button>`,
    stage: `
      <div class="sb-stage">
        <div class="sb-bowl">
          <div class="sb-dice" id="sb-dice">${sb.last.map((n) => dieHtml(n, "lg")).join("")}</div>
          <div class="sb-sum display" id="sb-sum"></div>
        </div>
        <div class="sb-recent" id="sb-recent"></div>
        <div class="board-scroll"><div class="sb-board" id="sb-board">${boardHtml()}</div></div>
      </div>
      <div class="result-line" id="sb-result"></div>`,
    rules: `<p>Trois dés sont lancés. Pose tes jetons sur une ou plusieurs cases : petit (total de 4 à 10) ou grand (11 à 17), pair ou impair, un total précis, un double, un triple ou un numéro simple.</p>
      <p>Petit, grand, pair et impair perdent sur un triple. Le numéro simple paie 1, 2 ou 3 pour 1 selon le nombre de dés qui le montrent.</p>`,
  });
  $("#sb-chips").addEventListener("click", (e) => {
    const c = e.target.closest("[data-chip]");
    if (!c) return;
    sb.chip = Number(c.dataset.chip);
    $$("#sb-chips .chip-token").forEach((x) => x.classList.toggle("active", x === c));
  });
  sb.history = [];
  $("#sb-board").addEventListener("click", (e) => {
    const c = e.target.closest("[data-key]");
    if (!c || sb.busy) return;
    if (total() + sb.chip > state.balance) return toast("Solde insuffisant pour ajouter ce jeton", "error");
    if (total() + sb.chip > 10_000) return toast("La mise totale est limitée à 10 000 jetons", "error");
    sb.bets[c.dataset.key] = (sb.bets[c.dataset.key] ?? 0) + sb.chip;
    sb.history.push([c.dataset.key, sb.chip]);
    paintBets();
  });
  $("#sb-undo").addEventListener("click", () => {
    if (sb.busy) return;
    const last = sb.history.pop();
    if (!last) return;
    sb.bets[last[0]] -= last[1];
    if (!sb.bets[last[0]]) delete sb.bets[last[0]];
    paintBets();
  });
  $("#sb-clear").addEventListener("click", () => {
    if (sb.busy) return;
    sb.bets = {};
    sb.history = [];
    paintBets();
  });
  $("#sb-roll").addEventListener("click", roll);
  paintBets();
  paintRecent();
  if (!sb.totals)
    casinoConfig()
      .then((c) => {
        sb.totals = c.sicboTotals;
        if (state.page === "sicbo") {
          $("#sb-board").innerHTML = boardHtml();
          paintBets();
        }
      })
      .catch(() => {});
}

function paintBets() {
  $$("#sb-board [data-chip-for]").forEach((el) => {
    const v = sb.bets[el.dataset.chipFor];
    el.textContent = v ? fmt(v) : "";
    el.classList.toggle("on", !!v);
  });
  $("#sb-total").innerHTML = tok(total());
  $("#sb-count").textContent = Object.keys(sb.bets).length;
  const btn = $("#sb-roll");
  btn.disabled = !total() || sb.busy;
  btn.textContent = total() ? `Lancer pour ${fmt(total())} jetons` : "Place une mise sur le tapis";
}

function paintRecent() {
  $("#sb-recent").innerHTML = sb.recent.map((d) => `<span class="sb-past">${d.map((n) => dieHtml(n, "xs")).join("")}<b>${d[0] + d[1] + d[2]}</b></span>`).join("");
}

async function roll() {
  if (sb.busy || !total()) return;
  sb.busy = true;
  paintBets();
  banner($("#sb-result"), "");
  $$("#sb-board .sb-cell").forEach((c) => c.classList.remove("hit", "won"));
  $("#sb-sum").textContent = "";
  const bets = Object.entries(sb.bets).map(([k, amount]) => {
    const [type, value] = k.split(":");
    return value ? { type, value: Number(value), amount } : { type, amount };
  });
  try {
    const r = await api("sicbo", { bets });
    setBalance(r.balance - r.payout);
    const box = $("#sb-dice");
    // Les dés roulent quelques instants (faces décoratives), puis affichent le tirage du serveur.
    box.classList.add("rolling");
    for (let i = 0; i < 9; i++) {
      box.innerHTML = [0, 1, 2].map(() => dieHtml(1 + Math.floor(Math.random() * 6), "lg")).join("");
      await sleep(70 + i * 12);
    }
    box.classList.remove("rolling");
    if (state.page !== "sicbo") return;
    box.innerHTML = r.dice.map((n) => dieHtml(n, "lg land")).join("");
    const sum = r.dice[0] + r.dice[1] + r.dice[2];
    const triple = r.dice[0] === r.dice[1] && r.dice[1] === r.dice[2];
    $("#sb-sum").textContent = triple ? `Triple ${r.dice[0]}` : `${sum} · ${sum <= 10 ? "Petit" : "Grand"} · ${sum % 2 ? "Impair" : "Pair"}`;
    sb.last = r.dice;
    sb.recent = [r.dice, ...sb.recent].slice(0, 10);
    paintRecent();
    setBalance(r.balance);
    for (const b of r.bets) {
      const el = $(`#sb-board [data-key="${b.type}:${b.value ?? ""}"]`);
      if (el && b.win) el.classList.add("won");
    }
    banner($("#sb-result"), r.payout ? `Retour : <b>${fmt(r.payout)}</b> jetons pour ${fmt(r.total)} misés` : `Mise de ${fmt(r.total)} jetons perdue`, r.payout > r.total ? "win" : "lose");
    if (r.payout >= r.total * 10) flare();
    refreshHistory("sicbo");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    sb.busy = false;
    if (state.page === "sicbo") paintBets();
  }
}

gamePage("sicbo", render);
