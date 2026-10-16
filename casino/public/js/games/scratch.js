/* Ticket à gratter : trois symboles identiques sur neuf cases */
import { $, $$, api, fmt, mult, onLeave, readStake, setBalance, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { SLOT_SYMBOLS, SLOT5_SYMBOLS } from "../icons.js";

const s64 = (body) => `<svg class="sym-art" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const ART = {
  crown: SLOT5_SYMBOLS.crown,
  diamond: SLOT_SYMBOLS["💎"],
  seven: s64('<text x="32" y="48" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="44" font-weight="700" fill="currentColor" stroke="none">7</text>'),
  bell: SLOT_SYMBOLS["🔔"],
  clover: s64('<circle cx="24" cy="22" r="9"/><circle cx="40" cy="22" r="9"/><circle cx="24" cy="38" r="9"/><circle cx="40" cy="38" r="9"/><path d="M32 30c2 10 6 18 12 24"/>'),
  cherry: SLOT_SYMBOLS["🍒"],
  coin: s64('<circle cx="32" cy="32" r="20"/><circle cx="32" cy="32" r="13" stroke-dasharray="3 4"/><path d="M32 24v16M27 28h10M27 36h10" opacity=".7"/>'),
};
const NAMES = { crown: "Couronne", diamond: "Diamant", seven: "Sept", bell: "Cloche", clover: "Trèfle", cherry: "Cerise", coin: "Pièce" };
const PRIZES = [
  ["crown", 1000],
  ["diamond", 100],
  ["seven", 20],
  ["bell", 10],
  ["clover", 5],
  ["cherry", 2],
  ["coin", 1],
];
const sc = { bet: 10, busy: false, ticket: null, revealed: new Set(), scratching: false };

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "scratch",
    controls: `<div><div class="label">Prix du ticket</div>${stakeInput("sc-bet", sc.bet)}</div>
      <div class="paytable sc-pays">${PRIZES.map(([k, m]) => `<div class="pay-row" data-sym="${k}"><span class="pay-syms">${ART[k]}<small>× 3</small></span><b>${mult(m)}</b></div>`).join("")}</div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="sc-buy">Acheter un ticket</button>
      <button class="btn btn-lg btn-block hidden" id="sc-all" style="margin-top:8px">Tout gratter</button>`,
    stage: `
      <div class="sc-stage">
        <div class="sc-ticket" id="sc-ticket">
          <div class="sc-head"><span class="display">Nuit dorée</span><small>Trois symboles identiques gagnent</small></div>
          <div class="sc-grid" id="sc-grid">${Array.from({ length: 9 }, (_, i) => `<button class="sc-cell covered" data-i="${i}" disabled><span class="sc-sym"></span><span class="sc-foil"></span></button>`).join("")}</div>
          <div class="sc-foot" id="sc-foot">Achète un ticket, puis gratte les neuf cases</div>
        </div>
        <div class="result-line" id="sc-result"></div>
      </div>`,
    rules: `<p>Achète un ticket puis gratte les neuf cases, en glissant le doigt ou la souris dessus, ou d'un clic. Si trois cases montrent le même symbole, tu gagnes le prix du ticket multiplié par la valeur de ce symbole.</p>
      <p>Un ticket contient au plus un symbole gagnant. Le résultat est fixé par le serveur au moment de l'achat.</p>`,
  });
  $("#sc-bet").addEventListener("input", (e) => (sc.bet = e.target.value));
  $("#sc-buy").addEventListener("click", buy);
  $("#sc-all").addEventListener("click", () => [...Array(9).keys()].forEach(reveal));
  const grid = $("#sc-grid");
  // Gratter : appui puis glisser sur les cases.
  grid.addEventListener("pointerdown", (e) => {
    if (!sc.ticket) return;
    sc.scratching = true;
    const c = e.target.closest("[data-i]");
    if (c) reveal(Number(c.dataset.i));
  });
  grid.addEventListener("pointermove", (e) => {
    if (!sc.scratching || !sc.ticket) return;
    const c = document.elementFromPoint(e.clientX, e.clientY)?.closest?.("#sc-grid [data-i]");
    if (c) reveal(Number(c.dataset.i));
  });
  const stop = () => (sc.scratching = false);
  window.addEventListener("pointerup", stop);
  onLeave(() => window.removeEventListener("pointerup", stop));
  grid.addEventListener("click", (e) => {
    const c = e.target.closest("[data-i]");
    if (c) reveal(Number(c.dataset.i));
  });
  if (sc.ticket) {
    paintTicket();
    const open = !sc.ticket.done;
    $("#sc-all").classList.toggle("hidden", !open);
    $("#sc-buy").disabled = open;
    $("#sc-foot").textContent = open ? "Gratte les cases" : "Achète un autre ticket";
  }
}

function paintTicket() {
  const cells = $$("#sc-grid .sc-cell");
  cells.forEach((c, i) => {
    c.querySelector(".sc-sym").innerHTML = sc.ticket ? ART[sc.ticket.grid[i]] : "";
    c.classList.toggle("covered", !sc.revealed.has(i));
    c.disabled = !sc.ticket || sc.revealed.has(i);
  });
}

async function buy() {
  if (sc.busy || (sc.ticket && sc.revealed.size < 9)) return;
  const bet = readStake("sc-bet");
  if (!bet) return;
  sc.busy = true;
  $("#sc-buy").disabled = true;
  banner($("#sc-result"), "");
  $$("#sc-grid .sc-cell").forEach((c) => c.classList.remove("win"));
  $$(".sc-pays .pay-row").forEach((r) => r.classList.remove("on"));
  try {
    const r = await api("scratch", { bet });
    // Le solde affiché n'inclut le gain qu'une fois le ticket gratté.
    setBalance(r.balance - r.payout);
    sc.ticket = { ...r, bet };
    sc.revealed = new Set();
    $("#sc-ticket").classList.add("fresh");
    setTimeout(() => $("#sc-ticket")?.classList.remove("fresh"), 500);
    $("#sc-foot").textContent = "Gratte les cases";
    $("#sc-all").classList.remove("hidden");
    paintTicket();
  } catch (err) {
    toast(err.message, "error");
    $("#sc-buy").disabled = false;
  } finally {
    sc.busy = false;
  }
}

function reveal(i) {
  if (!sc.ticket || sc.revealed.has(i) || state.page !== "scratch") return;
  sc.revealed.add(i);
  const cell = $(`#sc-grid [data-i="${i}"]`);
  cell.classList.remove("covered");
  cell.disabled = true;
  if (sc.revealed.size === 9) finish();
}

function finish() {
  const r = sc.ticket;
  setBalance(r.balance);
  $("#sc-all").classList.add("hidden");
  $("#sc-buy").disabled = false;
  $("#sc-buy").textContent = "Acheter un autre ticket";
  if (r.symbol) {
    $$("#sc-grid .sc-cell").forEach((c, i) => r.grid[i] === r.symbol && c.classList.add("win"));
    $(`.sc-pays [data-sym="${r.symbol}"]`)?.classList.add("on");
    $("#sc-foot").textContent = `Trois ${NAMES[r.symbol].toLowerCase()}s`;
    banner($("#sc-result"), r.multiplier > 1 ? `<b>+${fmt(r.payout)}</b> jetons, ${mult(r.multiplier)}` : `Ticket remboursé : ${fmt(r.payout)} jetons`, "win");
    if (r.multiplier >= 10) flare();
  } else {
    $("#sc-foot").textContent = "Pas de symbole gagnant";
    banner($("#sc-result"), "Ticket perdant", "lose");
  }
  sc.ticket = { ...r, done: true };
  refreshHistory("scratch");
}

gamePage("scratch", render);
