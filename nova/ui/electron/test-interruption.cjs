// Banc d'essai de l'interruption cote fenetre.
//
// ⚠️ NOVA CORE DETECTE « ATTENDS ». ELLE NE PEUT PAS L'APPLIQUER.
//
// Elle rend un WAV, et c'est cette fenetre qui le joue. Releve en conditions
// reelles : on dit « attends », le journal de Core montre bien la coupure, et
// Nova continue de parler jusqu'au bout. Elle avait cesse d'ecrire, mais le
// son etait deja parti.
//
// Ce banc verifie les deux sens : le son s'arrete quand Core le demande, et
// il ne s'arrete PAS quand elle ne le demande pas.
const fs = require('fs');
const assert = require('assert');

const src = fs.readFileSync(__dirname + '/reveil-vocal.js', 'utf8');
const debut = src.indexOf('(function reveilLocal() {') + '(function reveilLocal() {'.length;
const fin = src.lastIndexOf('})();');
const corps = src.slice(debut, fin);

let reponse = { wake: false, text: '', commande: '' };
const sons = [];
const faireUnSon = (enCours) => {
  const son = { paused: !enCours, currentTime: 12.5, pause() { this.paused = true; } };
  sons.push(son);
  return son;
};

globalThis.uiMode = 'veille';
globalThis.appState = 'IDLE';
globalThis.wakeOn = false;
globalThis.wakeChipEl = null;
globalThis.wakeToConversation = () => {};
globalThis.cycleVocal = async () => {};
globalThis.traiterDemande = async () => {};
globalThis.navigator = { mediaDevices: { getUserMedia: async () => { throw new Error('pas de micro'); } } };
let annulee = false;
globalThis.window = { speechSynthesis: { cancel: () => { annulee = true; } } };
globalThis.document = { querySelectorAll: () => sons };
globalThis.fetch = async () => ({ ok: true, json: async () => reponse });
globalThis.FormData = class { append() {} };
globalThis.Blob = class { constructor(parts) { this.parts = parts; this.size = parts[0].byteLength; } };

const mod = { exports: {} };
new Function('module', corps + '\n; module.exports = { analyser };')(mod);
const { analyser } = mod.exports;

(async () => {
  // ── Core demande la coupure : tout ce qui sonne s'arrete ──────────────
  sons.length = 0;
  const joue = faireUnSon(true);
  const deja = faireUnSon(false);
  deja.currentTime = 7;
  reponse = { wake: false, text: 'attends', commande: '', interrompre: true };
  await analyser({}, 500);

  assert.strictEqual(joue.paused, true, 'la lecture en cours devait etre arretee');
  assert.strictEqual(joue.currentTime, 0, 'la lecture arretee doit repartir de zero');
  assert.strictEqual(annulee, true, 'la voix de repli du systeme devait etre annulee');
  // ⚠️ ON NE TOUCHE PAS A CE QUI NE JOUE PAS.
  //
  // Remettre a zero un element deja en pause ferait repartir du debut la
  // reponse suivante, qui reutilise le meme element.
  assert.strictEqual(deja.currentTime, 7, 'un element en pause ne doit pas etre remis a zero');

  // ── Core ne demande rien : le son continue ────────────────────────────
  sons.length = 0;
  annulee = false;
  const tranquille = faireUnSon(true);
  reponse = { wake: false, text: 'il fait beau', commande: '' };
  await analyser({}, 500);

  assert.strictEqual(tranquille.paused, false, 'le son a ete coupe sans que Core le demande');
  assert.strictEqual(annulee, false, 'la voix du systeme a ete annulee sans raison');

  // ── Un DOM qui refuse ne doit pas emporter le reveil ──────────────────
  //
  // ⚠️ « NE DOIT PAS LEVER » NE PROTEGEAIT RIEN.
  //
  // `analyser` a son propre `catch` autour de tout : l'exception etait deja
  // avalee, et le banc restait vert meme sans l'enveloppe. Ce qui se casse
  // vraiment, c'est la SUITE — `res.wake` n'est jamais lu, et la phrase pour
  // laquelle on a coupe est perdue.
  let reveille = false;
  globalThis.wakeToConversation = () => { reveille = true; };
  globalThis.document = { querySelectorAll: () => { throw new Error('pas de DOM'); } };
  reponse = { wake: true, text: 'attends, ouvre le deuxieme',
              commande: 'ouvre le deuxieme', interrompre: true };
  await analyser({}, 500);

  assert.strictEqual(reveille, true, 'le reveil a ete perdu avec la coupure ratee');

  console.log('OK — interruption cote fenetre');
})();
