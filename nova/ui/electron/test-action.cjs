// Banc d'essai de la boucle de confirmation.
//
// ⚠️ C'EST LE MECANISME QUI PROTEGE LA MACHINE. Il merite plus de severite
// que le reste du fichier.
//
// Une action de niveau 2 ou 3 revient de Nova Core avec une QUESTION, pas un
// resultat. C'est l'application qui retient ce qui est en attente, pose la
// question, et ne rappelle avec `confirme=true` que si l'utilisateur a
// vraiment dit oui.
//
// LE POINT QUI NE DOIT JAMAIS BOUGER
//
//     `confirme` vient de l'UTILISATEUR, jamais du modele.
//
// Si un modele pouvait remplir ce champ, tout le bareme de risque
// deviendrait un decor : on demanderait au renard s'il a le droit d'entrer
// dans le poulailler, et un modele de trois milliards de parametres
// repondrait oui.
const http = require('http');
const path = require('path');

const Module = require('module');
const chargerOrigine = Module._load;
Module._load = function (d) {
  if (d === './memory') return { contexte: () => '' };
  return chargerOrigine.apply(this, arguments);
};

// ── Un faux Nova Core qui note ce qu'on lui demande ──────────────────────
const recu = [];
let reponse = { etat: 'ignoree', message: '' };

const serveur = http.createServer((req, res) => {
  let corps = '';
  req.on('data', (c) => { corps += c; });
  req.on('end', () => {
    recu.push(JSON.parse(corps));
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify(reponse));
  });
});

let echecs = 0;
function verifier(intitule, condition) {
  console.log((condition ? '  ok   ' : '  ECHEC') + '  ' + intitule);
  if (!condition) echecs++;
}

serveur.listen(0, '127.0.0.1', async () => {
  process.env.NOVA_PORT = String(serveur.address().port);
  process.env.NOVA_HOST = '127.0.0.1';
  const { analyserEnFlux } = require(path.join(__dirname, 'brain.js'));

  const dire = async (phrase) => {
    let dit = '';
    await analyserEnFlux(phrase, 'tu', (p) => { dit += p; });
    return dit;
  };

  console.log('\nUne action simple s’exécute sans cérémonie');
  recu.length = 0;
  reponse = { etat: 'executee', message: 'Discord est ouverte.',
              outil: 'ouvrir_application', intention: 'ouvrir_application' };
  let dit = await dire('ouvre Discord');
  verifier('Nova annonce le résultat', dit.includes('Discord est ouverte'));
  verifier('aucune confirmation demandée', recu.length === 1 && recu[0].confirme === false);

  console.log('\nUne action irréversible demande d’abord');
  recu.length = 0;
  reponse = { etat: 'a_confirmer', message: 'Je m’apprête à eteindre_ordinateur. Je confirme ?',
              outil: 'eteindre_ordinateur', niveau: 3 };
  dit = await dire('éteins l’ordinateur');
  verifier('Nova pose la question', dit.includes('Je confirme ?'));
  verifier('rien n’a été exécuté', recu.length === 1 && recu[0].confirme === false);

  console.log('\n« oui » confirme — et SEULEMENT alors');
  reponse = { etat: 'executee', message: 'L’ordinateur va s’éteindre.',
              outil: 'eteindre_ordinateur', intention: 'arret_pc' };
  recu.length = 0;
  dit = await dire('oui');
  verifier('l’action est rappelée avec confirme=true',
    recu.length === 1 && recu[0].confirme === true);
  verifier('c’est bien la phrase d’origine qui est rejouée',
    recu[0].texte.includes('éteins'));
  verifier('Nova annonce le résultat', dit.includes('éteindre'));

  console.log('\n« non » annule, et rien ne part au serveur');
  reponse = { etat: 'a_confirmer', message: 'Je m’apprête à eteindre_ordinateur. Je confirme ?',
              outil: 'eteindre_ordinateur', niveau: 3 };
  await dire('éteins l’ordinateur');
  recu.length = 0;
  dit = await dire('non');
  verifier('aucun appel au serveur', recu.length === 0);
  verifier('Nova le dit', /ne fais rien/i.test(dit));

  console.log('\nUne réponse ambiguë n’exécute PAS');
  // « peut-être » n'est pas un accord. Une action irréversible ne se
  // déclenche pas sur une hésitation.
  reponse = { etat: 'a_confirmer', message: 'Je m’apprête à eteindre_ordinateur. Je confirme ?',
              outil: 'eteindre_ordinateur', niveau: 3 };
  await dire('éteins l’ordinateur');
  recu.length = 0;
  reponse = { etat: 'ignoree', message: '' };
  await dire('peut-être, je ne sais pas');
  const confirmations = recu.filter((r) => r.confirme === true);
  verifier('aucune confirmation envoyée', confirmations.length === 0);

  console.log('\nUne action en attente ne survit pas à un second tour');
  // Sinon un « oui » prononcé dix minutes plus tard, pour tout autre chose,
  // déclencherait l’extinction.
  recu.length = 0;
  dit = await dire('oui');
  verifier('« oui » isolé ne confirme rien',
    recu.filter((r) => r.confirme === true).length === 0);

  console.log('\nUn serveur injoignable ne bloque pas la conversation');
  serveur.close();
  await new Promise((r) => setTimeout(r, 50));
  let leve = false;
  try { await dire('bonjour'); } catch (e) { leve = true; }
  verifier('aucune exception propagée', !leve);

  console.log(echecs === 0
    ? '\n✓ tout est conforme\n'
    : '\n✗ ' + echecs + ' vérification(s) en échec\n');
  process.exit(echecs === 0 ? 0 : 1);
});
