// Essai de bout en bout de la parole en flux, contre un faux Nova Core.
// Verifie ce qui compte : NOVA parle-t-elle AVANT la fin de la generation ?
const http = require('http');
const path = require('path');
const os = require('os');

const REPONSE = "Un trou noir est une région de l'espace où la gravité est si intense que rien ne s'en échappe. Même la lumière y reste piégée pour toujours.";
const OBJET = JSON.stringify({ response: REPONSE, memory: { shouldRemember: true, category: 'Study', title: 'trou noir', content: 'Hugo s’intéresse aux trous noirs' } });

// Faux Nova Core : emet l'objet JSON caractere par caractere, 12 ms chacun,
// pour reproduire un modele local lent.
const serveur = http.createServer((req, res) => {
  res.writeHead(200, { 'content-type': 'text/event-stream' });
  const env = (nom, charge) => res.write('event: ' + nom + '\ndata: ' + JSON.stringify(charge) + '\n\n');
  env('message_start', { type: 'message_start' });
  env('content_block_start', { type: 'content_block_start', index: 0 });
  let i = 0;
  const iv = setInterval(() => {
    if (i >= OBJET.length) {
      clearInterval(iv);
      env('content_block_stop', { type: 'content_block_stop', index: 0 });
      env('message_stop', { type: 'message_stop' });
      return res.end();
    }
    env('content_block_delta', { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: OBJET[i] } });
    i++;
  }, 12);
});

serveur.listen(8199, async () => {
  process.env.NOVA_PORT = '8199';
  const brain = require(process.env.NOVA_BRAIN_JS || './brain');
  const memory = require(process.env.NOVA_MEMORY_JS || './memory');
  memory.init(path.join(os.tmpdir(), 'nova-essai-' + Date.now()));
  brain.loadKey('', '');

  const T0 = Date.now();
  const phrases = [];
  const analyse = await brain.analyserEnFlux('Explique-moi ce qu’est un trou noir', 'tu', (p) => {
    phrases.push({ ms: Date.now() - T0, texte: p });
  });
  const total = Date.now() - T0;

  console.log('\n── Résultat ─────────────────────────────────');
  for (const p of phrases) console.log('  ' + String(p.ms).padStart(5) + ' ms | ' + p.texte);
  console.log('  ' + String(total).padStart(5) + ' ms | (fin de la génération)');
  console.log();

  let echecs = 0;
  const verifier = (nom, ok) => { console.log((ok ? 'ok    ' : 'ECHEC ') + nom); if (!ok) echecs++; };

  verifier('deux phrases émises', phrases.length === 2);
  verifier('texte reconstitué exact', analyse.response === REPONSE);
  verifier('mémoire transmise', analyse.memory && analyse.memory.shouldRemember === true);
  verifier('catégorie conservée', analyse.memory.category === 'Study');
  verifier('la 1re phrase précède la fin', phrases.length > 0 && phrases[0].ms < total);

  const avance = total - phrases[0].ms;
  verifier('avance > 40 % de la durée totale', avance / total > 0.4);
  console.log('\n  elle commence à parler ' + avance + ' ms avant la fin — ' + Math.round(avance / total * 100) + ' % de silence en moins');

  serveur.close();
  process.exit(echecs ? 1 : 0);
});
