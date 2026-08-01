//  PRINCIPE — découpage par la parole, pas par le chronomètre
//
//    1. le micro est capté en continu, en mémoire, sans rien envoyer ;
//    2. un tampon circulaire garde en permanence les 400 dernières ms —
//       c'est ce qui évite de perdre le « N » de « Nova », prononcé AVANT
//       que le niveau sonore ne franchisse le seuil ;
//    3. dès que tu parles, on enregistre ; dès que tu te tais 700 ms, on
//       arrête. L'extrait envoyé contient donc TA PHRASE ENTIÈRE, ni plus
//       ni moins — quelle que soit sa longueur ;
//    4. Whisper le transcrit, en local, dans Nova Core ;
//    5. si « Nova » y figure, on réveille — et la question qui suivait
//       est enchaînée sans la faire répéter.
//
//  CE QUE ÇA REMPLACE, ET POURQUOI
//
//  La version précédente envoyait un extrait de 2,6 s toutes les 3 s, en
//  aveugle. Deux conséquences mesurées dans les logs :
//
//    — la phrase tombait à cheval sur deux extraits. Whisper recevait deux
//      moitiés, dont aucune n'était compréhensible : « 0 segment ». D'où
//      une réussite sur dix tentatives, sans que rien ne soit « cassé » ;
//    — la machine transcrivait du silence en boucle. Sur un M1 8 Go, une
//      détection finissait par prendre 12 s parce que le processeur était
//      occupé à écouter le vide.
//
//  Ici, le silence ne coûte rien du tout : aucune requête n'est émise tant
//  que personne ne parle. Et quand quelqu'un parle, il n'y a jamais de
//  coupure au milieu d'un mot.
// ══════════════════════════════════════════════════════════════════════════
(function reveilLocal() {
  const NOVA_CORE = 'http://127.0.0.1:8100';

  // ── Réglages d'écoute ──
  const TAILLE_TRAME  = 2048;   // ~128 ms à 16 kHz : assez fin pour détecter
                                // une fin de phrase sans surcharger le CPU
  const ECHANT        = 16000;  // Whisper travaille en 16 kHz : autant le lui
                                // donner directement plutôt que de le laisser
                                // rééchantillonner 48 kHz inutilement
  const PRE_ROLL_MS   = 400;    // son conservé AVANT le déclenchement
  const SILENCE_MS    = 700;    // silence qui marque la fin d'une phrase
  const MIN_PAROLE_MS = 350;    // en dessous : un bruit, pas une phrase
  const MAX_PAROLE_MS = 8000;   // garde-fou : bruit continu, télévision…

  // Seuils sur l'énergie du signal (RMS). Le seuil de fin est plus bas que
  // celui de début : sans cet écart, une syllabe faible en milieu de phrase
  // couperait l'enregistrement en deux.
  const SEUIL_DEBUT   = 0.020;
  const SEUIL_FIN     = 0.012;
  // Le bruit de fond n'est pas le même chez toi et ailleurs. On le mesure en
  // continu et on exige d'être nettement au-dessus : c'est ce qui permet de
  // fonctionner aussi bien dans une pièce calme qu'avec un ventilateur.
  const MARGE_BRUIT   = 2.5;

  const DEPART = 12000;   // délai avant armement : laisse l'intro se terminer

  let flux = null, ctx = null, source = null, noeud = null;
  let actif = false, commande = null, occupe = false;
  let bruitFond = 0.004;
  // Taux réellement obtenu. Le système peut refuser 16 kHz et imposer le
  // sien ; écrire ECHANT dans l'en-tête WAV serait alors un mensonge, et
  // Whisper entendrait la phrase trois fois trop lente. On note ce qu'on a.
  let echantReel = ECHANT;

  // Tampon circulaire du pré-roll, et tampon de la phrase en cours.
  const tramesPreRoll = [];
  let tramesPhrase = null;
  let tramesSilence = 0;
  // Compte les trames REELLEMENT parlees. La duree totale ne suffit pas :
  // elle inclut le pre-roll et le silence de fin, si bien qu'un claquement
  // de porte de 120 ms produisait un extrait de 1,2 s d'apparence honnete.
  let tramesParole = 0;
  let dernierRapport = 0;

  const tramesPour = (ms) => Math.max(1, Math.round((ms / 1000) * echantReel / TAILLE_TRAME));

  function rms(trame) {
    let somme = 0;
    for (let i = 0; i < trame.length; i++) somme += trame[i] * trame[i];
    return Math.sqrt(somme / trame.length);
  }

  // ── Encodage WAV 16 bits ──
  // On envoie du WAV et non du WebM : le WebM ne peut pas être découpé
  // (seul le premier morceau porte l'en-tête), ce qui rend tout pré-roll
  // impossible. Le WAV, lui, se construit octet par octet.
  function versWav(trames) {
    let total = 0;
    for (const t of trames) total += t.length;
    const tampon = new ArrayBuffer(44 + total * 2);
    const vue = new DataView(tampon);
    const txt = (pos, s) => { for (let i = 0; i < s.length; i++) vue.setUint8(pos + i, s.charCodeAt(i)); };

    txt(0, 'RIFF');  vue.setUint32(4, 36 + total * 2, true);
    txt(8, 'WAVE');  txt(12, 'fmt ');
    vue.setUint32(16, 16, true);          // taille du bloc fmt
    vue.setUint16(20, 1, true);           // PCM non compressé
    vue.setUint16(22, 1, true);           // mono
    vue.setUint32(24, echantReel, true);
    vue.setUint32(28, echantReel * 2, true);  // octets par seconde
    vue.setUint16(32, 2, true);           // alignement
    vue.setUint16(34, 16, true);          // bits par échantillon
    txt(36, 'data'); vue.setUint32(40, total * 2, true);

    let pos = 44;
    for (const t of trames) {
      for (let i = 0; i < t.length; i++, pos += 2) {
        const v = Math.max(-1, Math.min(1, t[i]));
        vue.setInt16(pos, v < 0 ? v * 0x8000 : v * 0x7FFF, true);
      }
    }
    return new Blob([tampon], { type: 'audio/wav' });
  }

  // ── Le cœur : appelé pour chaque trame de ~128 ms ──
  function surTrame(evenement) {
    // On n'écoute QUE en veille. Sans ce garde-fou, Nova s'entendrait
    // elle-même parler et se réveillerait sur sa propre voix.
    if (!actif || typeof uiMode === 'undefined' || uiMode !== 'veille') {
      tramesPhrase = null;
      tramesPreRoll.length = 0;
      return;
    }

    const trame = new Float32Array(evenement.inputBuffer.getChannelData(0));
    const niveau = rms(trame);

    if (tramesPhrase === null) {
      // ── En attente ──
      // Le bruit de fond se met à jour lentement, et uniquement au calme :
      // sinon une phrase longue ferait monter le seuil et couperait la fin.
      if (niveau < SEUIL_DEBUT) bruitFond = bruitFond * 0.95 + niveau * 0.05;

      // Repère périodique : sans lui, un seuil mal réglé est indétectable.
      const maintenant = Date.now();
      if (maintenant - dernierRapport > 30000) {
        dernierRapport = maintenant;
        console.info('[NOVA/réveil] bruit de fond ' + bruitFond.toFixed(4)
          + ' — seuil effectif ' + Math.max(SEUIL_DEBUT, bruitFond * MARGE_BRUIT).toFixed(4));
      }

      tramesPreRoll.push(trame);
      while (tramesPreRoll.length > tramesPour(PRE_ROLL_MS)) tramesPreRoll.shift();

      if (niveau > Math.max(SEUIL_DEBUT, bruitFond * MARGE_BRUIT)) {
        // Départ : la phrase commence par le pré-roll, donc par le son
        // déjà prononcé au moment où le seuil a été franchi.
        tramesPhrase = tramesPreRoll.slice();
        tramesPhrase.push(trame);
        tramesPreRoll.length = 0;
        tramesSilence = 0;
        tramesParole = 1;
      }
      return;
    }

    // ── En cours d'enregistrement ──
    tramesPhrase.push(trame);
    if (niveau < Math.max(SEUIL_FIN, bruitFond * MARGE_BRUIT)) tramesSilence++;
    else { tramesSilence = 0; tramesParole++; }

    const duree = tramesPhrase.length * TAILLE_TRAME / echantReel * 1000;
    const finie = tramesSilence >= tramesPour(SILENCE_MS);

    if (finie || duree >= MAX_PAROLE_MS) {
      const trames = tramesPhrase;
      const parole = tramesParole * TAILLE_TRAME / echantReel * 1000;
      tramesPhrase = null;
      tramesSilence = 0;
      tramesParole = 0;
      // Trop court pour être une phrase : une porte, un clic, une chaise.
      if (parole < MIN_PAROLE_MS) return;
      analyser(versWav(trames), Math.round(duree));
    }
  }

  async function analyser(blob, ms) {
    if (occupe) return;   // une transcription à la fois
    occupe = true;
    try {
      const form = new FormData();
      form.append('file', blob, 'reveil.wav');
      const rep = await fetch(NOVA_CORE + '/v1/audio/wake', { method: 'POST', body: form });
      if (!rep.ok) {
        console.warn('[NOVA/réveil] Nova Core a répondu ' + rep.status
          + (rep.status === 503 ? ' — dépendance vocale absente (uv pip install -e ".[voice]")' : ''));
        return;
      }
      const res = await rep.json();
      if (res.text) console.info('[NOVA/réveil] ' + ms + ' ms → « ' + res.text + ' »');
      if (res.wake && uiMode === 'veille') {
        commande = (res.commande || '').trim() || null;
        console.info('[NOVA/réveil] déclenché'
          + (commande ? ' — enchaîne sur : « ' + commande + ' »' : ''));
        wakeToConversation();
      }
    } catch (e) {
      console.warn('[NOVA/réveil] échec :', e.message);
    } finally {
      occupe = false;
    }
  }

  async function ouvrirMicro() {
    if (flux) return true;
    try {
      flux = await navigator.mediaDevices.getUserMedia({
        audio: {
          // L'annulation d'écho évite que Nova ne s'entende elle-même ;
          // la suppression de bruit nettoie le signal avant Whisper.
          echoCancellation: true, noiseSuppression: true, autoGainControl: true,
        },
      });
      const Ctx = window.AudioContext || window.webkitAudioContext;
      // On demande directement 16 kHz : c'est le taux d'entrée de Whisper.
      try { ctx = new Ctx({ sampleRate: ECHANT }); }
      catch (e) { ctx = new Ctx(); }
      echantReel = ctx.sampleRate;
      if (echantReel !== ECHANT) {
        console.warn('[NOVA/réveil] le système impose ' + echantReel
          + ' Hz au lieu de ' + ECHANT + ' — sans conséquence sur la précision,'
          + ' l’extrait envoyé est simplement plus lourd');
      }
      source = ctx.createMediaStreamSource(flux);
      noeud = ctx.createScriptProcessor(TAILLE_TRAME, 1, 1);
      noeud.onaudioprocess = surTrame;
      source.connect(noeud);
      // Un ScriptProcessor ne tourne que s'il est raccordé à une sortie.
      // On le branche donc sur un gain à zéro : il travaille, sans un bruit.
      const muet = ctx.createGain();
      muet.gain.value = 0;
      noeud.connect(muet);
      muet.connect(ctx.destination);
      if (ctx.state === 'suspended') await ctx.resume();
      return true;
    } catch (e) {
      console.warn('[NOVA/réveil] micro indisponible :', e.message);
      return false;
    }
  }

  // ── Remplacement des deux fonctions mortes ──
  startWakeLoop = function () {
    actif = true;
    console.info('[NOVA/réveil] écoute par la parole active — dis « Nova »');
  };
  stopWakeLoop = function () {
    wakeOn = false;
    actif = false;
    tramesPhrase = null;
    tramesPreRoll.length = 0;
    console.info('[NOVA/réveil] écoute arrêtée');
  };

  // ── Enchaînement direct de la question dite avec le mot de réveil ──
  // On enveloppe le cycle existant plutôt que de le réécrire : si la question
  // a déjà été entendue, on la traite ; sinon, comportement d'origine intact.
  const cycleOrigine = cycleVocal;
  cycleVocal = async function () {
    if (commande) {
      const directe = commande;
      commande = null;
      console.info('[NOVA/réveil] traitement direct : « ' + directe + ' »');
      await traiterDemande(directe);
      return;
    }
    return cycleOrigine.apply(this, arguments);
  };

  // ── Armement automatique : aucun clic, aucune touche ──
  setTimeout(async () => {
    if (!(await ouvrirMicro())) return;
    wakeOn = true;
    try { if (typeof wakeChipEl !== 'undefined' && wakeChipEl) wakeChipEl.classList.add('on'); } catch (e) {}
    startWakeLoop();
  }, DEPART);
})();
