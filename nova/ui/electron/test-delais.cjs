// Banc d'essai : un chemin mort ne se retente pas.
//
// CE QUE CE BANC PROTEGE
//
// Question « qu'est-ce qu'un trou noir », relevee en conditions reelles :
//
//     [NOVA] Echec du flux : delai depasse — Nova Core est-il lance ?
//     [NOVA] Repli sur l'appel classique
//     [NOVA] Echec de l'analyse IA : delai depasse — Nova Core est-il lance ?
//     [NOVA] Repli sur l'analyse locale
//     [NOVA] reponse du cerveau en 240737 ms
//
// Deux attentes de deux minutes vers la MEME adresse, dont la premiere avait
// deja prouve le silence. La seconde n'avait aucune chance et a coute autant
// que la premiere.
//
// On verifie ici deux choses :
//   1. qu'un echec de joignabilite est reconnu comme tel ;
//   2. qu'un echec de FORME (reponse illisible) ne l'est pas — celui-la
//      merite bien une seconde tentative, le modele peut mieux formuler.
const path = require('path');

const Module = require('module');
const chargerOrigine = Module._load;
Module._load = function (demande) {
  if (demande === './memory') {
    return { contexte: () => 'Mémoire vide : aucune information enregistrée.' };
  }
  return chargerOrigine.apply(this, arguments);
};

const brain = require(path.join(__dirname, 'brain.js'));
const { estInjoignable, DELAI_LOCAL_MS, DELAI_CLOUD_MS } = brain;

let echecs = 0;
function verifier(intitule, condition) {
  console.log((condition ? '  ok   ' : '  ECHEC') + '  ' + intitule);
  if (!condition) echecs++;
}

console.log('\nUn chemin mort est reconnu');

// Les messages exacts produits par brain.js et par Node.
const MORTS = [
  new Error('délai dépassé — Nova Core est-il lancé ? (uvicorn sur le port 8100)'),
  new Error('délai dépassé'),
  new Error('Nova Core a répondu vide — le service tourne-t-il ?'),
  new Error('connect ECONNREFUSED 127.0.0.1:8100'),
  new Error('socket hang up'),
  Object.assign(new Error('quelque chose'), { code: 'ECONNREFUSED' }),
  Object.assign(new Error('quelque chose'), { code: 'EHOSTUNREACH' }),
  Object.assign(new Error('quelque chose'), { code: 'ETIMEDOUT' }),
];
for (const err of MORTS) {
  verifier('« ' + (err.code || err.message.slice(0, 45)) + ' »', estInjoignable(err));
}

console.log('\nUn échec de forme n’est PAS un chemin mort');

// Ceux-la valent une seconde tentative : le serveur a repondu, mal.
const VIVANTS = [
  new Error('réponse illisible : Unexpected token } in JSON at position 42'),
  new Error('HTTP 500 — internal server error'),
  new Error('JSON valide mais sans champ « response »'),
];
for (const err of VIVANTS) {
  verifier('« ' + err.message.slice(0, 45) + ' »', !estInjoignable(err));
}
verifier('une erreur absente ne bloque rien', !estInjoignable(null));
verifier('un objet sans message ne casse pas', !estInjoignable({}));

console.log('\nLa hiérarchie des délais est respectée');

// Nova Core attend Ollama 90 s (NOVA_REQUEST_TIMEOUT). L'application doit
// attendre Nova Core PLUS longtemps, sinon elle abandonne avant d'avoir
// recu le vrai diagnostic — et rend le sien, qui est faux.
const DELAI_NOVA_CORE_MS = 90000;
verifier('application (' + DELAI_LOCAL_MS / 1000 + ' s) > Nova Core ('
  + DELAI_NOVA_CORE_MS / 1000 + ' s)', DELAI_LOCAL_MS > DELAI_NOVA_CORE_MS);
verifier('marge d’au moins 15 s pour transmettre l’erreur',
  DELAI_LOCAL_MS - DELAI_NOVA_CORE_MS >= 15000);
verifier('le délai cloud reste court (' + DELAI_CLOUD_MS / 1000 + ' s)',
  DELAI_CLOUD_MS <= 30000);

// Le coût de la faute, chiffré : ce que le banc empêche de revenir.
console.log('\nCoût évité');
console.log('  avant : ' + (2 * DELAI_LOCAL_MS / 1000) + ' s (deux attentes complètes)');
console.log('  après : ' + (DELAI_LOCAL_MS / 1000) + ' s au pire, une seule');

console.log(echecs === 0
  ? '\n✓ tout est conforme\n'
  : '\n✗ ' + echecs + ' vérification(s) en échec\n');
process.exit(echecs === 0 ? 0 : 1);
