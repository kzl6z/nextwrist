/* =========================================================
   Icônes et illustrations dessinées pour PilotCasino
   (trait fin, couleur héritée : currentColor)
   ========================================================= */
const svg = (body, { size = 20, vb = 24, sw = 1.6, cls = "ico" } = {}) =>
  `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 ${vb} ${vb}" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

const PATHS = {
  football:
    '<circle cx="12" cy="12" r="9"/><path d="M12 7.2l4 2.9-1.5 4.7h-5L8 10.1z"/><path d="M12 3v4.2M16 10.1l4.4-1.4M14.5 14.8l2.7 3.8M9.5 14.8l-2.7 3.8M8 10.1L3.6 8.7"/>',
  basketball:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3v18"/><path d="M5.6 5.6c2.6 2.4 3.6 4.4 3.6 6.4s-1 4-3.6 6.4M18.4 5.6c-2.6 2.4-3.6 4.4-3.6 6.4s1 4 3.6 6.4"/>',
  tennis: '<circle cx="12" cy="12" r="9"/><path d="M5.2 5.9c3.4 2.9 3.4 9.3 0 12.2M18.8 5.9c-3.4 2.9-3.4 9.3 0 12.2"/>',
  rugby:
    '<ellipse cx="12" cy="12" rx="10" ry="6" transform="rotate(-35 12 12)"/><path d="M8.6 15.4l6.8-6.8M10 12.2l1.8 1.8M11.6 10.6l1.8 1.8M13.2 9l1.8 1.8"/>',
  hockey: '<path d="M7 3l6.5 13.5c.4.9 1.3 1.5 2.3 1.5H20v2.5h-5.2c-2 0-3.8-1.2-4.6-3L4.6 4"/><ellipse cx="6.5" cy="19" rx="3" ry="1.4"/>',
  mma: '<path d="M7 10V7.5A3.5 3.5 0 0110.5 4h4A3.5 3.5 0 0118 7.5V13a5 5 0 01-5 5h-1.5A4.5 4.5 0 017 13.5"/><path d="M7 10a2.5 2.5 0 00-2.5 2.5v.5A2 2 0 006.5 15H9M10 9.5h8M9 18v2.5h7V18"/>',
  americanfootball:
    '<ellipse cx="12" cy="12" rx="10" ry="6" transform="rotate(-35 12 12)"/><path d="M9 15l6-6M10.4 11.6l2 2M12 10l2 2"/>',
  baseball: '<circle cx="12" cy="12" r="9"/><path d="M6.5 5c2 2 2 12 0 14M17.5 5c-2 2-2 12 0 14"/>',
  handball: '<path d="M3 20V6h18v14"/><path d="M3 10h18M7 6v14M11 6v14M15 6v14M19 6v14" opacity=".35"/><circle cx="12" cy="15" r="3.6" fill="#0e100f"/><path d="M9.6 13.6c1.5.5 3.3.5 4.8 0"/>',
  volleyball:
    '<circle cx="12" cy="12" r="9"/><path d="M12 3c2.6 2.3 3.6 5.4 3 9M4.2 7.6c3.4-.6 6.4.4 7.8 4.4M7 19.5c-.4-3.4 1.4-6 5-7.5M12 12c3 1.6 5.6 1.8 8.6.6"/>',
  tabletennis: '<circle cx="9.5" cy="9.5" r="6"/><path d="M13.7 13.7l5.8 5.8"/><circle cx="18.5" cy="5.5" r="1.8"/>',
  badminton: '<path d="M5.5 18.5l2-2 3 3-2 2a2.1 2.1 0 01-3-3z"/><path d="M7.5 16.5L14 4M10.5 19.5L20 10M9 18l8.5-11.5M14 4l6 6"/>',
  darts: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><path d="M12 12l6.5-6.5M16.5 3.5l.6 3.4 3.4.6"/>',
  snooker: '<circle cx="8" cy="15" r="3"/><circle cx="14" cy="15" r="3"/><circle cx="11" cy="9.8" r="3"/><path d="M3 21l7-5" opacity=".6"/>',
  esports:
    '<path d="M7 8h10a4 4 0 014 4v2.5a2.5 2.5 0 01-4.5 1.5L15 14H9l-1.5 2A2.5 2.5 0 013 14.5V12a4 4 0 014-4z"/><path d="M8 11v3M6.5 12.5h3"/><circle cx="15.5" cy="11.5" r=".8" fill="currentColor"/><circle cx="17.5" cy="13" r=".8" fill="currentColor"/>',
  boxing: '<path d="M6 12V8.5A4.5 4.5 0 0110.5 4H13a5 5 0 015 5v4.5a5.5 5.5 0 01-5.5 5.5H11a5 5 0 01-5-5z"/><path d="M6 12a2.5 2.5 0 002.5 2.5H12M10 19v2h6v-2.5"/>',
  cricket: '<path d="M4.5 19.5l9.5-9.5 2.5 2.5L7 22z"/><path d="M14 10l4.5-4.5"/><circle cx="18" cy="17" r="2.2"/>',
  aussierules: '<ellipse cx="12" cy="12" rx="10" ry="6" transform="rotate(-35 12 12)"/><path d="M8.6 15.4l6.8-6.8"/>',
  golf: '<path d="M8 21V3l10 4-10 4"/><ellipse cx="9" cy="21" rx="5" ry="1"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 01-8 0zM8 6H5a3 3 0 003 4M16 6h3a3 3 0 01-3 4M12 13v4M8.5 20h7M10 17h4"/>',
  live: '<circle cx="12" cy="12" r="2.4"/><path d="M8.2 8.2a5.4 5.4 0 000 7.6M15.8 8.2a5.4 5.4 0 010 7.6M5.4 5.4a9.3 9.3 0 000 13.2M18.6 5.4a9.3 9.3 0 010 13.2"/>',
  casino: '<path d="M12 3.5c3.5 3.2 7 5.6 7 9a3.6 3.6 0 01-6 2.6L14 20h-4l1-4.9a3.6 3.6 0 01-6-2.6c0-3.4 3.5-5.8 7-9z"/>',
  ticket: '<path d="M4 7a2 2 0 012-2h12a2 2 0 012 2v2a2.5 2.5 0 000 5v3a2 2 0 01-2 2H6a2 2 0 01-2-2v-3a2.5 2.5 0 000-5z"/><path d="M14 5.5v2M14 10.5v3M14 16.5v2"/>',
  user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5"/>',
  gift: '<path d="M4 9.5h16V13H4zM5.5 13h13v7h-13zM12 9.5V20"/><path d="M12 9.5C10.5 6 7 5.6 7 7.6c0 1.6 2.5 1.9 5 1.9zM12 9.5c1.5-3.5 5-3.9 5-1.9 0 1.6-2.5 1.9-5 1.9z"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  back: '<path d="M14.5 5.5L8 12l6.5 6.5"/>',
  next: '<path d="M9.5 5.5L16 12l-6.5 6.5"/>',
  down: '<path d="M5.5 9.5L12 16l6.5-6.5"/>',
  up: '<path d="M5.5 14.5L12 8l6.5 6.5"/>',
  lock: '<rect x="5.5" y="10.5" width="13" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 017 0v2.5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  bolt: '<path d="M13 3L6 13.5h5.5L10.5 21 18 10h-5.5z"/>',
  star: '<path d="M12 3.8l2.5 5.2 5.6.7-4.1 3.9 1 5.6L12 16.5l-5 2.7 1-5.6-4.1-3.9 5.6-.7z"/>',
  logout: '<path d="M14 4h4a2 2 0 012 2v12a2 2 0 01-2 2h-4M10 16l-4-4 4-4M6 12h10"/>',
  history: '<path d="M4 12a8 8 0 102.4-5.7M4 4.5v3.3h3.3"/><path d="M12 8v4.5l3 1.8"/>',
  coin: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/><path d="M12 3.5v2.4M12 18.1v2.4M3.5 12h2.4M18.1 12h2.4M6 6l1.7 1.7M16.3 16.3L18 18M6 18l1.7-1.7M16.3 7.7L18 6"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5"/>',
  shield: '<path d="M12 3.5l7 2.8v5.2c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6.3z"/>',
  refresh: '<path d="M19 12a7 7 0 01-12.2 4.7M5 12a7 7 0 0112.2-4.7M17.5 3.8v3.7h-3.7M6.5 20.2v-3.7h3.7"/>',
  undo: '<path d="M9 14.5L4.5 10 9 5.5"/><path d="M4.5 10H14a5.5 5.5 0 010 11h-2"/>',
  bomb: '<circle cx="11" cy="13.5" r="6.5"/><path d="M15.5 8.8l2-2M17.5 6.8l1.5-.3M17.5 6.8l.3-1.5"/>',
  gem: '<path d="M6.5 4.5h11L21 9.5 12 20 3 9.5z"/><path d="M3 9.5h18M9 4.5L7.6 9.5 12 20l4.4-10.5L15 4.5"/>',
  heads: '<circle cx="12" cy="12" r="8.5"/><path d="M9.5 16.5c0-2.5 1-3.5 2.5-3.5s2.5 1 2.5 3.5M12 13a2.5 2.5 0 100-5 2.5 2.5 0 000 5z"/>',
  tails: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 9.5h7M12 9.5V16"/>',
  dice: '<rect x="4" y="4" width="16" height="16" rx="3.5"/><circle cx="8.5" cy="8.5" r=".9" fill="currentColor"/><circle cx="15.5" cy="15.5" r=".9" fill="currentColor"/><circle cx="12" cy="12" r=".9" fill="currentColor"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h10"/>',
};

export const icon = (name, opts) => svg(PATHS[name] ?? PATHS.trophy, opts);
export const sportIcon = (sport, opts) => icon(PATHS[sport] ? sport : "trophy", opts);

/** Jeton : petite plaque gravée, utilisée à côté de chaque montant. */
export const chip = (cls = "tok") =>
  `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="currentColor" opacity=".18"/><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3.2 2.6"/><circle cx="12" cy="12" r="5.4" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>`;

/* =========================================================
   Guilloché : rosace gravée (motif des jetons et des billets)
   ========================================================= */
export function guillochePath({ size = 400, layers = 14, petals = 18, base = 0.18, depth = 0.11, twist = 0.38, steps = 240 } = {}) {
  const c = size / 2;
  let d = "";
  for (let l = 0; l < layers; l++) {
    const r0 = c * (base + (l / layers) * 0.72);
    const phase = l * twist;
    for (let i = 0; i <= steps; i++) {
      const t = (i / steps) * Math.PI * 2;
      const r = r0 + c * depth * Math.sin(petals * t + phase) * (0.55 + 0.45 * Math.cos(3 * t + phase));
      const x = (c + r * Math.cos(t)).toFixed(1);
      const y = (c + r * Math.sin(t)).toFixed(1);
      d += `${i ? "L" : "M"}${x} ${y}`;
    }
    d += "Z";
  }
  return d;
}

export function guillocheSvg(opts = {}, stroke = "#c9a96a", width = 0.6) {
  const size = opts.size ?? 400;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}"><path d="${guillochePath(opts)}" fill="none" stroke="${stroke}" stroke-width="${width}"/></svg>`;
}

/** Image CSS (data URI) du guilloché, calculée une fois au démarrage. */
export const guillocheUrl = (opts, stroke, width) =>
  `url("data:image/svg+xml,${encodeURIComponent(guillocheSvg(opts, stroke, width))}")`;

/* =========================================================
   Illustrations des jeux (trait doré, viewBox 200×200)
   ========================================================= */
const art = (body) =>
  `<svg class="art" viewBox="0 0 200 200" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

function card(x, y, rank, suit, rot = 0, red = false) {
  return `<g transform="rotate(${rot} ${x + 30} ${y + 42})">
    <rect x="${x}" y="${y}" width="60" height="84" rx="7" fill="#0e100f"/>
    <text x="${x + 9}" y="${y + 20}" font-family="Bodoni Moda Variable, serif" font-size="17" font-weight="600" fill="currentColor" stroke="none" ${red ? 'opacity=".75"' : ""}>${rank}</text>
    <text x="${x + 30}" y="${y + 56}" text-anchor="middle" font-size="24" fill="currentColor" stroke="none" ${red ? 'opacity=".75"' : ""}>${suit}</text>
  </g>`;
}

export const GAME_ART = {
  crash: art(`
    <path d="M30 160h145M30 160V35" opacity=".35"/>
    <path d="M30 120h145M30 80h145" opacity=".12"/>
    <path d="M32 158C80 154 118 136 146 96c10-14 17-31 22-50"/>
    <circle cx="168" cy="46" r="7" fill="currentColor"/>
    <path d="M168 46l-16 6M168 46l-4 16" opacity=".5"/>`),
  plinko: art(`
    ${[0, 1, 2, 3, 4, 5]
      .map((r) => Array.from({ length: r + 2 }, (_, i) => `<circle cx="${100 - (r + 1) * 12 + i * 24}" cy="${42 + r * 22}" r="2.6" fill="currentColor" stroke="none"/>`).join(""))
      .join("")}
    <path d="M100 22c-3 10 9 16 4 28s-14 18-10 30 14 16 10 28-12 20-6 32" stroke-dasharray="3 5" opacity=".7"/>
    <circle cx="100" cy="22" r="6.5" fill="currentColor"/>
    ${[0, 1, 2, 3, 4, 5, 6].map((i) => `<rect x="${22 + i * 22.5}" y="168" width="20" height="12" rx="3" opacity="${i === 3 ? 1 : 0.4}"/>`).join("")}`),
  mines: art(`
    ${Array.from({ length: 16 }, (_, k) => {
      const x = 36 + (k % 4) * 33;
      const y = 36 + Math.floor(k / 4) * 33;
      return `<rect x="${x}" y="${y}" width="27" height="27" rx="5" opacity="${[5, 10].includes(k) ? 1 : 0.32}"/>`;
    }).join("")}
    <path d="M77.5 77l5-6h7l5 6-8.5 10z" fill="currentColor" stroke="none"/>
    <circle cx="118.5" cy="118.5" r="7.5" fill="currentColor" stroke="none"/>
    <path d="M124 112l4-4M128 108l3-.5" />`),
  dice: art(`
    <g transform="rotate(-12 80 108)"><rect x="42" y="70" width="76" height="76" rx="14"/>
      <circle cx="62" cy="90" r="5" fill="currentColor"/><circle cx="98" cy="126" r="5" fill="currentColor"/><circle cx="80" cy="108" r="5" fill="currentColor"/></g>
    <g transform="rotate(14 136 86)" opacity=".75"><rect x="108" y="54" width="58" height="58" rx="11"/>
      <circle cx="124" cy="70" r="4" fill="currentColor"/><circle cx="150" cy="70" r="4" fill="currentColor"/><circle cx="124" cy="96" r="4" fill="currentColor"/><circle cx="150" cy="96" r="4" fill="currentColor"/></g>`),
  limbo: art(`
    <path d="M44 160a70 70 0 01112 0" opacity=".3"/>
    <path d="M56 160a56 56 0 0188 0" opacity=".5"/>
    <path d="M100 160V48"/>
    <path d="M86 62l14-16 14 16"/>
    <path d="M70 104h60" stroke-dasharray="4 5" opacity=".7"/>
    <circle cx="100" cy="104" r="5" fill="currentColor"/>`),
  hilo: art(`
    ${card(50, 62, "7", "♠", -8)}
    ${card(92, 54, "Q", "♥", 9, true)}
    <path d="M168 58l10-12 10 12M168 142l10 12 10-12" opacity=".8"/>`),
  tower: art(`
    ${[0, 1, 2, 3, 4, 5]
      .map((r) =>
        [0, 1, 2]
          .map((c) => `<rect x="${52 + c * 34}" y="${150 - r * 22}" width="28" height="16" rx="4" opacity="${r < 3 && c === (r * 2) % 3 ? 1 : 0.28}" ${r < 3 && c === (r * 2) % 3 ? 'fill="currentColor"' : ""}/>`)
          .join(""),
      )
      .join("")}
    <path d="M100 26l-8 10h16z" fill="currentColor" stroke="none"/>`),
  keno: art(`
    ${Array.from({ length: 20 }, (_, k) => {
      const x = 44 + (k % 5) * 28;
      const y = 52 + Math.floor(k / 5) * 28;
      const on = [1, 7, 8, 13, 19].includes(k);
      return `<circle cx="${x}" cy="${y}" r="10" opacity="${on ? 1 : 0.3}" ${on ? 'fill="currentColor" fill-opacity=".22"' : ""}/>`;
    }).join("")}`),
  wheel: art(`
    <circle cx="100" cy="106" r="66"/>
    <circle cx="100" cy="106" r="18"/>
    ${Array.from({ length: 12 }, (_, i) => {
      const a = (i / 12) * Math.PI * 2;
      return `<path d="M${(100 + 18 * Math.cos(a)).toFixed(1)} ${(106 + 18 * Math.sin(a)).toFixed(1)}L${(100 + 66 * Math.cos(a)).toFixed(1)} ${(106 + 66 * Math.sin(a)).toFixed(1)}" opacity=".45"/>`;
    }).join("")}
    <path d="M100 28l-9 -14h18z" fill="currentColor" stroke="none" transform="translate(0 16)"/>`),
  coinflip: art(`
    <ellipse cx="100" cy="104" rx="56" ry="56"/>
    <ellipse cx="100" cy="104" rx="44" ry="44" stroke-dasharray="2 5" opacity=".6"/>
    <text x="100" y="122" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="52" font-weight="600" fill="currentColor" stroke="none">P</text>
    <path d="M150 52c10 6 16 15 18 25M50 156c-10-6-16-15-18-25" opacity=".45"/>`),
  roulette: art(`
    <circle cx="100" cy="100" r="68"/>
    <circle cx="100" cy="100" r="54" opacity=".5"/>
    <circle cx="100" cy="100" r="22"/>
    ${Array.from({ length: 18 }, (_, i) => {
      const a = (i / 18) * Math.PI * 2;
      return `<path d="M${(100 + 54 * Math.cos(a)).toFixed(1)} ${(100 + 54 * Math.sin(a)).toFixed(1)}L${(100 + 68 * Math.cos(a)).toFixed(1)} ${(100 + 68 * Math.sin(a)).toFixed(1)}" opacity=".6"/>`;
    }).join("")}
    <path d="M100 78v44M78 100h44" opacity=".7"/>
    <circle cx="146" cy="62" r="5" fill="currentColor"/>`),
  blackjack: art(`${card(46, 52, "A", "♠", -10)}${card(94, 58, "K", "♥", 8, true)}`),
  baccarat: art(`${card(30, 62, "4", "♣", -14)}${card(70, 52, "5", "♦", 0, true)}${card(110, 62, "9", "♠", 14)}`),
  videopoker: art(`
    ${["10", "J", "Q", "K", "A"].map((r, i) => card(12 + i * 36, 58 + Math.abs(i - 2) * 6, r, "♠", (i - 2) * 6)).join("")}`),
  slots: art(`
    <rect x="34" y="52" width="132" height="96" rx="12"/>
    <path d="M78 52v96M122 52v96" opacity=".4"/>
    ${[56, 100, 144]
      .map((x) => `<text x="${x}" y="114" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="40" font-weight="700" fill="currentColor" stroke="none">7</text>`)
      .join("")}
    <path d="M28 100h6M166 100h6" />
    <path d="M176 70v40" opacity=".6"/><circle cx="176" cy="66" r="6" fill="currentColor"/>`),
};

/* =========================================================
   Symboles de la machine à sous (le serveur renvoie des identifiants)
   ========================================================= */
const sym = (body) => `<svg class="sym-art" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
export const SLOT_SYMBOLS = {
  "🍒": sym('<circle cx="22" cy="44" r="10"/><circle cx="42" cy="46" r="9"/><path d="M22 34c2-10 8-18 18-22M42 37c-1-9-1-17-2-25M40 12c6-2 12 0 15 4-5 2-11 1-15-4z"/>'),
  "🍋": sym('<path d="M10 34c0-11 10-20 22-20s22 9 22 20-10 18-22 18S10 45 10 34z"/><path d="M8 34h4M52 34h4" /><path d="M22 30c3-4 7-6 12-6" opacity=".6"/>'),
  "🍊": sym('<circle cx="32" cy="36" r="17"/><path d="M32 19c0-5 3-8 8-9M32 19c-5-4-10-4-14-2 4 4 9 5 14 2z"/><circle cx="26" cy="32" r="1.4" fill="currentColor"/><circle cx="36" cy="40" r="1.4" fill="currentColor"/><circle cx="38" cy="30" r="1.4" fill="currentColor"/>'),
  "🍇": sym('<circle cx="26" cy="26" r="6"/><circle cx="38" cy="26" r="6"/><circle cx="32" cy="36" r="6"/><circle cx="20" cy="36" r="6"/><circle cx="44" cy="36" r="6"/><circle cx="26" cy="46" r="6"/><circle cx="38" cy="46" r="6"/><circle cx="32" cy="56" r="5"/><path d="M32 20c0-6 3-10 8-12"/>'),
  "🔔": sym('<path d="M20 44V30a12 12 0 0124 0v14l4 5H16z"/><path d="M28 54a4 4 0 008 0M32 18v-5"/>'),
  "💎": sym('<path d="M18 14h28l10 12-24 28L8 26z"/><path d="M8 26h48M26 14l-4 12 10 28 10-28-4-12"/>'),
};

export const SUIT_RED = new Set(["♥", "♦"]);

/* =========================================================
   Deuxième série de jeux : illustrations du lobby
   ========================================================= */
function die(x, y, s, face, rot = 0, opacity = 1) {
  const P = { 1: [[0.5, 0.5]], 2: [[0.27, 0.27], [0.73, 0.73]], 3: [[0.27, 0.27], [0.5, 0.5], [0.73, 0.73]], 4: [[0.27, 0.27], [0.73, 0.27], [0.27, 0.73], [0.73, 0.73]], 5: [[0.27, 0.27], [0.73, 0.27], [0.5, 0.5], [0.27, 0.73], [0.73, 0.73]], 6: [[0.27, 0.25], [0.73, 0.25], [0.27, 0.5], [0.73, 0.5], [0.27, 0.75], [0.73, 0.75]] };
  return `<g transform="rotate(${rot} ${x + s / 2} ${y + s / 2})" opacity="${opacity}"><rect x="${x}" y="${y}" width="${s}" height="${s}" rx="${s * 0.18}" fill="#0e100f"/>${P[face].map(([a, b]) => `<circle cx="${x + a * s}" cy="${y + b * s}" r="${s * 0.075}" fill="currentColor" stroke="none"/>`).join("")}</g>`;
}

Object.assign(GAME_ART, {
  dragontiger: art(`
    ${card(26, 56, "D", "♦", -12, true)}
    ${card(114, 56, "T", "♣", 12)}
    <path d="M100 82l12 16-12 16-12-16z" fill="#0e100f"/>
    <path d="M94 98h12" opacity=".6"/>`),
  sicbo: art(`
    <ellipse cx="100" cy="112" rx="78" ry="56" opacity=".25"/>
    ${die(46, 84, 52, 5, -14)}${die(104, 90, 50, 3, 10)}${die(76, 36, 48, 6, 4, 0.8)}`),
  diamonds: art(`
    <g transform="translate(18 92) scale(1.25)" opacity=".5"><path d="M4 8h22l6 8-17 20L-2 16z"/><path d="M-2 16h34M11 8l-3 8 7 20 7-20-3-8"/></g>
    <g transform="translate(140 92) scale(1.25)" opacity=".5"><path d="M4 8h22l6 8-17 20L-2 16z"/><path d="M-2 16h34M11 8l-3 8 7 20 7-20-3-8"/></g>
    <g transform="translate(62 46) scale(2.4)" stroke-width=".9"><path d="M4 8h22l6 8-17 20L-2 16z" fill="currentColor" fill-opacity=".14"/><path d="M-2 16h34M11 8l-3 8 7 20 7-20-3-8"/></g>
    <path d="M100 26v-10M124 34l7-7M76 34l-7-7" opacity=".6"/>
    <path d="M40 162h120" opacity=".3"/>`),
  scratch: art(`
    <rect x="30" y="44" width="140" height="112" rx="10"/>
    ${Array.from({ length: 9 }, (_, k) => {
      const x = 58 + (k % 3) * 42;
      const y = 72 + Math.floor(k / 3) * 30;
      return k < 5 ? `<circle cx="${x}" cy="${y}" r="10" ${k % 2 === 0 ? 'fill="currentColor" fill-opacity=".25"' : ""}/>` : `<rect x="${x - 15}" y="${y - 11}" width="30" height="22" rx="4" fill="currentColor" fill-opacity=".55" stroke="none"/>`;
    }).join("")}
    <path d="M128 150l26-44 10 6-26 44z" fill="#0e100f"/><path d="M134 140l14 8" opacity=".6"/>`),
  darts: art(`
    <circle cx="96" cy="108" r="64"/><circle cx="96" cy="108" r="46" opacity=".55"/><circle cx="96" cy="108" r="28" opacity=".75"/><circle cx="96" cy="108" r="9" fill="currentColor"/>
    ${Array.from({ length: 10 }, (_, i) => {
      const a = (i / 10) * Math.PI * 2;
      return `<path d="M${(96 + 28 * Math.cos(a)).toFixed(1)} ${(108 + 28 * Math.sin(a)).toFixed(1)}L${(96 + 64 * Math.cos(a)).toFixed(1)} ${(108 + 64 * Math.sin(a)).toFixed(1)}" opacity=".25"/>`;
    }).join("")}
    <path d="M100 104l58-58"/><path d="M150 40l14-2-2 14M156 46l12-2-2 12" opacity=".8"/>`),
  chest: art(`
    <path d="M44 104h112v54a6 6 0 01-6 6H50a6 6 0 01-6-6z"/>
    <path d="M44 104c0-26 20-40 56-40s56 14 56 40" opacity=".5" transform="rotate(-14 44 104)"/>
    <path d="M44 124h112M92 104v26h16v-26" opacity=".6"/>
    <path d="M100 58V34M70 66L58 46M130 66l12-20M80 92l-26-8M120 92l26-8" opacity=".55"/>
    <circle cx="100" cy="88" r="7" fill="currentColor"/>`),
  race: art(`
    <path d="M60 46c-14 10-22 28-22 50 0 30 16 54 30 64l14-8C70 142 60 122 60 96c0-20 8-34 18-42zM140 46c14 10 22 28 22 50 0 30-16 54-30 64l-14-8c12-10 22-30 22-56 0-20-8-34-18-42z"/>
    ${[[52, 78], [47, 100], [52, 124], [148, 78], [153, 100], [148, 124]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="2.6" fill="currentColor" stroke="none"/>`).join("")}
    <path d="M86 40h28" opacity=".5"/>
    <text x="100" y="114" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="34" font-weight="600" fill="currentColor" stroke="none">1</text>`),
  slot5: art(`
    <rect x="20" y="50" width="160" height="100" rx="12"/>
    ${[0, 1, 2, 3, 4].map((i) => `<rect x="${30 + i * 29}" y="60" width="24" height="80" rx="5" opacity=".35"/>`).join("")}
    <path d="M42 120L71 82l29 38 29-38 29 38" opacity=".9"/>
    ${[[42, 120], [71, 82], [100, 120], [129, 82], [158, 120]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="5" fill="currentColor" stroke="none"/>`).join("")}
    <path d="M150 34a14 14 0 1010 24 11 11 0 01-10-24z" fill="currentColor" stroke="none" opacity=".9"/>`),
  threecard: art(`${card(26, 62, "A", "♥", -14, true)}${card(70, 52, "K", "♥", 0, true)}${card(114, 62, "Q", "♥", 14, true)}`),
  crossing: art(`
    <path d="M30 40v124M170 40v124" opacity=".5"/>
    <path d="M65 40v124M100 40v124M135 40v124" stroke-dasharray="10 9" opacity=".35"/>
    <path d="M110 60h18a6 6 0 016 6v26a6 6 0 01-6 6h-18a6 6 0 01-6-6V66a6 6 0 016-6z" opacity=".75"/><path d="M108 72h22M108 86h22" opacity=".5"/>
    <circle cx="48" cy="128" r="11" fill="currentColor" fill-opacity=".2"/><path d="M48 117v-8M44 109h8"/>
    <path d="M62 128h24M80 122l6 6-6 6" opacity=".8"/>`),
  balloon: art(`
    <path d="M100 30c-30 0-48 24-48 52 0 32 26 54 44 62l-4 8h16l-4-8c18-8 44-30 44-62 0-28-18-52-48-52z"/>
    <path d="M78 58c-8 8-10 18-9 28" opacity=".55"/>
    <path d="M100 152c-6 10 6 16 0 26" opacity=".7"/>
    <text x="100" y="98" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="28" font-weight="600" fill="currentColor" stroke="none">×</text>`),
  penalty: art(`
    <path d="M26 150V58h148v92"/>
    <path d="M26 82h148M26 106h148M26 130h148M54 58v92M82 58v92M110 58v92M138 58v92M166 58v92" opacity=".18"/>
    <path d="M14 150h172" opacity=".5"/>
    <circle cx="140" cy="80" r="13" fill="#0e100f"/><path d="M140 70l6 5-2 7h-8l-2-7z" fill="currentColor" stroke="none"/>
    <path d="M100 176c10-30 22-60 34-86" stroke-dasharray="3 6" opacity=".6"/>`),
  rps: art(`
    <circle cx="100" cy="58" r="26"/><circle cx="56" cy="134" r="26"/><circle cx="144" cy="134" r="26"/>
    <path d="M90 64c-2-8 4-16 12-15 7 1 10 8 8 14-2 5-8 7-13 6-4-1-6-2-7-5z" fill="currentColor" fill-opacity=".25"/>
    <path d="M46 122h16l6 6v18H46z"/><path d="M62 122v6h6" opacity=".6"/>
    <circle cx="136" cy="144" r="5"/><circle cx="152" cy="144" r="5"/><path d="M139 140l14-18M149 140l-14-18"/>
    <path d="M122 70l12 34M78 70l-12 34M76 148h44" opacity=".35" stroke-dasharray="4 5"/>`),
});

/* ---------- Nuit dorée : symboles des 5 rouleaux ---------- */
const letter = (t) => sym(`<text x="32" y="45" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="${t.length > 1 ? 30 : 36}" font-weight="600" fill="currentColor" stroke="none">${t}</text><path d="M14 52h36" opacity=".35"/>`);
export const SLOT5_SYMBOLS = {
  10: letter("10"),
  J: letter("V"),
  Q: letter("D"),
  K: letter("R"),
  A: letter("A"),
  bell: SLOT_SYMBOLS["🔔"],
  crown: sym('<path d="M10 46l-2-26 13 11 11-17 11 17 13-11-2 26z"/><path d="M10 52h44"/><circle cx="32" cy="36" r="3" fill="currentColor"/>'),
  gem: SLOT_SYMBOLS["💎"],
  W: sym('<circle cx="32" cy="32" r="20"/><path d="M32 4v6M32 54v6M4 32h6M54 32h6M12 12l4 4M48 48l4 4M12 52l4-4M48 16l4-4" opacity=".7"/><text x="32" y="40" text-anchor="middle" font-family="Bodoni Moda Variable, serif" font-size="22" font-weight="700" fill="currentColor" stroke="none">W</text>'),
  S: sym('<path d="M38 10a22 22 0 1016 34A18 18 0 0138 10z" fill="currentColor" fill-opacity=".2"/><path d="M48 14l2 5 5 1-4 3 1 5-4-3-5 3 1-5-4-3 5-1z" fill="currentColor" stroke="none"/>'),
};

/* ---------- Diamonds : sept gemmes, une forme par couleur ---------- */
const GEM_SHAPES = [
  '<path d="M16 12h32l10 14-26 28L6 26z"/><path d="M6 26h52M24 12l-5 14 13 28 13-28-5-14" opacity=".55"/>',
  '<rect x="12" y="12" width="40" height="40" rx="4"/><rect x="21" y="21" width="22" height="22" rx="2" opacity=".55"/><path d="M12 12l9 9M52 12l-9 9M12 52l9-9M52 52l-9-9" opacity=".55"/>',
  '<path d="M32 8l26 46H6z"/><path d="M32 22l12 24H20z" opacity=".55"/><path d="M32 8v14M6 54l14-8M58 54l-14-8" opacity=".55"/>',
  '<path d="M32 6l23 13v26L32 58 9 45V19z"/><path d="M32 18l12 7v14l-12 7-12-7V25z" opacity=".55"/>',
  '<path d="M32 4c14 12 20 20 20 28s-6 16-20 28C18 48 12 40 12 32s6-16 20-28z"/><path d="M32 4v56M12 32h40" opacity=".55"/>',
  '<path d="M32 56L10 32c-6-7-3-20 8-21 6 0 10 3 14 9 4-6 8-9 14-9 11 1 14 14 8 21z"/><path d="M32 20v36M18 22l14 34 14-34" opacity=".5"/>',
  '<path d="M22 6h20l14 14v24L42 58H22L8 44V20z"/><path d="M26 18h12l8 8v12l-8 8H26l-8-8V26z" opacity=".55"/>',
];
export const GEM_COLORS = ["#4f9a78", "#c0544a", "#5a7fbc", "#9a74b8", "#d1b06c", "#5fb0ae", "#e3dccb"];
export const gemSvg = (i, size = 56) =>
  `<svg class="gem-art" width="${size}" height="${size}" viewBox="0 0 64 64" fill="none" stroke="${GEM_COLORS[i]}" stroke-width="2.4" stroke-linejoin="round" aria-hidden="true" style="--gc:${GEM_COLORS[i]}"><g fill="${GEM_COLORS[i]}" fill-opacity=".16">${GEM_SHAPES[i]}</g></svg>`;

/* ---------- Pierre-feuille-ciseaux ---------- */
export const RPS_ART = {
  rock: svg('<path d="M10 42l5-15 12-11 16 1 11 12-2 15-13 7H21z"/><path d="M27 16l5 13-17-2M32 29h22M32 29l-7 20" opacity=".45"/>', { size: 56, vb: 64, sw: 2.4, cls: "rps-art" }),
  paper: svg('<path d="M16 8h24l10 10v38H16z"/><path d="M40 8v10h10"/><path d="M22 28h20M22 36h20M22 44h14" opacity=".55"/>', { size: 56, vb: 64, sw: 2.4, cls: "rps-art" }),
  scissors: svg('<circle cx="18" cy="46" r="7"/><circle cx="46" cy="46" r="7"/><path d="M23 41L46 8M41 41L18 8"/><circle cx="32" cy="26" r="1.6" fill="currentColor"/>', { size: 56, vb: 64, sw: 2.4, cls: "rps-art" }),
};
