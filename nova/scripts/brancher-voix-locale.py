#!/usr/bin/env python3
"""Faire parler l'application avec Nova Core au lieu d'ElevenLabs.

CE QU'ON REMPLACE, ET POURQUOI SEULEMENT CA

`electron/tts.js` est bien decoupe : `requestSpeech(text)` est la SEULE
fonction qui parle au fournisseur de voix. Tout le reste — le cache disque, le
prechauffage, `speak()`, le repli sur la voix systeme — l'entoure sans savoir
a qui elle s'adresse.

On remplace donc ce seul corps de fonction. Le cache continue de fonctionner,
le repli reste en place, et les appelants ne changent pas. Reecrire davantage
serait plus rapide a taper et bien plus long a reparer.

⚠️ TROIS PIEGES QUI NE SE VOIENT PAS DANS LE DIFF

1. ElevenLabs rendait du MP3, Kokoro rend du WAV. Le cache disque contient
   donc des MP3 de l'ancienne voix : sans le vider, l'intro continuerait de
   parler avec ElevenLabs pendant que le reste parle avec Kokoro. On le vide.

2. Le delai. ElevenLabs repondait en ~300 ms ; le PREMIER appel local charge
   un modele et peut demander vingt secondes. Garder 15 000 ms ferait echouer
   la premiere phrase de chaque session — c'est-a-dire celle qu'on entend.

3. `http` et non `https`. Le module n'etait pas importe : on parlait a
   l'exterieur, jamais a la machine.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

NOUVELLE = '''// ── Appel a Nova Core ─────────────────────────────────────────────────────
//
// La voix est LOCALE depuis qu'ElevenLabs s'est tu en pleine conversation :
//
//     "This request exceeds your quota of 10000. You have 3 credits
//      remaining, while 10 credits are required for this request."
//
// Dix mille credits par mois, une reponse ~150 caracteres : soixante reponses
// mensuelles. Un assistant dont la voix depend d'un quota n'est pas un
// assistant personnel, c'est un abonnement qui parle.
//
// Le moteur est Kokoro (voix `ff_siwis`), choisie A L'OREILLE parmi sept —
// c'est celle qui se rapprochait le plus de la voix d'origine. On y perd en
// qualite : ElevenLabs tourne sur des GPU de serveur. On y gagne l'absence de
// cle, de quota, de reseau — et la voix ne quitte plus l'ordinateur.
function requestSpeech(text) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ input: text });
    const chemin = '/v1/audio/speech';

    console.info('[NOVA] Synthese demandee a Nova Core');
    console.info('        URL    : http://127.0.0.1:8100' + chemin);
    console.info('        Texte  : ' + text.length + ' caracteres');

    const req = http.request({
      hostname: '127.0.0.1',
      port: 8100,
      path: chemin,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'audio/wav',
        'Content-Length': Buffer.byteLength(body),
      },
      // ⚠️ TRENTE SECONDES, ET PAS QUINZE COMME POUR ELEVENLABS.
      //
      // Un service distant repond en ~300 ms ou pas du tout. Un modele local
      // doit d'abord etre LU DEPUIS LE DISQUE au premier appel — plusieurs
      // secondes, une seule fois par session. Garder le delai de l'API ferait
      // echouer la premiere phrase de chaque session, c'est-a-dire justement
      // celle qu'on entend.
      timeout: 30000,
    }, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        if (res.statusCode !== 200) {
          // L'etiquette RESUME, elle ne remplace pas. Nova Core renvoie la
          // cause exacte ; l'effacer nous avait deja coute trois tours de
          // diagnostic sur un quota pris pour une cle invalide.
          const brut = buf.toString('utf8').slice(0, 300);
          let detail = brut;
          if (res.statusCode === 503) detail = 'synthese locale non installee';
          if (res.statusCode === 400) detail = 'texte vide ou absent';
          if (detail !== brut) detail += ' — ' + brut;
          console.error('[NOVA] Nova Core a REFUSE la synthese : HTTP '
            + res.statusCode + ' — ' + detail);
          return reject(new Error(`HTTP ${res.statusCode} — ${detail}`));
        }
        console.info('[NOVA] Audio successfully received — ' + Math.round(buf.length/1024) + ' Ko');
        resolve(buf);
      });
    });

    req.on('timeout', () => {
      req.destroy(new Error('Nova Core n\\'a pas repondu en 30 s — est-il lance ? (make serve)'));
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}'''


def _fin_de_fonction(texte: str, depart: int) -> int | None:
    """Index juste apres l'accolade fermante de la fonction ouverte a `depart`.

    Compteur d'accolades qui ignore chaines, commentaires et gabarits. On
    verifie ensuite avec `node --check` : c'est la verification qui rend
    l'operation acceptable, pas la finesse du comptage.
    """
    profondeur = 0
    i = texte.index("{", depart)
    n = len(texte)
    while i < n:
        c = texte[i]
        if c == "/" and i + 1 < n:
            if texte[i + 1] == "/":
                i = texte.find("\n", i)
                if i == -1:
                    return None
                continue
            if texte[i + 1] == "*":
                fin = texte.find("*/", i + 2)
                if fin == -1:
                    return None
                i = fin + 2
                continue
        if c in "\"'`":
            fermeture, i = c, i + 1
            while i < n:
                if texte[i] == "\\":
                    i += 2
                    continue
                if texte[i] == fermeture:
                    break
                i += 1
            if i >= n:
                return None
            i += 1
            continue
        if c == "{":
            profondeur += 1
        elif c == "}":
            profondeur -= 1
            if profondeur == 0:
                return i + 1
        i += 1
    return None


def brancher(source: str) -> tuple[str, list[str]]:
    faits: list[str] = []

    if "'/v1/audio/speech'" in source:
        return source, []

    # 1. `http` n'etait pas importe : on ne parlait qu'a l'exterieur.
    if "require('http')" not in source:
        source = source.replace(
            "const https = require('https');",
            "const https = require('https');\n"
            "// Nova Core est sur la machine : http, pas https. Le module manquait\n"
            "// parce qu'on ne parlait jusqu'ici qu'a des serveurs distants.\n"
            "const http = require('http');",
            1,
        )
        faits.append("module `http` importe")

    # 2. Le corps de `requestSpeech`, et lui seul.
    debut = source.find("function requestSpeech(")
    if debut == -1:
        return source, faits
    fin = _fin_de_fonction(source, debut)
    if fin is None:
        return source, faits

    # On remonte au commentaire d'en-tete pour ne pas laisser une description
    # de l'ancien appel au-dessus du nouveau : un commentaire qui ment est
    # pire qu'un commentaire absent.
    tete = source.rfind("\n// ── Appel à l'API ──", 0, debut)
    if tete == -1:
        tete = source.rfind("\n\n", 0, debut)
    source = source[: tete + 1].rstrip() + "\n\n" + NOUVELLE + source[fin:]
    faits.append("`requestSpeech` appelle Nova Core")

    return source, faits


def main() -> int:
    defaut = Path.home() / "Desktop" / "nova-project"
    racine = Path(sys.argv[1]) if len(sys.argv) > 1 else defaut
    chemin = racine / "electron" / "tts.js"

    if not chemin.is_file():
        print(f"✗ introuvable : {chemin}", file=sys.stderr)
        return 1

    original = chemin.read_text(encoding="utf-8")
    modifie, faits = brancher(original)

    if not faits:
        print("Rien a faire — l'application parle deja a Nova Core.")
        return 0

    sauvegarde = chemin.with_suffix(".js.avant-voix-locale")
    if not sauvegarde.exists():
        sauvegarde.write_text(original, encoding="utf-8")
    chemin.write_text(modifie, encoding="utf-8")

    verif = subprocess.run(["node", "--check", str(chemin)], capture_output=True, text=True)
    if verif.returncode != 0:
        chemin.write_text(original, encoding="utf-8")
        print("✗ branchement annule : le fichier ne parsait plus", file=sys.stderr)
        if verif.stderr:
            print(f"  {verif.stderr.strip().splitlines()[0]}", file=sys.stderr)
        return 1

    for fait in faits:
        print(f"  ✓ {fait}")

    # ⚠️ LE CACHE CONTIENT L'ANCIENNE VOIX, EN MP3.
    #
    # Sans ce vidage, l'intro « Bonjour Monsieur Kozlowski » continuerait de
    # sortir en ElevenLabs — elle est en cache — pendant que tout le reste
    # parlerait en Kokoro. Deux voix dans la meme session, et une cause
    # introuvable : le cache ne se voit pas dans le code.
    cache = Path.home() / "Library" / "Application Support" / "nova-desktop" / "voice-cache"
    if cache.is_dir():
        nombre = len(list(cache.iterdir()))
        shutil.rmtree(cache, ignore_errors=True)
        cache.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ cache vide ({nombre} fichier(s) de l'ancienne voix)")

    print(f"\n✓ L'application parle maintenant a Nova Core. Sauvegarde : {sauvegarde}")
    print("  Relance-la, puis cherche cette ligne :")
    print("    [NOVA] Synthese demandee a Nova Core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
