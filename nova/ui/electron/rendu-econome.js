
// ══════════════════════════════════════════════════════════════════════════
//  RENDU ÉCONOME — rendre le GPU au modèle pendant qu'il réfléchit
//
//  LE CONSTAT
//
//  Mesures sur l'iMac M1, même modèle, mêmes appels :
//
//                          application fermée   application ouverte
//      lecture de la question      0,2 s              14,6 s
//      écriture                 28,8 jetons/s      7,6 jetons/s
//
//  Soixante-treize fois plus lent à lire, presque quatre fois plus lent à
//  écrire. Le modèle n'y était pour rien, le prompt non plus : c'est
//  l'interface qui étranglait le moteur.
//
//  POURQUOI, ET POURQUOI L'ÉCART EST SI DIFFÉRENT SUR LES DEUX PHASES
//
//  Sur Apple Silicon, la sphère et le modèle partagent le MÊME processeur
//  graphique. Or les deux phases n'en dépendent pas de la même façon :
//
//    — la LECTURE traite tous les jetons du prompt en parallèle. C'est la
//      phase la plus massivement parallèle, donc celle qui souffre le plus
//      d'un GPU déjà occupé : ×73.
//    — l'ÉCRITURE produit un jeton après l'autre et bute surtout sur la
//      bande passante mémoire : ×3,8 seulement.
//
//  Ce rapport de 73 contre 3,8 n'est pas un détail : c'est la signature
//  d'une contention GPU, et c'est ce qui a permis de désigner la sphère
//  plutôt que la mémoire ou le disque.
//
//  CE QU'ON FAIT
//
//  On ne coupe pas l'animation — une sphère figée dirait « c'est planté »
//  exactement au moment où il ne faut pas. On abaisse sa cadence, et on
//  l'abaisse le plus fort précisément quand le modèle travaille.
//
//  Soixante images par seconde pour une respiration de 7,5 secondes est de
//  toute façon du gaspillage : l'œil ne voit aucune différence en dessous
//  de 15, et la machine, elle, la voit très bien.
//
//  Ajout pur : aucune ligne existante n'est modifiée. On enveloppe
//  `requestAnimationFrame`, ce qui atteint la boucle de rendu sans avoir à
//  la toucher.
// ══════════════════════════════════════════════════════════════════════════
(function renduEconome() {
  if (typeof window === 'undefined' || !window.requestAnimationFrame) return;

  // Cadence visée, par état. Le fond de l'affaire tient dans la ligne
  // THINKING : c'est le seul moment où le modèle a vraiment besoin du GPU,
  // et le seul où personne ne regarde la sphère.
  const CADENCE = {
    INTRO:      30,   // moment de mise en scène, aucun modèle ne tourne
    PRESENTING: 30,
    IDLE:       12,   // respiration de 7,5 s : 12 images suffisent
    LISTENING:  20,   // elle réagit à ta voix, ça doit rester vivant
    THINKING:    4,   // ⚡ le GPU appartient au modèle
    SPEAKING:   12,   // il écrit peut-être encore la phrase suivante
  };
  const PAR_DEFAUT = 20;

  const rafOrigine = window.requestAnimationFrame.bind(window);
  const cafOrigine = window.cancelAnimationFrame.bind(window);

  // Les identifiants natifs sont de petits entiers. On numérote les nôtres
  // très au-dessus pour ne jamais entrer en collision avec eux.
  let compteur = 1e9;
  const differes = new Map();
  let dernierRendu = 0;

  function cadence() {
    if (typeof appState === 'undefined') return PAR_DEFAUT;
    return CADENCE[appState] || PAR_DEFAUT;
  }

  window.requestAnimationFrame = function (rappel) {
    const intervalle = 1000 / cadence();
    const attente = intervalle - (performance.now() - dernierRendu);

    if (attente <= 1) {
      dernierRendu = performance.now();
      return rafOrigine(rappel);
    }

    const id = ++compteur;
    const minuteur = setTimeout(() => {
      // On repasse par le vrai rAF : le rendu doit rester synchronisé avec
      // l'affichage, sinon on gagne des images déchirées au lieu de temps.
      const vrai = rafOrigine((horodatage) => {
        differes.delete(id);
        dernierRendu = performance.now();
        rappel(horodatage);
      });
      differes.set(id, { raf: vrai });
    }, attente);

    differes.set(id, { minuteur });
    return id;
  };

  window.cancelAnimationFrame = function (id) {
    const differe = differes.get(id);
    if (!differe) return cafOrigine(id);
    if (differe.minuteur) clearTimeout(differe.minuteur);
    if (differe.raf) cafOrigine(differe.raf);
    differes.delete(id);
  };

  console.info('[NOVA/rendu] cadence adaptative — 4 images/s pendant qu’elle réfléchit,'
    + ' le GPU revient au modèle');
})();
