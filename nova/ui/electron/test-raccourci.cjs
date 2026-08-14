// Banc d'essai du raccourci « reponse immediate ».
//
// POURQUOI CE RACCOURCI MERITE PLUS DE SEVERITE QUE LE RESTE
//
// Il repond en ZERO milliseconde, sans appeler le modele. C'est sa raison
// d'etre — et c'est aussi ce qui rend ses erreurs invisibles : une reponse
// fausse arrive instantanement, donc rien ne parait anormal. Un modele lent
// qui se trompe se remarque ; un raccourci rapide qui se trompe passe pour
// un bon fonctionnement.
//
// Releve en conditions reelles, sur une transcription bancale :
//
//     « quelle heure est a planete les plus grandes du systeme solaire »
//         -> reponse immediate (aucun modele appele) — 0 ms
//         -> « Il est 13 heures 10. »
//
// La question portait sur les planetes. Le mot « heure » venait d'une erreur
// de transcription, et le declencheur le cherchait N'IMPORTE OU dans la
// phrase. Il faut regarder ce qui le SUIT.
const path = require('path');

const Module = require('module');
const chargerOrigine = Module._load;
Module._load = function (demande) {
  if (demande === './memory') return { contexte: () => '' };
  return chargerOrigine.apply(this, arguments);
};

const { repondreImmediatement } = require(path.join(__dirname, 'brain.js'));

let echecs = 0;
function verifier(intitule, condition) {
  console.log((condition ? '  ok   ' : '  ECHEC') + '  ' + intitule);
  if (!condition) echecs++;
}

const intention = (phrase) => {
  const r = repondreImmediatement(phrase);
  return r ? r.intent : null;
};

console.log('\nLes vraies demandes d’heure sont interceptées');
for (const phrase of [
  'quelle heure est-il',
  'il est quelle heure',
  'quelle heure est-il maintenant',
  'tu peux me dire quelle heure il est s’il te plaît',
  'Nova, quelle heure est-il ?',
  'quelheure',   // Whisper colle et tronque les mots courts
]) {
  verifier('« ' + phrase + ' »', intention(phrase) === 'time_query');
}

console.log('\nUne phrase qui parle d’autre chose n’est PAS une demande d’heure');
for (const phrase of [
  // Le cas releve en conditions reelles.
  'quelle heure est à planète les plus grandes du système solaire',
  'quelle heure est le meilleur moment pour visiter le Japon',
  'combien d’heures de vol jusqu’à Tokyo',
  'donne-moi les planètes du système solaire',
  'qu’est-ce qu’un trou noir',
]) {
  verifier('« ' + phrase + ' »', intention(phrase) !== 'time_query');
}

console.log('\nLes demandes de date restent intactes');
for (const phrase of [
  'quel jour sommes-nous',
  'on est quel jour',
  'quelle est la date',
  'quelle date sommes-nous',
]) {
  verifier('« ' + phrase + ' »', intention(phrase) === 'date_query');
}

console.log('\nRien ne se déclenche sur une question ordinaire');
for (const phrase of [
  'raconte-moi une histoire',
  'qui était Charles Aznavour',
  'ouvre Discord',
  '',
]) {
  verifier('« ' + phrase + ' »', intention(phrase) === null);
}

console.log(echecs === 0
  ? '\n✓ tout est conforme\n'
  : '\n✗ ' + echecs + ' vérification(s) en échec\n');
process.exit(echecs === 0 ? 0 : 1);
