// Banc d'essai des doublons.
//
// ⚠️ CE FICHIER GARDE LA PANNE LA PLUS DÉROUTANTE DE TOUTES.
//
// Relevé sur la machine réelle, dans cet ordre :
//
//     [NOVA/rendu] cadence adaptative…      ← deux fois
//     [NOVA/flux]  parole en flux active…   ← deux fois
//     Request sent to ElevenLabs (88 car.)  ← deux fois, MÊME texte
//     PLAYBACK BLOCKED: AbortError — play() interrupted by pause()
//     [VOIX] lecture échouée -> repli voix système
//
// L'utilisateur a entendu « une deuxième voix qui répond en plus de celle de
// Nova ». Ce n'était pas un défaut de synthèse : c'était deux fois le même
// module, collé une fois à la main et une fois par `make ui`.
//
// POURQUOI LE DOUBLON COÛTE PLUS CHER QU'UNE ABSENCE
//
// Un module absent ne fait rien — on le voit tout de suite. Un module
// chargé deux fois fait tout DEUX FOIS : deux enveloppes autour de
// `requestAnimationFrame` (donc deux fois le travail qu'on voulait
// supprimer), deux requêtes de synthèse, deux lectures qui s'annulent. La
// panne ressemble alors à n'importe quoi sauf à sa cause.
//
// On ne peut pas empêcher quelqu'un de coller deux fois. On peut faire que
// ça ne coûte rien — c'est ce que ce banc vérifie.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let echecs = 0;
function verifier(intitule, condition) {
  console.log((condition ? '  ok   ' : '  ECHEC') + '  ' + intitule);
  if (!condition) echecs++;
}

function charger(fichier, contexte, fois) {
  const source = fs.readFileSync(path.join(__dirname, fichier), 'utf8');
  for (let i = 0; i < fois; i++) vm.runInContext(source, contexte);
}

function bureau(extra = {}) {
  const journal = [];
  const fenetre = {
    requestAnimationFrame: (f) => { fenetre._rafs++; return 1; },
    cancelAnimationFrame: () => {},
    _rafs: 0,
  };
  const contexte = vm.createContext(Object.assign({
    window: fenetre,
    console: { info: (m) => journal.push(String(m)), warn: () => {}, error: () => {} },
    performance: { now: () => 0 },
    setTimeout: () => 1,
    clearTimeout: () => {},
    appState: 'IDLE',
    document: { addEventListener: () => {} },
  }, extra));
  contexte.globalThis = contexte;
  return { contexte, journal, fenetre };
}

// ── rendu-econome : deux emballages de rAF valent moins que zéro ─────────
console.log('\nLe rendu économe ne s’installe qu’une fois');
{
  const { contexte, journal, fenetre } = bureau();
  const rafOrigine = fenetre.requestAnimationFrame;

  charger('rendu-econome.js', contexte, 1);
  const apresUn = fenetre.requestAnimationFrame;
  verifier('la première copie enveloppe bien rAF', apresUn !== rafOrigine);

  charger('rendu-econome.js', contexte, 1);
  verifier('la seconde copie n’enveloppe PAS une deuxième fois',
    fenetre.requestAnimationFrame === apresUn);
  verifier('et elle le dit', journal.some((l) => /déjà actif/.test(l)));
  verifier('une seule annonce d’activation',
    journal.filter((l) => /cadence adaptative/.test(l)).length === 1);
}

// ── parole-en-flux : la deuxième voix ────────────────────────────────────
console.log('\nLa parole en flux ne double pas les phrases');
{
  const envois = [];
  const { contexte, journal } = bureau({
    traiterDemande: (t) => { envois.push(t); return null; },
    // `isDesktopApp` est lu par l'enveloppe. Sans lui, une ReferenceError
    // dans une fonction `async` devient une promesse rejetée en silence —
    // et le banc mesurait alors ce silence au lieu du doublon.
    isDesktopApp: false,
    setAppState: () => {},
    adresse: 'tu',
  });

  charger('parole-en-flux.js', contexte, 3);   // trois fois, exprès
  verifier('une seule annonce d’activation malgré trois copies',
    journal.filter((l) => /parole en flux active/.test(l)).length === 1);
  verifier('les copies surnuméraires le disent',
    journal.filter((l) => /déjà actif/.test(l)).length === 2);

  contexte.traiterDemande('bonjour');
  verifier('une phrase ne part qu’une fois, pas trois', envois.length === 1);
}

// ── reveil-vocal : deux micros ouverts ──────────────────────────────────
console.log('\nLe réveil vocal n’ouvre pas deux écoutes');
{
  const { contexte, journal } = bureau({
    navigator: { mediaDevices: { getUserMedia: () => Promise.reject(new Error('pas de micro')) } },
    fetch: () => Promise.reject(new Error('hors ligne')),
    AudioContext: function () { throw new Error('pas d’audio'); },
    addEventListener: () => {},
  });

  // Chaque chargement dans son propre `try` : sans micro, le premier lève, et
  // un `try` commun empêcherait le second de s'exécuter — le banc mesurerait
  // alors sa propre erreur au lieu du garde-fou.
  for (let i = 0; i < 2; i++) {
    try { charger('reveil-vocal.js', contexte, 1); } catch (e) { /* pas de micro ici */ }
  }
  verifier('la seconde copie se retire',
    journal.filter((l) => /déjà actif/.test(l)).length === 1);
}

// ── Le drapeau doit être posé sur `window`, pas sur une portée locale ────
console.log('\nLe garde-fou survit à l’ordre de collage');
{
  const { contexte, fenetre } = bureau({ traiterDemande: () => {} });
  charger('rendu-econome.js', contexte, 1);
  charger('parole-en-flux.js', contexte, 1);
  verifier('rendu-econome laisse sa marque', fenetre.__novaRenduEconome === true);
  verifier('parole-en-flux laisse la sienne', fenetre.__novaParoleEnFlux === true);
  verifier('les deux marques sont distinctes',
    Object.keys(fenetre).filter((c) => c.startsWith('__nova')).length === 2);
}

console.log(echecs === 0
  ? '\n✓ un doublon ne coûte plus rien\n'
  : '\n✗ ' + echecs + ' vérification(s) en échec\n');
process.exit(echecs === 0 ? 0 : 1);
