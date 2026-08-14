// Banc d'essai de la consigne donnee au modele.
//
// CE QU'IL PROTEGE, ET POURQUOI CA NE SE VOIT PAS A LA LECTURE
//
// La consigne se terminait par ces deux lignes, placees juste apres le bloc
// de memoire personnelle :
//
//     Si la demande porte sur ces informations, reponds A PARTIR d'elles.
//     Si tu ne sais pas, dis-le en une phrase. N'invente jamais.
//
// Chaque phrase est raisonnable. Ensemble, et a cet endroit, elles disent a
// un modele de trois milliards de parametres : « ton savoir, c'est ce bloc ».
// Releve en conditions reelles, question « donne-moi les planetes de notre
// systeme solaire » :
//
//     « Merci, mais je ne connais pas les planetes de notre systeme solaire.
//       Je peux citer les sources qui en parlent, mais je ne peux pas
//       fournir les informations. »
//
// Aucune erreur, aucune lenteur, aucun journal : juste une assistante
// devenue inutile. C'est le pire mode de panne, parce qu'on l'attribue au
// modele — « il est trop petit » — alors qu'on le lui a demande.
//
// La regle a tenir : la memoire BORNE ce que NOVA affirme sur Hugo, elle ne
// borne PAS ce qu'elle sait du monde.
const path = require('path');

const Module = require('module');
const chargerOrigine = Module._load;
Module._load = function (demande) {
  if (demande === './memory') {
    return { contexte: () => 'Hugo Kozlowski, 17 ans. Frere : Adam. Mere : Berangere.' };
  }
  return chargerOrigine.apply(this, arguments);
};

const { systemPrompt } = require(path.join(__dirname, 'brain.js'));

let echecs = 0;
function verifier(intitule, condition) {
  console.log((condition ? '  ok   ' : '  ECHEC') + '  ' + intitule);
  if (!condition) echecs++;
}

const consigne = systemPrompt('tu');
// Espaces normalisés AVANT de chercher : la consigne est écrite sur
// plusieurs lignes, et une règle coupée par un retour à la ligne est la même
// règle. Sans ça, reformater le texte casserait le banc d'essai sans que
// rien n'ait changé — un test qui crie pour de la mise en page finit ignoré.
const sansAccents = consigne
  .normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/\s+/g, ' ')
  .toLowerCase();

console.log('\nLa mémoire ne doit pas devenir la limite du savoir');
verifier('la consigne dit explicitement que la mémoire ne limite pas',
  /ne limitent? (en rien|pas)/.test(sansAccents));   // « limite » ou « limitent »
verifier('la culture générale est autorisée nommément',
  sansAccents.includes('culture generale'));
verifier('refuser une question générale est interdit',
  /ne refuse jamais/.test(sansAccents));

console.log('\nLa mémoire reste la seule source sur les faits personnels');
verifier('les faits personnels ne viennent que de la mémoire',
  /uniquement depuis eux|uniquement depuis la memoire/.test(sansAccents));
verifier('inventer un fait personnel reste interdit',
  /n'invente jamais/.test(sansAccents));

// ── UN SEUL PROPRIETAIRE DE LA MEMOIRE ──────────────────────────────────
//
// Deux systemes l'injectaient dans le meme prompt : `memory.js` cote
// application, et les faits PostgreSQL cote Nova Core. Nova relisait donc
// qui est Hugo deux fois, a chaque question, dans deux formats.
//
// Ce n'est pas qu'une depense. Quand les deux blocs se contredisent — un
// fait corrige d'un cote, pas de l'autre — rien ne dit lequel fait foi, et
// le modele tranche au hasard. Une memoire qui se contredit est pire
// qu'une memoire absente.
console.log('\nEn mode local, Nova Core est le seul propriétaire');
verifier('aucun bloc <memoire> envoyé par l’application',
  !consigne.includes('<memoire>'));
verifier('la mémoire de l’application n’est pas recopiée',
  !consigne.includes('Adam'));
verifier('le modèle est prévenu que les faits arrivent',
  /faits connus sur hugo sont fournis/.test(sansAccents));

console.log('\nLa taille ne dépend plus de la mémoire');
// C'est la propriete qui compte sur dix ans : une memoire qui grossit ne
// doit pas ralentir CHAQUE question (risque R13).
const avecPlus = systemPrompt('tu');
verifier('la consigne locale est de taille constante',
  avecPlus.length === consigne.length);

console.log('\nLe contrat de forme tient toujours');
verifier('la clé JSON est nommée explicitement', /clé[^.]*response|response/.test(consigne));
verifier('deux phrases demandées', /DEUX phrases/.test(consigne));

// Le budget : cette consigne part a CHAQUE question, et le temps avant le
// premier mot croit avec sa taille.
console.log('\nBudget');
console.log('  taille de la consigne : ' + consigne.length + ' caractères');
verifier('la consigne reste sous 2000 caractères', consigne.length < 2000);

console.log(echecs === 0
  ? '\n✓ tout est conforme\n'
  : '\n✗ ' + echecs + ' vérification(s) en échec\n');
process.exit(echecs === 0 ? 0 : 1);
