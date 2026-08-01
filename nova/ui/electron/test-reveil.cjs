// Banc d'essai du decoupage par la parole. On simule des trames audio et on
// verifie que la segmentation produit UN extrait, de la bonne duree, avec un
// en-tete WAV correct — sans micro, sans Electron, sans Nova Core.
const fs = require('fs');

const src = fs.readFileSync(__dirname + '/reveil-vocal.js', 'utf8');
const debut = src.indexOf('(function reveilLocal() {') + '(function reveilLocal() {'.length;
const fin = src.lastIndexOf('})();');
const corps = src.slice(debut, fin);

globalThis.uiMode = 'veille';
globalThis.appState = 'IDLE';
globalThis.wakeOn = false;
globalThis.wakeChipEl = null;
globalThis.wakeToConversation = () => {};
globalThis.cycleVocal = async () => {};
globalThis.traiterDemande = async () => {};
globalThis.navigator = { mediaDevices: { getUserMedia: async () => { throw new Error('pas de micro'); } } };
globalThis.window = {};
globalThis.fetch = async () => ({ ok: true, json: async () => ({ wake: false, text: '', commande: '' }) });
globalThis.FormData = class { append() {} };
globalThis.Blob = class { constructor(parts) { this.parts = parts; this.size = parts[0].byteLength; } };

const envois = [];
const exporter = '\n; module.exports = { surTrame, versWav, demarrer: () => { actif = true; }, envoiTest: analyser };';
const mod = { exports: {} };
// On remplace `analyser` par un espion, en gardant le WAV produit.
const corpsEspion = corps.replace(
  'async function analyser(blob, ms) {',
  'async function analyser(blob, ms) { envois.push({ blob, ms }); return;'
);
new Function('module', 'envois', corpsEspion + exporter)(mod, envois);
const { surTrame, versWav, demarrer } = mod.exports;
demarrer();

const TAILLE = 2048, ECHANT = 16000;
const trame = (amplitude) => {
  const d = new Float32Array(TAILLE);
  for (let i = 0; i < TAILLE; i++) d[i] = (Math.random() * 2 - 1) * amplitude;
  return { inputBuffer: { getChannelData: () => d } };
};
const MS = TAILLE / ECHANT * 1000;

// Scenario : 1 s de silence, 1,5 s de parole, 1,2 s de silence.
const envoyer = (amplitude, ms) => { for (let i = 0; i < Math.round(ms / MS); i++) surTrame(trame(amplitude)); };
envoyer(0.002, 1000);
envoyer(0.20,  1500);
envoyer(0.002, 1200);

console.log('extraits envoyes :', envois.length);
if (envois.length !== 1) { console.error('ECHEC : on attendait exactement 1 extrait'); process.exit(1); }

const { blob, ms } = envois[0];
console.log('duree annoncee   :', ms, 'ms');
// Pre-roll 400 + parole 1500 + silence de fin 700 = ~2600 ms
if (ms < 2200 || ms > 3000) { console.error('ECHEC : duree hors des bornes attendues (2200-3000)'); process.exit(1); }

const vue = new DataView(blob.parts[0]);
const lire = (p, n) => String.fromCharCode(...[...Array(n)].map((_, i) => vue.getUint8(p + i)));
console.log('en-tete          :', lire(0, 4) + '/' + lire(8, 4) + '/' + lire(12, 4) + '/' + lire(36, 4));
console.log('taux             :', vue.getUint32(24, true), 'Hz');
console.log('canaux / bits    :', vue.getUint16(22, true), '/', vue.getUint16(34, true));
const octetsData = vue.getUint32(40, true);
console.log('octets de donnees:', octetsData, '=', (octetsData / 2 / ECHANT * 1000).toFixed(0), 'ms de son');

if (lire(0, 4) !== 'RIFF' || lire(8, 4) !== 'WAVE' || lire(36, 4) !== 'data') { console.error('ECHEC : en-tete WAV invalide'); process.exit(1); }
if (vue.getUint32(24, true) !== ECHANT) { console.error('ECHEC : mauvais taux'); process.exit(1); }
if (blob.parts[0].byteLength !== 44 + octetsData) { console.error('ECHEC : taille incoherente'); process.exit(1); }

// Un bruit bref ne doit rien declencher.
envois.length = 0;
envoyer(0.002, 500); envoyer(0.30, 120); envoyer(0.002, 1200);
console.log('\nbruit bref -> extraits :', envois.length, envois.length === 0 ? '(ignore, correct)' : '(ECHEC)');
if (envois.length !== 0) process.exit(1);

// Le silence seul ne doit jamais rien envoyer.
envois.length = 0;
envoyer(0.002, 8000);
console.log('silence 8 s -> extraits :', envois.length, envois.length === 0 ? '(rien, correct)' : '(ECHEC)');
if (envois.length !== 0) process.exit(1);

// Nova occupee (elle reflechit ou elle parle) : l'ecoute doit se taire.
// Sans ce garde-fou, Whisper tourne pendant la generation, sur le meme
// processeur — et une reponse de 94 caracteres prend 30 secondes.
envois.length = 0;
globalThis.appState = 'THINKING';
envoyer(0.002, 500); envoyer(0.20, 1500); envoyer(0.002, 1200);
console.log('pendant THINKING -> extraits :', envois.length, envois.length === 0 ? '(silence, correct)' : '(ECHEC)');
if (envois.length !== 0) process.exit(1);

globalThis.appState = 'SPEAKING';
envoyer(0.002, 500); envoyer(0.20, 1500); envoyer(0.002, 1200);
console.log('pendant SPEAKING -> extraits :', envois.length, envois.length === 0 ? '(silence, correct)' : '(ECHEC)');
if (envois.length !== 0) process.exit(1);

globalThis.appState = 'IDLE';
envoyer(0.002, 500); envoyer(0.20, 1500); envoyer(0.002, 1200);
console.log('retour en IDLE  -> extraits :', envois.length, envois.length === 1 ? '(reprise, correct)' : '(ECHEC)');
if (envois.length !== 1) process.exit(1);

console.log('\nTOUT PASSE');
