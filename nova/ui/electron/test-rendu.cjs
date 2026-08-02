// Banc d'essai de la cadence adaptative.
//
// Ce module intercepte requestAnimationFrame pour tout le renderer : une
// erreur ici fige l'interface ou casse une animation en cours. On le teste
// donc hors navigateur, avec un faux rAF qui compte les images.
const fs = require('fs');

// ── Faux navigateur ──
let horloge = 0;
const enAttente = [];               // rappels rAF natifs en attente
const minuteurs = new Map();
let idMinuteur = 1, idRaf = 1;

global.performance = { now: () => horloge };
global.setTimeout = (cb, ms) => { const id = idMinuteur++; minuteurs.set(id, { cb, quand: horloge + ms }); return id; };
global.clearTimeout = (id) => minuteurs.delete(id);
global.window = {
  requestAnimationFrame: (cb) => { const id = idRaf++; enAttente.push({ id, cb }); return id; },
  cancelAnimationFrame: (id) => { const i = enAttente.findIndex(f => f.id === id); if (i >= 0) enAttente.splice(i, 1); },
};
global.appState = 'IDLE';
global.console = console;

// Avance le temps par pas de 1 ms, en declenchant minuteurs puis images.
function avancer(ms) {
  for (let i = 0; i < ms; i++) {
    horloge++;
    for (const [id, m] of [...minuteurs]) {
      if (m.quand <= horloge) { minuteurs.delete(id); m.cb(); }
    }
    const prets = enAttente.splice(0, enAttente.length);
    for (const f of prets) f.cb(horloge);
  }
}

const src = fs.readFileSync(__dirname + '/rendu-econome.js', 'utf8');
new Function(src)();

// ── Boucle de rendu, comme celle de l'orbe ──
let images = 0;
function animer() { window.requestAnimationFrame(animer); images++; }

let echecs = 0;
const verifier = (nom, ok, detail) => {
  console.log((ok ? 'ok    ' : 'ECHEC ') + nom + (detail ? '   ' + detail : ''));
  if (!ok) echecs++;
};

function mesurer(etat, secondes) {
  // Chaque mesure part d'un etat propre : sans ce nettoyage, la boucle de
  // la mesure precedente continue de tourner et les images s'additionnent.
  // C'est ce qui a fait echouer la premiere version de ce banc — 146 img/s
  // annonces pour une cadence visee a 30.
  enAttente.length = 0;
  minuteurs.clear();
  global.appState = etat;
  images = 0;
  animer();
  avancer(secondes * 1000);
  enAttente.length = 0;
  minuteurs.clear();
  return images / secondes;
}

console.log('\n── Images par seconde, par état ───────────────');
const attendus = { IDLE: 12, LISTENING: 20, THINKING: 4, SPEAKING: 12, INTRO: 30 };
for (const [etat, vise] of Object.entries(attendus)) {
  const obtenu = mesurer(etat, 4);
  console.log('  ' + etat.padEnd(11) + Math.round(obtenu) + ' img/s   (visé ' + vise + ')');
  verifier(etat + ' respecte sa cadence', Math.abs(obtenu - vise) <= 2);
}

console.log();
// Le point qui compte : combien d'images en moins pendant qu'elle reflechit.
const veille = mesurer('IDLE', 4), reflexion = mesurer('THINKING', 4);
console.log('  pendant THINKING : ' + Math.round((1 - reflexion / 60) * 100)
  + ' % d’images en moins qu’à 60 img/s — autant de GPU rendu au modèle\n');
verifier('la réflexion consomme au moins 10x moins qu’un rendu libre', reflexion <= 6);

// L'annulation doit fonctionner, sinon une animation continue en fond.
global.appState = 'THINKING';
let appele = false;
const id = window.requestAnimationFrame(() => { appele = true; });
window.cancelAnimationFrame(id);
avancer(1000);
verifier('une image différée peut être annulée', !appele);

// Un identifiant natif inconnu ne doit pas etre avale par notre table.
let nat = false;
const idNatif = global.window.requestAnimationFrame(() => { nat = true; });
window.cancelAnimationFrame(idNatif);
avancer(100);
verifier('l’annulation native reste fonctionnelle', !nat);

process.exit(echecs ? 1 : 0);
