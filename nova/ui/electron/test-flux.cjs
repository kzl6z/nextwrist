// Banc d'essai de la parole en flux, contre un faux Nova Core.
//
// Il ne suffit pas de verifier que le flux « marche » : il faut verifier
// qu'il fait gagner du temps, et lequel. On mesure donc deux choses que
// l'on confond facilement :
//
//   — le TOTAL, qui depend de la quantite de jetons demandee au modele ;
//   — le SILENCE, c'est-a-dire l'attente avant qu'elle ouvre la bouche.
//
// Le second est ce que l'utilisateur ressent. Le premier est ce qu'on croit
// mesurer quand on regarde « Analyse IA en … ms ».
const http = require('http');
const path = require('path');
const os = require('os');

const REPONSE = "Un trou noir est une région de l'espace où la gravité est si intense "
  + "que rien ne s'en échappe. Même la lumière y reste piégée pour toujours.";

// L'ancien contrat exigeait aussi la fiche memoire. Elle pesait a peu pres
// autant que la reponse elle-meme — et l'utilisateur l'attendait.
const AVEC_MEMOIRE = JSON.stringify({
  response: REPONSE,
  memory: { shouldRemember: true, category: 'Study', title: 'trou noir',
            content: 'Hugo s’intéresse aux trous noirs' },
});
const SANS_MEMOIRE = JSON.stringify({ response: REPONSE });

const MS_PAR_CARACTERE = 12;   // vitesse d'ecriture d'un modele local

function fauxNovaCore(objet, port) {
  return new Promise((resolve) => {
    const serveur = http.createServer((req, res) => {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      const env = (nom, charge) =>
        res.write('event: ' + nom + '\ndata: ' + JSON.stringify(charge) + '\n\n');
      env('message_start', { type: 'message_start' });
      env('content_block_start', { type: 'content_block_start', index: 0 });
      let i = 0;
      const iv = setInterval(() => {
        if (i >= objet.length) {
          clearInterval(iv);
          env('content_block_stop', { type: 'content_block_stop', index: 0 });
          env('message_stop', { type: 'message_stop' });
          return res.end();
        }
        env('content_block_delta', {
          type: 'content_block_delta', index: 0,
          delta: { type: 'text_delta', text: objet[i] },
        });
        i++;
      }, MS_PAR_CARACTERE);
    });
    serveur.listen(port, () => resolve(serveur));
  });
}

async function mesurer(objet, port) {
  const serveur = await fauxNovaCore(objet, port);
  process.env.NOVA_PORT = String(port);
  delete require.cache[require.resolve('./brain')];   // pour qu'il relise le port
  const brain = require('./brain');
  brain.loadKey('', '');

  const T0 = Date.now();
  const phrases = [];
  const analyse = await brain.analyserEnFlux(
    'Explique-moi ce qu’est un trou noir', 'tu',
    (p) => phrases.push({ ms: Date.now() - T0, texte: p }),
  );
  const total = Date.now() - T0;
  serveur.close();
  return { phrases, total, analyse, silence: phrases.length ? phrases[0].ms : total };
}

(async () => {
  require('./memory').init(path.join(os.tmpdir(), 'nova-essai-' + Date.now()));

  const avant = await mesurer(AVEC_MEMOIRE, 8198);
  const apres = await mesurer(SANS_MEMOIRE, 8199);

  const montrer = (titre, m) => {
    console.log('\n── ' + titre + ' ' + '─'.repeat(Math.max(0, 46 - titre.length)));
    for (const p of m.phrases) {
      console.log('  ' + String(p.ms).padStart(5) + ' ms | ' + p.texte.slice(0, 58) + '…');
    }
    console.log('  ' + String(m.total).padStart(5) + ' ms | (fin de la génération)');
  };
  montrer('Contrat AVEC la fiche mémoire (avant)', avant);
  montrer('Contrat RÉPONSE SEULE (après)', apres);

  const pourcent = (a, b) => Math.round((1 - b / a) * 100) + ' % en moins';
  console.log('\n── Ce qui compte ──────────────────────────────');
  console.log('  silence avant qu’elle parle : ' + avant.silence + ' → ' + apres.silence
    + ' ms   (' + pourcent(avant.silence, apres.silence) + ')');
  console.log('  durée totale                : ' + avant.total + ' → ' + apres.total
    + ' ms   (' + pourcent(avant.total, apres.total) + ')');
  console.log();

  let echecs = 0;
  const verifier = (nom, ok) => { console.log((ok ? 'ok    ' : 'ECHEC ') + nom); if (!ok) echecs++; };

  verifier('deux phrases émises', apres.phrases.length === 2);
  verifier('texte reconstitué exact', apres.analyse.response === REPONSE);
  verifier('mémoire déduite localement, sans le modèle', !!apres.analyse.memory);
  verifier('elle parle avant la fin de la génération', apres.silence < apres.total);
  verifier('le contrat court réduit le silence', apres.silence < avant.silence);
  verifier('le contrat court réduit le total', apres.total < avant.total);

  process.exit(echecs ? 1 : 0);
})();
