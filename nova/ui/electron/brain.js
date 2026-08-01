// ══════════════════════════════════════════════════════════════════════
//  NOVA — COMPRÉHENSION DES DEMANDES
//
//  Transforme une phrase libre en intention structurée :
//
//     "Aide-moi à lancer une startup"
//        ↓
//     { intent: "business_creation", goal: "...", workspaceType: "Business" }
//
//  Deux moteurs :
//    1. IA (Anthropic) — comprend n'importe quelle demande, même imprévue.
//       Nécessite ANTHROPIC_API_KEY dans le fichier de clés permanent.
//    2. Repli local — analyse sémantique simplifiée, sans réseau ni clé.
//       Moins fin, mais NOVA reste utilisable.
//
//  Ce module tourne dans le processus principal : aucune clé n'atteint
//  jamais la fenêtre.
// ══════════════════════════════════════════════════════════════════════
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const memory = require('./memory');

// ══════════════════════════════════════════════════════════════════════
//  OÙ EST LE CERVEAU DE NOVA ?
//
//    'local' (défaut) → Nova Core sur cette machine.
//                       Mémoire PostgreSQL, documents indexés, modèle Ollama.
//                       Aucune donnée ne quitte le Mac. Aucune clé requise.
//    'cloud'          → API Anthropic, comportement d'origine.
//
//  Bascule sans toucher au code :   NOVA_BRAIN=cloud npm start
//
//  Le protocole est IDENTIQUE dans les deux cas : Nova Core répond au
//  format Anthropic Messages. Seule l'adresse change — c'est précisément
//  ce que permet une frontière construite sur un standard.
// ══════════════════════════════════════════════════════════════════════
const CERVEAU_LOCAL = (process.env.NOVA_BRAIN || 'local') !== 'cloud';
const NOVA_HOST = process.env.NOVA_HOST || '127.0.0.1';
const NOVA_PORT = parseInt(process.env.NOVA_PORT || '8100', 10);

let apiKey = null;
// 110 jetons : deux phrases parlées dans leur enveloppe JSON tiennent
// largement dedans. Le plafond n'est pas une réserve gratuite — sur un modèle
// local, chaque jeton autorisé est un jeton que le moteur peut décider
// d'écrire, et il coûte ici environ 100 ms.
let config = { model: 'claude-sonnet-4-6', maxTokens: 110 };

// Les espaces de travail que NOVA saura ouvrir. Ajouter ici suffit :
// le modèle choisira automatiquement parmi cette liste.
const WORKSPACES = {
  Presentation: 'Créer un exposé, un diaporama, des slides',
  Travel:       'Organiser un voyage, un itinéraire, une destination',
  Document:     'Rédiger, résumer ou analyser un texte, un PDF, un rapport',
  Development:  'Créer une application, un site, du code, un outil logiciel',
  Business:     'Lancer une entreprise, un projet, une stratégie, des finances',
  Research:     'Chercher, comparer, analyser un sujet, une personne, un marché',
  Media:        'Analyser une vidéo, une image, un son',
  Schedule:     'Agenda, rendez-vous, rappels, organisation du temps',
  Conversation: 'Discussion simple, salutation, question courte — aucun espace requis',
};

function loadKey(dossierPermanent, projectRoot) {
  if (CERVEAU_LOCAL) {
    // Nova Core ne demande pas de clé : le modèle tourne ici.
    // On renseigne quand même `apiKey` car c'est lui qui autorise l'appel
    // au cerveau plus bas — sans quoi NOVA se replierait sur l'analyse locale.
    apiKey = 'local';
    config.model = 'nova';
    console.info('[NOVA/cerveau] Nova Core local — http://' + NOVA_HOST + ':' + NOVA_PORT);
    console.info('[NOVA/cerveau] mémoire et documents : sur cette machine');
    return apiKey;
  }

  const lire = (f) => {
    try {
      for (const line of fs.readFileSync(f, 'utf8').split(/\r?\n/)) {
        const m = line.match(/^\s*ANTHROPIC_API_KEY\s*=\s*(.+?)\s*$/);
        if (m) { const v = m[1].replace(/^["']|["']$/g, ''); if (v && !v.includes('colle_ta_cle')) return v; }
      }
    } catch (e) {}
    return null;
  };
  apiKey = lire(path.join(dossierPermanent, '.env'))
        || lire(path.join(projectRoot, '.env'))
        || process.env.ANTHROPIC_API_KEY
        || null;

  if (apiKey) console.info('[NOVA/cerveau] IA active — compréhension complète');
  else {
    console.warn('[NOVA/cerveau] Aucune clé Anthropic : analyse LOCALE simplifiée.');
    console.warn('[NOVA/cerveau] Pour la compréhension complète :');
    console.warn('[NOVA/cerveau]   npm run cle-ia sk-ant-...');
  }
  return apiKey;
}

function setConfig(c) { if (c) config = Object.assign(config, c); }

// ── Consigne donnée au modèle ────────────────────────────────────────
// ════════════════════════════════════════════════════════════════════════
//  BUDGET DE LA MÉMOIRE — en caractères, pas en nombre d'entrées
//
//  Sur un modèle local, le temps avant le premier mot est proportionnel à
//  la TAILLE du prompt. Mesuré sur cet iMac M1 :
//
//      prompt 6573 car.  →  21,4 s avant le premier mot   (~3,3 ms/car.)
//
//  `memory.contexte()` bornait le nombre d'entrées (40), jamais leur
//  longueur. Or NOVA enregistre un souvenir à presque chaque échange :
//  la mémoire grossit, le prompt avec elle, et chaque question devient
//  plus lente que la précédente.
//
//  C'est le pire défaut possible pour un assistant censé accumuler : il
//  punit exactement l'usage qu'on veut encourager, et il arrive assez
//  lentement pour qu'on l'attribue au modèle ou à la machine.
//
//  900 caractères ≈ 3 secondes de lecture. C'est le prix qu'on accepte
//  de payer, sur chaque question, pour que NOVA te connaisse.
// ════════════════════════════════════════════════════════════════════════
const BUDGET_MEMOIRE = 900;

function memoireBornee() {
  const brut = memory.contexte();
  if (brut.length <= BUDGET_MEMOIRE) return brut;

  // Coupe sur une fin de ligne : un souvenir tronqué au milieu d'un mot est
  // pire qu'un souvenir absent — le modèle le complète par une invention.
  const coupe = brut.slice(0, BUDGET_MEMOIRE);
  const fin = coupe.lastIndexOf('\n');
  const garde = fin > 200 ? coupe.slice(0, fin) : coupe;
  console.info('[NOVA] mémoire tronquée : ' + brut.length + ' → ' + garde.length
    + ' caractères (au-delà, chaque caractère coûte ~3 ms sur CHAQUE question)');
  return garde;
}

function systemPrompt(adresse) {
  const MEMOIRE = memoireBornee();
  // ══════════════════════════════════════════════════════════════════
  //  UN SEUL CHAMP — mesuré, pas supposé
  //
  //  Le contrat demandait aussi un objet `memory` : shouldRemember,
  //  category, title, content. Sur cette machine, l'écriture de cet
  //  objet coûtait à peu près autant de jetons que la réponse elle-même.
  //
  //  Autrement dit : tu attendais que NOVA finisse de remplir sa fiche
  //  mémoire avant qu'elle ouvre la bouche. C'est une inversion de
  //  priorité, pas une optimisation manquée.
  //
  //  Répondre est du travail INTERACTIF — quelqu'un attend.
  //  Mémoriser est du travail DE FOND — personne n'attend.
  //  Les mélanger fait payer le second au rythme du premier.
  //
  //  La mémorisation passe donc par l'analyse locale (`extraireMemoireLocale`),
  //  instantanée et sans modèle. Le jour où on voudra qu'un modèle s'en
  //  charge finement, ce sera dans une passe séparée, après la réponse.
  //
  //  DEUX phrases et non « une à deux » : avec une seule longue phrase,
  //  la parole en flux n'a rien à dire avant la fin. Mesuré — la première
  //  phrase arrivait 2 ms avant la dernière.
  // ══════════════════════════════════════════════════════════════════
  return `Tu es NOVA, l'assistante personnelle d'Hugo Kozlowski.
Tu ${adresse === 'tu' ? 'le tutoies' : 'le vouvoies'}. Tu es calme, directe, jamais flatteuse.

Réponds en DEUX phrases courtes, jamais plus. Elles seront PRONONCÉES, pas lues.
Termine chaque phrase par un point : c'est ce qui permet de la dire tout de suite.

Renvoie UNIQUEMENT un objet JSON avec une seule clé, nommée exactement
response. Ne traduis pas ce nom, ne le remplace pas, n'en ajoute aucun autre.

Question : « Quelle heure est-il ? »
{"response": "Il est vingt heures. La nuit va bientôt tomber."}

Question : « Qu'est-ce qu'un trou noir ? »
{"response": "Un trou noir est une région où la gravité est si forte que rien ne s'en échappe. Même la lumière y reste piégée."}

Ce que tu sais déjà d'Hugo :
<memoire>
${MEMOIRE}
</memoire>

Si la demande porte sur ces informations, réponds À PARTIR d'elles.
Si tu ne sais pas, dis-le en une phrase. N'invente jamais.`;
}

// ════════════════════════════════════════════════════════════════════════
//  PAROLE EN FLUX — commencer à parler avant d'avoir fini de penser
//
//  Aujourd'hui NOVA attend d'avoir écrit TOUTE sa réponse, puis la fait
//  synthétiser, puis la prononce. Trois attentes bout à bout.
//
//  Un humain ne fait pas ça. Il commence sa phrase et construit la suite
//  en parlant. C'est ce qui donne à Siri et à ChatGPT vocal leur air
//  instantané : ils ne calculent pas plus vite, ils commencent plus tôt.
//
//  DEUX OBSTACLES, ET COMMENT ON LES PASSE
//
//  1. La réponse arrive enveloppée dans du JSON : {"response":"..."}.
//     `ExtraitReponse` lit ce champ caractère par caractère, pendant que
//     le reste s'écrit encore. Il gère les échappements — un `\"` au
//     milieu d'une phrase ne doit pas être pris pour la fin du champ.
//
//  2. Une syllabe isolée ne se synthétise pas : on découpe sur les fins
//     de phrase, avec une longueur minimale. Mieux vaut une seconde de
//     plus qu'une voix hachée.
//
//  ⚠️ CE QUE ÇA NE FAIT PAS
//
//  Le flux ne raccourcit que l'ÉCRITURE. Si le modèle met trente secondes
//  à LIRE la question avant son premier mot, il n'y a rien à streamer
//  pendant ces trente secondes. La parole en flux et la taille du prompt
//  ne s'opposent pas : elles se multiplient.
// ════════════════════════════════════════════════════════════════════════

class ExtraitReponse {
  constructor() {
    this.brut = '';       // tout le JSON reçu jusqu'ici
    this.i = -1;          // position de lecture dans le champ `response`
    this.texte = '';      // le champ décodé, tel qu'on le prononcera
    this.fini = false;
  }

  // Renvoie ce qui vient d'être décodé, ou '' si rien de nouveau.
  feed(morceau) {
    this.brut += morceau;
    if (this.fini) return '';

    if (this.i < 0) {
      const debut = /"response"\s*:\s*"/.exec(this.brut);
      if (!debut) return '';
      this.i = debut.index + debut[0].length;
    }

    let ajout = '';
    while (this.i < this.brut.length) {
      const c = this.brut[this.i];

      if (c === '"') { this.fini = true; this.i++; break; }

      if (c === '\\') {
        // Une séquence d'échappement peut être coupée en deux par le flux.
        // On attend d'avoir tout ce qu'il faut plutôt que de deviner.
        const suivant = this.brut[this.i + 1];
        if (suivant === undefined) break;
        if (suivant === 'u') {
          if (this.brut.length < this.i + 6) break;
          ajout += String.fromCharCode(parseInt(this.brut.slice(this.i + 2, this.i + 6), 16));
          this.i += 6;
          continue;
        }
        const table = { n: '\n', t: ' ', r: '', '"': '"', '\\': '\\', '/': '/', b: '', f: '' };
        ajout += (suivant in table) ? table[suivant] : suivant;
        this.i += 2;
        continue;
      }

      ajout += c;
      this.i++;
    }

    this.texte += ajout;
    return ajout;
  }
}

// Longueur en dessous de laquelle on n'envoie pas un fragment à la synthèse :
// « Oui. » tout seul revient plus cher en aller-retour qu'il ne fait gagner,
// et une voix hachée annule le bénéfice ressenti.
const PHRASE_MIN = 25;

class DecoupePhrases {
  constructor(surPhrase) {
    this.reste = '';
    this.surPhrase = surPhrase;
  }

  feed(ajout) {
    if (!ajout) return;
    this.reste += ajout;

    // Une fin de phrase, c'est un point d'arrêt SUIVI d'un espace : sans
    // cette condition, « 3.5 » et « M. Dupont » seraient coupés en deux.
    let coupe;
    while ((coupe = /[.!?…](\s)/.exec(this.reste)) !== null) {
      const fin = coupe.index + 1;
      const phrase = this.reste.slice(0, fin).trim();
      if (phrase.length < PHRASE_MIN) break;   // trop court : on attend la suite
      this.reste = this.reste.slice(fin).replace(/^\s+/, '');
      this.surPhrase(phrase);
    }
  }

  // Tout ce qui reste à la fin est une phrase, même sans ponctuation.
  vider() {
    const reste = this.reste.trim();
    this.reste = '';
    if (reste) this.surPhrase(reste);
  }
}

// Options HTTP communes aux deux modes d'appel. Extraites pour qu'il n'y ait
// qu'un seul endroit à corriger le jour où l'adresse ou les en-têtes changent.
function optionsRequete(body) {
  return CERVEAU_LOCAL
    ? {
        hostname: NOVA_HOST,
        port: NOVA_PORT,
        path: '/v1/messages',
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'content-length': Buffer.byteLength(body),
        },
        // Généreux volontairement : le tout premier appel après le démarrage
        // charge le modèle en mémoire (plusieurs dizaines de secondes).
        timeout: 120000,
      }
    : {
        hostname: 'api.anthropic.com',
        path: '/v1/messages',
        method: 'POST',
        headers: {
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
          'content-type': 'application/json',
          'content-length': Buffer.byteLength(body),
        },
        timeout: 20000,
      };
}

// ── Filet de sécurité : retrouver la réponse quelle que soit sa forme ──
//
// Constaté en conditions réelles avec llama3.2:3b. Le contrat disait :
//
//     {"response":"tes deux phrases"}
//
// Le modèle a pris le texte d'exemple pour le NOM du champ :
//
//     { "tes deux phrases": { "Un trou noir est une région…": "C'est une…" } }
//
// La réponse était là, complète et juste, rangée là où personne ne la
// cherchait. NOVA a dit « Entendu. »
//
// La consigne est corrigée. Mais un petit modèle inventera d'autres formes,
// et perdre une bonne réponse pour une clé mal nommée est inacceptable : on
// parcourt donc tout l'objet et on récupère les phrases où qu'elles soient —
// dans les valeurs comme dans les clés, puisque le modèle a mis la moitié de
// sa réponse dans une clé.
const LONGUEUR_PHRASE = 30;   // en dessous, c'est un nom de champ, pas une phrase

function recupererPhrases(objet) {
  const trouvees = [];
  const parcourir = (noeud) => {
    if (typeof noeud === 'string') {
      if (noeud.length >= LONGUEUR_PHRASE) trouvees.push(noeud);
      return;
    }
    if (Array.isArray(noeud)) return noeud.forEach(parcourir);
    if (noeud && typeof noeud === 'object') {
      for (const [cle, valeur] of Object.entries(noeud)) {
        if (cle.length >= LONGUEUR_PHRASE) trouvees.push(cle);
        parcourir(valeur);
      }
    }
  };
  parcourir(objet);
  // L'ordre de parcours suit l'ordre d'écriture du modèle, donc l'ordre du
  // discours : on les recolle telles quelles plutôt que de les trier.
  return trouvees.join(' ').trim();
}

// ── Appel à l'IA, EN FLUX ────────────────────────────────────────────
//
// `surPhrase` est appelé dès qu'une phrase complète est disponible, bien
// avant la fin de la réponse. La promesse, elle, se résout comme
// `appelIA` : avec l'analyse complète, mémoire comprise.
function appelIAEnFlux(texte, adresse, surPhrase) {
  return new Promise((resolve, reject) => {
    const consigne = systemPrompt(adresse);
    console.info('[NOVA] prompt envoyé : ' + consigne.length
      + ' caractères → environ ' + Math.round(consigne.length * 3.3 / 1000)
      + ' s de lecture avant le premier mot');

    const body = JSON.stringify({
      model: config.model,
      max_tokens: config.maxTokens,
      system: consigne,
      messages: [{ role: 'user', content: texte }],
      stream: true,
    });

    const transport = CERVEAU_LOCAL ? http : https;
    const T0 = Date.now();
    const extrait = new ExtraitReponse();
    let premiere = true;
    let lecture = 0;   // temps passé à lire la question
    let recus = 0;     // caractères produits par le modèle
    const decoupe = new DecoupePhrases((phrase) => {
      if (premiere) {
        console.info('[NOVA] première phrase prononçable après ' + (Date.now() - T0)
          + ' ms — elle commence à parler pendant qu’elle finit d’écrire');
        premiere = false;
      }
      try { surPhrase(phrase); } catch (e) { console.warn('[NOVA] phrase non transmise :', e.message); }
    });

    const req = transport.request(optionsRequete(body), (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error('HTTP ' + res.statusCode));
      }
      let tampon = '';
      res.setEncoding('utf8');
      res.on('data', (bloc) => {
        tampon += bloc;
        // Les événements SSE sont séparés par une ligne vide. On ne traite
        // que les blocs complets : le dernier morceau peut être tronqué.
        const evenements = tampon.split('\n\n');
        tampon = evenements.pop();
        for (const ev of evenements) {
          for (const ligne of ev.split('\n')) {
            if (!ligne.startsWith('data:')) continue;
            try {
              const donnee = JSON.parse(ligne.slice(5).trim());
              if (donnee.type === 'content_block_delta' && donnee.delta && donnee.delta.text) {
                // ── LA MESURE QUI SÉPARE LES DEUX MOITIÉS ──
                //
                // Le tout premier caractère reçu marque la fin de la LECTURE
                // et le début de l'ÉCRITURE. Les deux se corrigent à l'opposé
                // l'une de l'autre — raccourcir le prompt d'un côté, produire
                // moins de jetons de l'autre — et les confondre fait corriger
                // trois fois la mauvaise chose. C'est arrivé.
                if (recus === 0) {
                  lecture = Date.now() - T0;
                  console.info('[NOVA] LECTURE de la question : ' + lecture + ' ms'
                    + ' (' + consigne.length + ' caractères de contexte)');
                }
                recus += donnee.delta.text.length;
                decoupe.feed(extrait.feed(donnee.delta.text));
              }
            } catch (e) { /* fragment incomplet : on ignore, on ne casse pas */ }
          }
        }
      });
      res.on('end', () => {
        decoupe.vider();
        const total = Date.now() - T0;
        const ecriture = Math.max(total - lecture, 1);
        console.info('[NOVA] ÉCRITURE de la réponse : ' + ecriture + ' ms pour '
          + recus + ' caractères — ' + (recus / 4 / (ecriture / 1000)).toFixed(1) + ' jetons/s');
        console.info('[NOVA] total ' + total + ' ms = lecture ' + lecture
          + ' + écriture ' + ecriture);
        // Ce que le modèle a VRAIMENT écrit. Sans cette ligne, une réponse
        // vide devient « Entendu. » — le garde-fou — et on cherche la cause
        // pendant deux tours en croyant que c'est le modèle qui répond ça.
        const diagnostic = () => console.warn('[NOVA] sortie brute du modèle ('
          + extrait.brut.length + ' car.) : ' + JSON.stringify(extrait.brut.slice(0, 300)));

        try {
          const txt = extrait.brut.replace(/```json|```/g, '').trim();
          const objet = JSON.parse(txt);
          if (!objet || !objet.response) {
            console.warn('[NOVA] JSON valide mais sans champ « response ».');
            diagnostic();
            const secours = recupererPhrases(objet);
            if (secours) {
              console.info('[NOVA] réponse récupérée : « ' + secours + ' »');
              return resolve({ response: secours });
            }
          }
          resolve(objet);
        } catch (e) {
          // Le JSON est illisible mais on a peut-être déjà prononcé la
          // réponse : on la rend plutôt que de tout perdre.
          if (extrait.texte) return resolve({ response: extrait.texte, memory: { shouldRemember: false } });
          console.warn('[NOVA] réponse illisible : ' + e.message);
          diagnostic();
          // Dernier recours : le modèle a peut-être répondu en texte brut,
          // sans JSON du tout. Mieux vaut le prononcer que dire « Entendu. »
          const brut = extrait.brut.replace(/```json|```/g, '').trim();
          if (brut && !brut.startsWith('{')) return resolve({ response: brut });
          reject(new Error('réponse illisible : ' + e.message));
        }
      });
    });
    req.on('timeout', () => req.destroy(new Error(
      CERVEAU_LOCAL
        ? 'délai dépassé — Nova Core est-il lancé ? (uvicorn sur le port ' + NOVA_PORT + ')'
        : 'délai dépassé')));
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ── Appel à l'IA ─────────────────────────────────────────────────────
function appelIA(texte, adresse) {
  return new Promise((resolve, reject) => {
    const consigne = systemPrompt(adresse);

    // Le chiffre qui explique la lenteur, dans le log de l'application.
    // Sans lui, « c'est lent » ne dit pas s'il faut couper le prompt,
    // baisser le plafond de jetons ou changer de modèle — et on corrige
    // trois fois la mauvaise chose.
    console.info('[NOVA] prompt envoyé : ' + consigne.length
      + ' caractères → environ ' + Math.round(consigne.length * 3.3 / 1000)
      + ' s de lecture avant le premier mot');

    const body = JSON.stringify({
      model: config.model,
      max_tokens: config.maxTokens,
      system: consigne,
      messages: [{ role: 'user', content: texte }],
    });

    // Même requête, même format, même code de lecture ci-dessous.
    // Seuls le transport et l'adresse changent.
    const transport = CERVEAU_LOCAL ? http : https;
    const options = CERVEAU_LOCAL
      ? {
          hostname: NOVA_HOST,
          port: NOVA_PORT,
          path: '/v1/messages',
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            'content-length': Buffer.byteLength(body),
          },
          // Généreux volontairement : le tout premier appel après le démarrage
          // charge le modèle en mémoire (plusieurs dizaines de secondes).
          // Les suivants répondent en quelques secondes.
          timeout: 120000,
        }
      : {
          hostname: 'api.anthropic.com',
          path: '/v1/messages',
          method: 'POST',
          headers: {
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
            'content-length': Buffer.byteLength(body),
          },
          timeout: 20000,
        };

    const req = transport.request(options, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const brut = Buffer.concat(chunks).toString('utf8');
        if (res.statusCode !== 200) {
          return reject(new Error(`HTTP ${res.statusCode} — ${brut.slice(0, 200)}`));
        }
        if (CERVEAU_LOCAL && res.statusCode === 200 && !brut.trim()) {
          return reject(new Error('Nova Core a répondu vide — le service tourne-t-il ?'));
        }
        try {
          const rep = JSON.parse(brut);
          let txt = (rep.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
          txt = txt.replace(/```json|```/g, '').trim();
          resolve(JSON.parse(txt));
        } catch (e) {
          reject(new Error('réponse illisible : ' + e.message));
        }
      });
    });
    req.on('timeout', () => req.destroy(new Error(
      CERVEAU_LOCAL
        ? 'délai dépassé — Nova Core est-il lancé ? (uvicorn sur le port ' + NOVA_PORT + ')'
        : 'délai dépassé')));
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ── Repli local ──────────────────────────────────────────────────────
// Pas de mots-clés rigides : on pondère des familles de sens, et on
// retient la plus probable. Moins fin qu'une IA, mais jamais bloquant.
const FAMILLES = [
  { intent:'greeting',          ws:null,           mots:['bonjour','salut','bonsoir','coucou','ca va','comment vas'] },
  { intent:'presentation_prep', ws:'Presentation', mots:['expose','presentation','diapo','powerpoint','slide','soutenance','oral'] },
  { intent:'travel_planning',   ws:'Travel',       mots:['voyage','partir','vol','avion','hotel','sejour','vacances','itineraire','visiter','je pars'] },
  { intent:'document_work',     ws:'Document',     mots:['resume','resumer','pdf','document','rapport','lettre','rediger','ecrire','texte','corriger'] },
  { intent:'development',       ws:'Development',  mots:['application','appli','site','code','programme','logiciel','developper','coder','extension'] },
  { intent:'business_creation', ws:'Business',     mots:['startup','entreprise','societe','business','lancer','finance','budget','client','vendre','marketing'] },
  { intent:'research',          ws:'Research',     mots:['cherche','recherche','analyse','compare','explique','information','qui est','trouve'] },
  { intent:'media_analysis',    ws:'Media',        mots:['video','image','photo','audio','son','musique','film'] },
  { intent:'schedule',          ws:'Schedule',     mots:['agenda','rendez','planning','rappel','demain','semaine','calendrier','reunion'] },
];

function normalise(s){
  return (s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
}

// Détecte une question portant sur la mémoire et y répond directement.
function repondreDepuisMemoire(texte, vous) {
  const t = normalise(texte);
  const estQuestion = /(quels?|quelles?|que sais|qu.est ce que tu sais|ou en est|rappelle|mes projets|mes objectifs|mes etudes|mes preferences)/.test(t);
  if (!estQuestion) return null;

  const cats = [
    { motif:/projets?/,                    cat:'Project',    label:'projet' },
    { motif:/objectifs?|ambitions?|buts?/, cat:'Goal',       label:'objectif' },
    { motif:/etudes?|expose|devoir|revis/, cat:'Study',      label:'sujet d\u2019étude' },
    { motif:/preferences?|habitudes?/,     cat:'Preference', label:'préférence' },
  ];
  const trouve = cats.find(c => c.motif.test(t));

  let entrees, intro;
  if (trouve) {
    entrees = memory.tout().entries.filter(e => e.category === trouve.cat);
    intro = entrees.length
      ? (vous ? `Vous avez ${entrees.length} ${trouve.label}${entrees.length>1?'s':''} en mémoire : `
              : `Tu as ${entrees.length} ${trouve.label}${entrees.length>1?'s':''} en mémoire : `)
      : (vous ? `Je n\u2019ai encore aucun ${trouve.label} en mémoire.`
              : `Je n\u2019ai encore aucun ${trouve.label} en mémoire.`);
  } else {
    entrees = memory.chercher(texte, 3);
    if (!entrees.length) return null;
    intro = vous ? 'Voici ce dont je me souviens : ' : 'Voici ce dont je me souviens : ';
  }

  const liste = entrees.map(e => e.title + (e.content ? ' — ' + e.content : '')).join('. ');
  return {
    userRequest: texte,
    intent: 'memory_query',
    goal: 'Consulter la mémoire de NOVA',
    requiresWorkspace: false,
    workspaceType: null,
    response: entrees.length ? intro + liste + '.' : intro,
    memory: { shouldRemember: false },
    _moteur: 'memoire',
  };
}

// Extraction locale d'une information durable, sans IA.
function extraireMemoireLocale(texte) {
  const t = texte.trim();
  const motifs = [
    // ── PROJETS ──
    { re:/(?:je (?:travaille|bosse) sur|mon projet(?: s.appelle)?|je (?:developpe|développe)|je (?:cree|crée)|(?:aide|aidez).{0,6}moi (?:a|à) (?:creer|créer|developper|développer|faire|coder|construire))\s+(?:une?\s+)?([^.,;!?]{2,60})/i, cat:'Project' },
    { re:/(?:mon|ma)\s+(?:appli|application|extension|site|logiciel|startup|entreprise|boite|boîte)\s+([^.,;!?]{2,60})/i, cat:'Project' },
    // forme impérative : « Crée une application pour gérer mes finances »
    { re:/^(?:cree|crée|fais|construis|developpe|développe|code)\s+(?:moi\s+)?(?:une?\s+|des\s+)?((?:appli|application|site|extension|logiciel|outil|programme)[^.,;!?]{0,60})/i, cat:'Project' },

    // ── ÉTUDES ──
    { re:/(?:expose|exposé|devoir|controle|contrôle|examen|dissertation|memoire|mémoire|presentation|présentation)\s+(?:sur|de|d.)\s+([^.,;!?]{2,60})/i, cat:'Study' },
    { re:/(?:je (?:revise|révise)|revisions? (?:de|pour)|réviser)\s+([^.,;!?]{2,60})/i, cat:'Study' },

    // ── OBJECTIFS ──
    { re:/(?:mon objectif est(?: de)?|je veux|j.aimerais|mon but est(?: de)?|je souhaite)\s+([^.,;!?]{3,80})/i, cat:'Goal' },
    // « Aide-moi à lancer une startup » : l'objectif est dans le verbe
    { re:/(?:aide|aidez)[- ]?moi\s+(?:a|à)\s+((?:lancer|monter|creer|créer|demarrer|démarrer)\s+(?:une?\s+)?[^.,;!?]{2,50})/i, cat:'Goal' },

    // ── PRÉFÉRENCES ──
    { re:/(?:j.habite (?:a|à)|je vis (?:a|à)|je suis (?:de|originaire de))\s+([A-ZÀ-Ý][^.,;!?]{1,40})/, cat:'Preference' },
    { re:/(?:je m.appelle|mon (?:prenom|prénom|nom) est)\s+([^.,;!?]{2,40})/i, cat:'Preference' },
  ];

  for (const m of motifs) {
    const r = t.match(m.re);
    if (r && r[1]) {
      let brut = (r[1] || '').trim().replace(/^(mon|ma|mes|le|la|les|un|une|des|de|d.)\s+/i, '');
      // Cas « aide-moi à lancer une startup » : le groupe capturé peut être
      // vide, on retombe alors sur l'intention exprimée dans la phrase.
      if (!brut) {
        const g = t.match(/(startup|entreprise|societe|société|boite|boîte)/i);
        brut = g ? 'Lancer une ' + g[1].toLowerCase() : t.slice(0, 40);
      }
      const titre = brut.split(/\s+/).slice(0, 5).join(' ')
                        .replace(/^./, c => c.toUpperCase());
      return { shouldRemember:true, category:m.cat, title:titre, content:t };
    }
  }
  return { shouldRemember:false };
}

function analyseLocale(texte, adresse) {
  const vous = adresse !== 'tu';
  // 1) La demande porte-t-elle sur ce que Nova sait déjà ?
  const depuisMemoire = repondreDepuisMemoire(texte, vous);
  if (depuisMemoire) return depuisMemoire;

  const t = normalise(texte);
  let meilleur = null, score = 0;
  for (const f of FAMILLES) {
    let s = 0;
    for (const m of f.mots) if (t.includes(m)) s += m.length > 6 ? 2 : 1;
    if (s > score) { score = s; meilleur = f; }
  }

  if (!meilleur) {
    return {
      userRequest: texte,
      intent: 'unknown_request',
      goal: 'Demande non identifiée par l\u2019analyse locale',
      requiresWorkspace: false,
      workspaceType: null,
      response: vous
        ? 'J\u2019ai bien noté votre demande. Je ne sais pas encore la traiter, mais nous pouvons y travailler ensemble.'
        : 'J\u2019ai bien noté ta demande. Je ne sais pas encore la traiter, mais on peut y travailler ensemble.',
      memory: extraireMemoireLocale(texte),
      _moteur: 'local',
    };
  }

  const reponses = {
    greeting:          [ 'Bonjour. Que puis-je faire pour vous ?', 'Bonjour. Que puis-je faire pour toi ?' ],
    presentation_prep: [ 'Très bien, je prépare votre exposé.', 'Très bien, je prépare ton exposé.' ],
    travel_planning:   [ 'Je m\u2019occupe de votre voyage.', 'Je m\u2019occupe de ton voyage.' ],
    document_work:     [ 'Je regarde ce document pour vous.', 'Je regarde ce document pour toi.' ],
    development:       [ 'Intéressant. Je prépare l\u2019espace de développement.', 'Intéressant. Je prépare l\u2019espace de développement.' ],
    business_creation: [ 'Beau projet. Je prépare votre espace de travail.', 'Beau projet. Je prépare ton espace de travail.' ],
    research:          [ 'Je lance la recherche.', 'Je lance la recherche.' ],
    media_analysis:    [ 'Je regarde ce média.', 'Je regarde ce média.' ],
    schedule:          [ 'Je consulte votre agenda.', 'Je consulte ton agenda.' ],
  };
  const r = reponses[meilleur.intent] || ['Entendu.', 'Entendu.'];

  return {
    userRequest: texte,
    intent: meilleur.intent,
    goal: WORKSPACES[meilleur.ws] || 'Échange simple',
    requiresWorkspace: !!meilleur.ws,
    workspaceType: meilleur.ws,
    response: vous ? r[0] : r[1],
    memory: extraireMemoireLocale(texte),
    _moteur: 'local',
  };
}

// ── Réponses immédiates ──────────────────────────────────────────────
//
// Certaines questions n'ont pas de raison de traverser un modèle de
// langue. « Quelle heure est-il » a UNE réponse, l'ordinateur la connaît
// exactement, et la faire calculer par un réseau de neurones coûtait
// entre 9 et 28 secondes pour un résultat parfois faux.
//
// Ces réponses-là partent en moins d'une milliseconde. Ce n'est pas un
// contournement : c'est la bonne architecture. Un assistant demande au
// modèle ce qui exige du jugement, et lit l'horloge pour lire l'heure.
//
// La règle pour en ajouter : la question doit avoir une réponse unique,
// vérifiable, et connue de la machine. Tout le reste va au cerveau.
// ─────────────────────────────────────────────────────────────────────

function immediat(texte, intent, response) {
  return {
    userRequest: texte,
    intent,
    goal: 'Réponse directe, sans modèle',
    requiresWorkspace: false,
    workspaceType: null,
    response,
    memory: { shouldRemember: false },
    _moteur: 'immediat',
  };
}

function repondreImmediatement(texte) {
  const t = normalise(texte);

  // L'heure. « quelle heure est-il », « il est quelle heure », « t'as l'heure »
  // On accepte aussi « quelheur » : Whisper colle et tronque les mots courts,
  // et refuser la réponse instantanée pour une lettre manquante serait absurde.
  // Exclusion : « dans deux heures », « une heure de route » — là il s'agit
  // d'une durée, pas d'une demande d'heure.
  const demandeHeure = /\bheure\b|\bheur\b|\bquelheure?\b/.test(t);
  const parleDeDuree = /\bheures?\s+(de|du|pour|avant|apres)\b|\b(dans|depuis|pendant)\b/.test(t);
  if (demandeHeure && !parleDeDuree) {
    const maintenant = new Date();
    const h = maintenant.getHours();
    const m = maintenant.getMinutes();
    // « 14 h 05 » et non « 14:5 » : le texte sera PRONONCÉ, pas lu.
    const dit = m === 0 ? `${h} heures pile`
              : `${h} heures ${m < 10 ? '0' + m : m}`;
    return immediat(texte, 'time_query', `Il est ${dit}.`);
  }

  // La date du jour.
  // « quelle jour est on » n'est pas du français, mais c'est exactement ce
  // que Whisper transcrit. Une réponse instantanée refusée pour un accord
  // grammatical serait absurde : on accepte les deux formes.
  const demandeJour = /\bquel(le)?s? jours?\b|\bon est quel\b|\bquel(le)? est on\b/.test(t);
  const demandeDate = /\bquel(le)? date\b|\bla date\b|\bdate du jour\b|\bquel(le) jour sommes\b|\bsommes nous\b/.test(t);
  if (demandeJour || demandeDate) {
    const d = new Date();
    const jour = new Intl.DateTimeFormat('fr-FR', { weekday: 'long' }).format(d);
    const mois = new Intl.DateTimeFormat('fr-FR', { month: 'long' }).format(d);
    // « le 1er août », jamais « le 1 août » : le texte sera prononcé.
    const quantieme = d.getDate() === 1 ? '1er' : String(d.getDate());
    return immediat(texte, 'date_query',
      `Nous sommes le ${jour} ${quantieme} ${mois} ${d.getFullYear()}.`);
  }

  return null;
}

// ── Point d'entrée ───────────────────────────────────────────────────
async function analyser(texte, adresse = 'vous') {
  console.info('[NOVA] User Input Received');
  console.info('        « ' + texte + ' »');
  // Avant tout : la question a-t-elle une réponse exacte et immédiate ?
  const direct = repondreImmediatement(texte);
  if (direct) {
    console.info('[NOVA] réponse immédiate (aucun modèle appelé) — 0 ms');
    console.info('        « ' + direct.response + ' »');
    return direct;
  }

  console.info('[NOVA] Analysing Request');

  let res = null;
  if (apiKey) {
    const t0 = Date.now();
    try {
      res = await appelIA(texte, adresse);
      res._moteur = 'ia';
      console.info('[NOVA] Analyse IA en ' + (Date.now() - t0) + ' ms');
    } catch (e) {
      console.error('[NOVA] Échec de l\u2019analyse IA :', e.message);
      console.warn('[NOVA] Repli sur l\u2019analyse locale');
    }
  }
  if (!res) res = analyseLocale(texte, adresse);

  // garde-fous : le modèle peut oublier un champ
  res.userRequest       = res.userRequest || texte;
  res.intent            = res.intent || 'unknown_request';
  res.goal              = res.goal || '';
  res.requiresWorkspace = !!res.requiresWorkspace;
  res.workspaceType     = res.requiresWorkspace ? (res.workspaceType || 'Research') : null;
  res.response          = res.response || 'Entendu.';

  console.info('[NOVA] Intent Detected:');
  console.info('        ' + res.intent);
  console.info('[NOVA] Goal:');
  console.info('        ' + res.goal);
  console.info('[NOVA] Workspace Required:');
  console.info('        ' + (res.requiresWorkspace ? 'YES' : 'NO'));
  console.info('[NOVA] Selected Workspace:');
  console.info('        ' + (res.workspaceType || '—'));
  console.info('[NOVA] Response Generated');
  console.info('        « ' + res.response + ' »');
  console.info('        moteur : ' + (res._moteur === 'ia' ? 'IA' : 'analyse locale'));

  return res;
}

// ── Point d'entrée EN FLUX ───────────────────────────────────────────
//
// Même contrat que `analyser`, avec un rappel en plus : `surPhrase` est
// appelé dès qu'une phrase est prononçable. Si le flux échoue pour une
// raison quelconque, on retombe sur l'appel classique — une nouveauté ne
// doit jamais rendre Nova moins fiable qu'avant.
async function analyserEnFlux(texte, adresse = 'vous', surPhrase = () => {}) {
  console.info('[NOVA] User Input Received');
  console.info('        « ' + texte + ' »');

  const direct = repondreImmediatement(texte);
  if (direct) {
    console.info('[NOVA] réponse immédiate (aucun modèle appelé) — 0 ms');
    console.info('        « ' + direct.response + ' »');
    surPhrase(direct.response);
    return garde(direct, texte);
  }

  if (apiKey) {
    const t0 = Date.now();
    try {
      const res = await appelIAEnFlux(texte, adresse, surPhrase);
      res._moteur = 'ia';
      // La mémorisation ne passe plus par le modèle : elle est déduite ici,
      // en zéro milliseconde, APRÈS que Nova a parlé. Répondre est du travail
      // interactif, mémoriser est du travail de fond — les mélanger faisait
      // payer le second au rythme du premier.
      if (!res.memory) res.memory = extraireMemoireLocale(texte);
      console.info('[NOVA] Analyse IA en flux, terminée en ' + (Date.now() - t0) + ' ms');
      return garde(res, texte);
    } catch (e) {
      console.error('[NOVA] Échec du flux :', e.message);
      console.warn('[NOVA] Repli sur l’appel classique');
    }
  }
  const res = await analyser(texte, adresse);
  if (res && res.response) surPhrase(res.response);
  return res;
}

// Garde-fous communs : le modèle peut oublier un champ.
function garde(res, texte) {
  res.userRequest       = res.userRequest || texte;
  res.intent            = res.intent || 'unknown_request';
  res.goal              = res.goal || '';
  res.requiresWorkspace = !!res.requiresWorkspace;
  res.workspaceType     = res.requiresWorkspace ? (res.workspaceType || 'Research') : null;
  res.response          = res.response || 'Entendu.';
  res.memory            = res.memory || { shouldRemember: false };
  console.info('[NOVA] Response Generated');
  console.info('        « ' + res.response + ' »');
  return res;
}

module.exports = { loadKey, setConfig, analyser, analyserEnFlux, WORKSPACES };
