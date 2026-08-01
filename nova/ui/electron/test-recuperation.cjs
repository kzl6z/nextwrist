// Retrouver la reponse quelle que soit la forme inventee par le modele.
//
// Cas REEL releve dans les logs de la machine. Le contrat disait :
//     {"response":"tes deux phrases"}
// llama3.2:3b a pris le texte d'exemple pour le NOM du champ :
//     { "tes deux phrases": { "Un trou noir est…": "C'est une…" } }
// La reponse etait la, complete et juste, rangee la ou personne ne la
// cherchait. NOVA a dit « Entendu. »
const fs = require('fs');

const src = fs.readFileSync(__dirname + '/brain.js', 'utf8');
const debut = src.indexOf('const LONGUEUR_PHRASE');
const fin = src.indexOf("// ── Appel à l'IA, EN FLUX");
if (debut < 0 || fin < 0) { console.error('brain.js : bloc de récupération introuvable'); process.exit(1); }
const mod = { exports: {} };
new Function('module', src.slice(debut, fin) + '; module.exports = { recupererPhrases };')(mod);
const { recupererPhrases } = mod.exports;

let echecs = 0;
const verifier = (nom, ok, obtenu) => {
  console.log((ok ? 'ok    ' : 'ECHEC ') + nom + (ok ? '' : '\n        obtenu : ' + JSON.stringify(obtenu)));
  if (!ok) echecs++;
};

// ── Le cas reel ──
const REEL = {
  'tes deux phrases': {
    'Un trou noir est une région du vide spatial où la gravité est si forte que rien ne peut y échapper.':
      "C'est une des régions les plus mystérieuses de l'univers, avec un champ gravitationnel qui attire tout vers son centre sans jamais laisser échapper quelque chose.",
  },
};
const recupere = recupererPhrases(REEL);
verifier('le cas réel est intégralement récupéré',
  recupere.startsWith('Un trou noir est une région du vide spatial')
  && recupere.includes('mystérieuses de l’univers'.replace('’', "'")),
  recupere);
verifier('les deux phrases sont dans l’ordre du discours',
  recupere.indexOf('Un trou noir') < recupere.indexOf("C'est une des régions"), recupere);

// ── Autres formes plausibles ──
verifier('clé anglaise', recupererPhrases(
  { answer: 'Un trou noir est une région où la gravité est si forte que rien ne s en echappe.' }).length > 30);
verifier('clé française', recupererPhrases(
  { reponse: 'Un trou noir est une région où la gravité est si forte que rien ne s en echappe.' }).length > 30);
verifier('tableau de phrases', recupererPhrases(
  { phrases: ['Un trou noir est une région très dense de l espace.',
              'Même la lumière y reste piégée pour toujours.'] }).split('.').length === 3);
verifier('imbrication profonde', recupererPhrases(
  { a: { b: { c: 'Un trou noir est une région où la gravité est si forte que rien ne s en echappe.' } } }).length > 30);

// ── Ce qu'il ne faut PAS récupérer ──
// Sans seuil de longueur, on prononcerait « query goal Research ».
verifier('des noms de champ ne sont pas une réponse',
  recupererPhrases({ intent: 'query', goal: 'x', workspaceType: 'Research' }) === '');
verifier('un objet vide ne produit rien', recupererPhrases({}) === '');
verifier('null ne casse pas', recupererPhrases(null) === '');

process.exit(echecs ? 1 : 0);
