
// ══════════════════════════════════════════════════════════════════════════
//  PAROLE EN FLUX — elle commence à parler avant d'avoir fini d'écrire
//
//  Jusqu'ici : NOVA écrivait TOUTE sa réponse, puis la faisait synthétiser,
//  puis la prononçait. Trois attentes bout à bout, et un silence complet
//  pendant tout ce temps.
//
//  Désormais : chaque phrase part à la synthèse dès qu'elle est terminée,
//  pendant que la suivante s'écrit encore. Le temps total ne change pas ;
//  le temps de SILENCE, lui, est divisé par trois ou quatre. C'est ce qui
//  fait la différence entre « elle réfléchit » et « elle répond ».
//
//  Ajout pur, comme l'écoute : aucune ligne existante n'est modifiée, et si
//  le pont ne propose pas le flux (preload ancien), le comportement
//  d'origine s'applique intégralement.
// ══════════════════════════════════════════════════════════════════════════
(function paroleEnFlux() {
  if (typeof traiterDemande !== 'function') return;

  // ── File d'attente ──
  // Les phrases arrivent plus vite qu'elles ne se prononcent. Sans file,
  // deux voix se superposeraient dès la deuxième phrase.
  let file = Promise.resolve();
  let enAttente = 0;

  function enfiler(phrase) {
    if (!phrase) return;
    enAttente++;
    file = file
      .then(async () => {
        if (typeof setAppState === 'function' && appState !== 'SPEAKING') setAppState('SPEAKING');
        msgEl.textContent = phrase;
        msgEl.classList.add('visible');
        const ok = await speak(phrase);
        if (!ok) await typewriter(phrase);
      })
      .catch((e) => console.warn('[NOVA/flux] phrase non prononcée :', e && e.message))
      .then(() => { enAttente--; });
  }

  async function attendreLaFin() {
    // La file grandit pendant qu'on l'attend : on boucle jusqu'au silence.
    while (enAttente > 0) await file;
    await file;
  }

  if (window.nova && typeof window.nova.onPhrase === 'function') {
    window.nova.onPhrase(enfiler);
  }

  // ── Enveloppe du pipeline ──
  const traiterOrigine = traiterDemande;

  traiterDemande = async function (texte, opts = {}) {
    const possible = isDesktopApp && window.nova
      && typeof window.nova.analyzeStream === 'function'
      && typeof window.nova.onPhrase === 'function';
    if (!possible) return traiterOrigine.apply(this, arguments);

    if (!texte || !texte.trim()) {
      console.warn('[NOVA] demande vide, ignorée');
      return null;
    }

    console.info('[NOVA] ─────────────────────────────────');
    console.info('[NOVA] User Input Received');
    console.info('        « ' + texte + ' »');

    try {
      setAppState('THINKING');
      console.info('[NOVA] Analysing Request (flux — elle parlera dès la première phrase)…');
      const t0 = performance.now();

      const analyse = await window.nova.analyzeStream(texte, adresse);
      console.info('[NOVA] réponse du cerveau en ' + Math.round(performance.now() - t0) + ' ms');
      if (!analyse) throw new Error('le cerveau a renvoyé null — voir les erreurs du processus principal');

      console.info('[NOVA] Intent Detected: ' + analyse.intent);

      if (analyse.memory && analyse.memory.shouldRemember && window.nova.memoryAdd) {
        const enr = await window.nova.memoryAdd({
          category: analyse.memory.category,
          title:    analyse.memory.title,
          content:  analyse.memory.content,
          source:   texte,
        });
        if (enr) {
          analyse._memorise = enr;
          console.info('[NOVA] souvenir enregistré : ' + enr.category + ' / ' + enr.title);
        }
      }

      if (opts.onAnalyse) {
        try { opts.onAnalyse(analyse); }
        catch (e) { console.error('[NOVA] affichage du résultat impossible :', e); }
      }

      // La parole a déjà commencé : il ne reste qu'à la laisser finir.
      await attendreLaFin();
      console.info('[NOVA] parole terminée — ' + Math.round(performance.now() - t0) + ' ms au total');

      msgEl.classList.remove('visible');
      if (analyse.requiresWorkspace) {
        setAppState(WORKSPACE_ETAT[analyse.workspaceType] || 'PRESENTING');
      } else if (appState !== 'PRESENTING') {
        setAppState('IDLE');
      }
      return analyse;

    } catch (e) {
      console.error('[NOVA] PIPELINE FAILED:', e.message);
      if (e.stack) console.error(e.stack);
      if (opts.onErreur) opts.onErreur(e);
      setAppState('IDLE');
      return null;
    }
  };

  console.info('[NOVA/flux] parole en flux active — elle parlera dès la première phrase');
})();
