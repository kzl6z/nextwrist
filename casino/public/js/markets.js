/* =========================================================
   Libellés des pronostics (clés décrites dans src/sports/markets.ts)
   ========================================================= */
import { fmtDec } from "./core.js";

const UNIT = {
  football: ["but", "buts"],
  hockey: ["but", "buts"],
  handball: ["but", "buts"],
  basketball: ["point", "points"],
  rugby: ["point", "points"],
  baseball: ["point", "points"],
  americanfootball: ["point", "points"],
  tennis: ["set", "sets"],
  volleyball: ["set", "sets"],
  badminton: ["set", "sets"],
  tabletennis: ["manche", "manches"],
  esports: ["carte", "cartes"],
  darts: ["leg", "legs"],
  snooker: ["frame", "frames"],
};
/** Sports dont le score compte des sets, manches, cartes, legs ou frames. */
const SET_SPORTS = new Set(["tennis", "volleyball", "badminton", "tabletennis", "esports", "darts", "snooker"]);
const FIRST = { tabletennis: "1re manche", esports: "1re carte" };
const unit = (sport) => (UNIT[sport] ?? ["point", "points"])[1];
const line = (L) => fmtDec(Math.abs(Number(L)), Number(L) % 1 ? 1 : 0);
const signed = (L) => (Number(L) > 0 ? "+" : Number(L) < 0 ? "−" : "") + line(L);
const hasDraw = (sport) => ["football", "hockey", "rugby", "handball"].includes(sport);

/** { group, market, pick, short } pour une clé et un match. */
export function describe(key, ev) {
  const [m, x, y, z] = key.split(":");
  const { home, away, sport } = ev;
  const team = (o) => (o === "home" ? home : o === "away" ? away : "Match nul");
  const short = (o) => (o === "home" ? "1" : o === "away" ? "2" : "N");
  switch (m) {
    case "home":
    case "draw":
    case "away":
      return {
        group: "result",
        market: hasDraw(sport) ? (sport === "hockey" ? "Résultat (temps réglementaire)" : "Résultat") : "Vainqueur",
        pick: team(m),
        short: short(m),
      };
    case "dc":
      return {
        group: "dc",
        market: "Double chance",
        pick: x === "1X" ? `${home} ou nul` : x === "12" ? `${home} ou ${away}` : `Nul ou ${away}`,
        short: x,
      };
    case "dnb":
      return { group: "dnb", market: "Remboursé si match nul", pick: team(x), short: short(x) };
    case "ou":
      return {
        group: "ou",
        market: SET_SPORTS.has(sport) ? `Nombre de ${unit(sport)}` : `Total de ${unit(sport)}`,
        pick: `${y === "over" ? "Plus" : "Moins"} de ${line(x)}`,
        short: y === "over" ? "Plus" : "Moins",
        line: line(x),
      };
    case "th":
    case "ta":
      return {
        group: m,
        market: `${unit(sport)[0].toUpperCase()}${unit(sport).slice(1)} ${m === "th" ? home : away}`,
        pick: `${y === "over" ? "Plus" : "Moins"} de ${line(x)}`,
        short: y === "over" ? "Plus" : "Moins",
        line: line(x),
      };
    case "ah": {
      const L = Number(x);
      return {
        group: "ah",
        market: SET_SPORTS.has(sport) ? `Handicap en ${unit(sport)}` : "Handicap",
        pick: y === "home" ? `${home} ${signed(L)}` : `${away} ${signed(-L)}`,
        short: y === "home" ? signed(L) : signed(-L),
        line: signed(L),
      };
    }
    case "btts":
      return { group: "btts", market: "Les deux équipes marquent", pick: x === "yes" ? "Oui" : "Non", short: x === "yes" ? "Oui" : "Non" };
    case "cs":
      return {
        group: "cs",
        market: SET_SPORTS.has(sport) ? `Score en ${unit(sport)}` : "Score exact",
        pick: x === "other" ? "Autre score" : x,
        short: x === "other" ? "Autre" : x,
      };
    case "oe":
      return { group: "oe", market: `Total de ${unit(sport)} pair ou impair`, pick: x === "odd" ? "Impair" : "Pair", short: x === "odd" ? "Impair" : "Pair" };
    case "mg": {
      if (x === "d") return { group: "mg", market: "Écart de victoire", pick: "Match nul", short: "Nul" };
      const lo = Number(y);
      const hi = Number(z);
      const band = hi >= 999 ? `${lo} et plus` : `${lo} à ${hi}`;
      return { group: "mg", market: "Écart de victoire", pick: `${team(x === "h" ? "home" : "away")} de ${band}`, short: band, side: x };
    }
    case "ht":
      return { group: "ht", market: "Résultat à la mi-temps", pick: team(x), short: short(x) };
    case "q1":
      return { group: "q1", market: "1er quart-temps", pick: team(x), short: short(x) };
    case "s1":
      return { group: "s1", market: FIRST[sport] ?? "1er set", pick: team(x), short: short(x) };
    case "games":
      return { group: "games", market: "Nombre de jeux", pick: `${y === "over" ? "Plus" : "Moins"} de ${line(x)} jeux`, short: y === "over" ? "Plus" : "Moins", line: line(x) };
    case "fin":
      return { group: "fin", market: "Fin du combat", pick: x === "yes" ? "Avant la limite" : "À la décision", short: x === "yes" ? "Avant la limite" : "Décision" };
    case "mt":
      return { group: "mt", market: "Vainqueur et méthode", pick: `${team(x)} ${y === "fin" ? "avant la limite" : "aux points"}`, short: y === "fin" ? "Avant la limite" : "Aux points", side: x };
    case "rd":
      return { group: "rd", market: "Round de la fin", pick: y ? `Rounds ${x} à ${y}` : `Round ${x}`, short: y ? `Rounds ${x} à ${y}` : `Round ${x}` };
    default:
      return { group: "other", market: "Autre", pick: key, short: key };
  }
}

/** Ordre et catégories des marchés sur la fiche match. */
export const GROUP_ORDER = ["result", "dc", "dnb", "fin", "mt", "rd", "btts", "ou", "th", "ta", "games", "oe", "ah", "mg", "ht", "q1", "s1", "cs"];
export const CATEGORIES = [
  ["main", "Principaux", ["result", "dc", "dnb", "btts", "fin", "mt", "rd"]],
  ["totals", "Totaux", ["ou", "th", "ta", "games", "oe"]],
  ["handicap", "Handicaps", ["ah", "mg"]],
  ["periods", "Périodes", ["ht", "q1", "s1"]],
  ["scores", "Scores exacts", ["cs"]],
];
