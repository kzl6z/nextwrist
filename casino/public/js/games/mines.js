/* Mines : grille 5×5, éviter les mines, encaisser quand on veut */
import { $, $$, api, fmt, fmtDec, onSpace, readStake, setBalance, setStakeDisabled, stakeInput, state, toast, flare } from "../core.js";
import { banner, gamePage, gameShell, refreshHistory } from "../casino.js";
import { icon } from "../icons.js";

const mn = { bet: 10, mines: 3, game: null, busy: false };

function render() {
  document.querySelector("#view").innerHTML = gameShell({
    id: "mines",
    controls: `
      <div><div class="label">Mise</div>${stakeInput("mn-bet", mn.bet)}</div>
      <div><div class="label">Nombre de mines <b id="mn-count-show"></b></div>
        <input type="range" class="range" id="mn-count" min="1" max="24" value="${mn.mines}" aria-label="Nombre de mines" /></div>
      <div class="info-list" id="mn-info"></div>`,
    action: `<button class="btn btn-gold btn-lg btn-block" id="mn-main">Commencer</button>
      <button class="btn btn-block hidden" id="mn-random" style="margin-top:8px">Retourner une case au hasard</button>`,
    stage: `
      <div class="mines-stage">
        <div class="mines-grid" id="mn-grid">${Array.from({ length: 25 }, (_, i) => `<button class="mt" data-cell="${i}" aria-label="Case ${i + 1}" disabled></button>`).join("")}</div>
        <div class="result-line" id="mn-result"></div>
      </div>`,
    rules: `<p>Choisis le nombre de mines cachées dans la grille, puis retourne des cases. Chaque case sûre augmente le multiplicateur ; une mine fait perdre la mise.</p>
      <p>Encaisse quand tu veux. Plus il y a de mines, plus chaque case rapporte.</p>`,
  });
  $("#mn-bet").addEventListener("input", (e) => {
    mn.bet = e.target.value;
    paint();
  });
  $("#mn-count").addEventListener("input", (e) => {
    mn.mines = Number(e.target.value);
    paint();
  });
  $("#mn-main").addEventListener("click", main);
  $("#mn-random").addEventListener("click", () => {
    const free = $$("#mn-grid .mt:not(.open)").map((b) => Number(b.dataset.cell));
    if (free.length) reveal(free[Math.floor(Math.random() * free.length)]);
  });
  $("#mn-grid").addEventListener("click", (e) => {
    const b = e.target.closest("[data-cell]");
    if (b && !b.disabled) reveal(Number(b.dataset.cell));
  });
  onSpace(main);
  paint();
  api("mines")
    .then((d) => apply(d, false))
    .catch((err) => toast(err.message, "error"));
}

/** Multiplicateur après k cases sûres (même formule que le serveur). */
function multAfter(mines, k) {
  let m = 0.99;
  for (let i = 0; i < k; i++) m *= (25 - i) / (25 - mines - i);
  return k ? Math.floor(m * 10_000) / 10_000 : 1;
}

function apply(d, animate = true) {
  if (state.page !== "mines") return;
  setBalance(d.balance);
  mn.game = d.game;
  if (d.game) mn.mines = d.game.mines;
  paint(animate, d.hit);
}

function paint(animate = false, hit = false) {
  if (state.page !== "mines") return;
  const g = mn.game;
  const playing = g?.status === "playing";
  $("#mn-count").value = mn.mines;
  $("#mn-count").disabled = playing;
  $("#mn-count-show").textContent = mn.mines;
  setStakeDisabled("mn-bet", playing);
  const bet = Math.max(0, Math.floor(Number($("#mn-bet").value) || 0));
  const safe = g?.revealed.filter((c) => !g.bombs?.includes(c)).length ?? 0;
  const btn = $("#mn-main");
  if (playing) {
    btn.className = "btn btn-win btn-lg btn-block";
    btn.disabled = !g.revealed.length;
    btn.textContent = g.revealed.length ? `Encaisser ${fmt(Math.floor(g.bet * g.multiplier))}` : "Retourne une première case";
    $("#mn-info").innerHTML = `<div><span>Multiplicateur actuel</span><b>×${fmtDec(g.multiplier)}</b></div><div><span>Case suivante</span><b>×${fmtDec(g.next)}</b></div><div><span>Prochaine case sûre</span><b>${fmtDec(((25 - mn.mines - safe) / (25 - safe)) * 100, 1)} %</b></div>`;
  } else {
    btn.className = "btn btn-gold btn-lg btn-block";
    btn.disabled = false;
    btn.textContent = `Commencer pour ${fmt(bet)} jetons`;
    $("#mn-info").innerHTML = `<div><span>Après 1 case sûre</span><b>×${fmtDec(multAfter(mn.mines, 1))}</b></div><div><span>Après 3 cases sûres</span><b>×${fmtDec(multAfter(mn.mines, Math.min(3, 25 - mn.mines)))}</b></div>`;
  }
  $("#mn-random").classList.toggle("hidden", !playing);
  // Grille
  $$("#mn-grid .mt").forEach((b) => {
    const c = Number(b.dataset.cell);
    const revealed = g?.revealed.includes(c);
    const bomb = g?.bombs?.includes(c);
    b.disabled = !playing || revealed;
    b.className = "mt";
    if (revealed) b.classList.add("open", bomb ? "bomb" : "gem");
    else if (g && !playing && g.bombs) b.classList.add("ghost", bomb ? "bomb" : "gem");
    b.innerHTML = revealed || (g && !playing && g.bombs) ? icon(bomb ? "bomb" : "gem", { size: 30, sw: 1.5 }) : "";
    if (animate && revealed && c === g.revealed[g.revealed.length - 1]) b.classList.add("pop");
  });
  if (g && !playing && animate) {
    if (g.status === "won") {
      banner($("#mn-result"), `<b>+${fmt(g.payout)}</b> jetons, ×${fmtDec(g.multiplier)}`, "win");
      if (g.multiplier >= 5) flare();
    } else banner($("#mn-result"), hit ? "Une mine : mise perdue" : "Partie terminée", "lose");
  } else if (playing) banner($("#mn-result"), "");
}

async function main() {
  if (mn.busy) return;
  const playing = mn.game?.status === "playing";
  if (playing && !mn.game.revealed.length) return;
  mn.busy = true;
  try {
    if (playing) {
      apply(await api("mines/cashout", {}));
      refreshHistory("mines");
    } else {
      const bet = readStake("mn-bet");
      if (!bet) return;
      apply(await api("mines/start", { bet, mines: mn.mines }));
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    mn.busy = false;
  }
}

async function reveal(cell) {
  if (mn.busy || mn.game?.status !== "playing") return;
  mn.busy = true;
  try {
    const d = await api("mines/reveal", { cell });
    apply(d);
    if (d.game.status !== "playing") refreshHistory("mines");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    mn.busy = false;
  }
}

gamePage("mines", render);
