/* Jetons de table partagés (Dragon Tiger, Sic Bo) */
export const CHIPS = [
  [5, "#9c3a30"],
  [10, "#3d5a73"],
  [25, "#2f6b4f"],
  [100, "#1d1f1e"],
  [500, "#b8955a"],
];

export const chipsHtml = (id, active) =>
  `<div class="chips-row" id="${id}">${CHIPS.map(([v, c]) => `<button class="chip-token ${v === active ? "active" : ""}" style="--c:${c}" data-chip="${v}">${v}</button>`).join("")}</div>`;
