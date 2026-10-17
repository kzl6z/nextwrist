/* Cartes à jouer partagées (Blackjack, Hi-Lo, Baccarat, Video poker) */
import { SUIT_RED } from "../icons.js";

const FACE = { J: "V", Q: "D", K: "R", A: "A" };

/** Carte : « 10♥ ». `??` = carte cachée. */
export function cardHtml(card, { delay = 0, animate = false, extra = "" } = {}) {
  const style = animate ? ` style="animation-delay:${delay}ms"` : "";
  const deal = animate ? " deal" : "";
  if (card === "??" || !card) return `<div class="pcard back${deal} ${extra}"${style}></div>`;
  const rank = card.slice(0, -1);
  const suit = card.slice(-1);
  const red = SUIT_RED.has(suit) ? " red" : "";
  const shown = FACE[rank] ?? rank;
  return `<div class="pcard${red}${deal} ${extra}"${style} aria-label="${rank}${suit}">
    <span class="pc-corner"><b>${shown}</b><i>${suit}</i></span>
    <span class="pc-mid">${suit}</span>
    <span class="pc-corner flip"><b>${shown}</b><i>${suit}</i></span>
  </div>`;
}
