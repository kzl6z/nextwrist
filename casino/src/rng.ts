// Seule source de hasard du projet. Pour de l'argent réel, ce module devra
// être remplacé par (ou audité comme) un RNG certifié par un labo agréé.

/** Entier uniforme dans [0, max). Échantillonnage par rejet : aucun biais modulo. */
export function randomInt(max: number): number {
  if (!Number.isInteger(max) || max <= 0 || max > 2 ** 32) throw new Error("max invalide");
  const limit = Math.floor(2 ** 32 / max) * max;
  const buf = new Uint32Array(1);
  while (true) {
    crypto.getRandomValues(buf);
    if (buf[0]! < limit) return buf[0]! % max;
  }
}

/** Réel uniforme dans [0, 1). */
export function randomFloat(): number {
  return randomInt(2 ** 32) / 2 ** 32;
}

export function shuffle<T>(items: T[]): T[] {
  for (let i = items.length - 1; i > 0; i--) {
    const j = randomInt(i + 1);
    [items[i], items[j]] = [items[j]!, items[i]!];
  }
  return items;
}

/** Tire un élément selon des poids entiers. */
export function weightedPick<T>(entries: readonly (readonly [T, number])[]): T {
  const total = entries.reduce((s, [, w]) => s + w, 0);
  let r = randomInt(total);
  for (const [item, w] of entries) {
    if (r < w) return item;
    r -= w;
  }
  throw new Error("unreachable");
}
