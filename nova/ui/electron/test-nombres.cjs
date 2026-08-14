// Banc d'essai : les nombres tels qu'ils sont ENTENDUS.
//
// LE DEFAUT
//
// Le modele ecrit les grands nombres avec un separateur de milliers, parce
// que c'est la typographie francaise correcte :
//
//     « La Terre mesure environ 12 742 kilometres de diametre. »
//
// La synthese vocale y voit DEUX nombres et prononce « douze, sept cent
// quarante-deux ». Le texte affiche est juste ; ce qui sort du haut-parleur
// est faux. Aucun journal ne le signale — seule l'oreille le detecte.
//
// CE QU'IL NE FAUT SURTOUT PAS CASSER
//
// « 2024 100 personnes » n'est pas un nombre a separateur : ce sont deux
// nombres voisins. Recoller a l'aveugle donnerait « deux millions vingt-quatre
// mille cent », ce qui serait pire que le defaut d'origine.
const fs = require('fs');

// Le module est une IIFE qui s'arrete si l'application n'est pas la. On en
// extrait le corps, comme test-reveil.cjs, pour atteindre la fonction seule.
const src = fs.readFileSync(__dirname + '/parole-en-flux.js', 'utf8');
const ouverture = '(function paroleEnFlux() {';
const corps = src.slice(
  src.indexOf(ouverture) + ouverture.length,
  src.lastIndexOf('})();'),
);

// Doublures minimales du navigateur : le module s'installe au chargement,
// et on ne teste ici qu'une fonction pure au milieu.
globalThis.traiterDemande = async () => {};
globalThis.window = {};
globalThis.msgEl = { classList: { add() {}, remove() {} } };
globalThis.setAppState = () => {};
globalThis.appState = 'IDLE';
globalThis.speak = async () => true;
globalThis.typewriter = async () => {};
globalThis.performance = { now: () => 0 };

const mod = { exports: {} };
new Function('module', corps + '\n; module.exports = { pourLaVoix };')(mod);
const { pourLaVoix } = mod.exports;

let echecs = 0;
function verifier(entree, attendu) {
  const obtenu = pourLaVoix(entree);
  const ok = obtenu === attendu;
  console.log((ok ? '  ok   ' : '  ECHEC') + '  ' + JSON.stringify(entree)
    + (ok ? '' : '\n           attendu ' + JSON.stringify(attendu)
                + '\n           obtenu  ' + JSON.stringify(obtenu)));
  if (!ok) echecs++;
}

console.log('\nLes séparateurs de milliers sont recollés');
verifier('La Terre mesure environ 12 742 kilomètres de diamètre.',
         'La Terre mesure environ 12742 kilomètres de diamètre.');
verifier('un diamètre de environ 142 984 kilomètres',
         'un diamètre de environ 142984 kilomètres');
verifier('1 234 567 habitants', '1234567 habitants');
verifier('10 000 euros', '10000 euros');

console.log('\nTous les espaces typographiques comptent');
// Le modèle peut produire l'espace fine insécable (U+202F), l'insécable
// (U+00A0) ou la fine (U+2009) : elles sont invisibles et se ressemblent
// toutes à l'écran. En rater une, c'est retrouver le défaut sans comprendre.
verifier('12 742 km', '12742 km');
verifier('12 742 km', '12742 km');
verifier('12 742 km', '12742 km');

console.log('\nCe qui n’est PAS un séparateur reste intact');
verifier('2024 100 personnes', '2024 100 personnes');
verifier('Il est 13 heures 10.', 'Il est 13 heures 10.');
verifier('en 1789 la Révolution', 'en 1789 la Révolution');
verifier('12 pommes et 3 poires', '12 pommes et 3 poires');
verifier('page 12 ligne 742', 'page 12 ligne 742');

console.log('\nRien ne casse sur les cas limites');
verifier('', '');
verifier('Mercure, Vénus, Terre, Mars.', 'Mercure, Vénus, Terre, Mars.');
console.log('  ok     null et undefined ne lèvent pas');
if (pourLaVoix(null) !== '' || pourLaVoix(undefined) !== '') { echecs++; }

console.log(echecs === 0
  ? '\n✓ tout est conforme\n'
  : '\n✗ ' + echecs + ' vérification(s) en échec\n');
process.exit(echecs === 0 ? 0 : 1);
