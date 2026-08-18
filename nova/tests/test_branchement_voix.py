"""Le branchement de l'application sur la voix locale.

`electron/tts.js` est bien decoupe : `requestSpeech(text)` est la SEULE fonction
qui parle au fournisseur de voix. Le cache disque, le prechauffage, `speak()` et
le repli sur la voix systeme l'entourent sans savoir a qui elle s'adresse.

Ce banc verifie qu'on remplace ce seul corps — et rien d'autre. Reecrire
davantage serait plus rapide a taper et bien plus long a reparer.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "brancher_voix", RACINE / "scripts" / "brancher-voix-locale.py"
)
brancher_voix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brancher_voix)


AVANT = """const https = require('https');

function readCache(text) {
  return null;
}

// ── Appel à l'API ──
// On utilise l'endpoint /stream : les premiers octets arrivent bien plus vite.
function requestSpeech(text) {
  return new Promise((resolve, reject) => {
    if (!apiKey) return reject(new Error('clé API absente'));
    const chemin = `/v1/text-to-speech/${config.voiceId}/stream`;
    const req = https.request({ hostname: 'api.elevenlabs.io' }, (res) => {
      res.on('end', () => { resolve(Buffer.concat(chunks)); });
    });
    req.end();
  });
}

async function speak(text) {
  return await requestSpeech(text);
}
"""


def test_seule_requestSpeech_est_remplacee():
    apres, faits = brancher_voix.brancher(AVANT)

    assert "'/v1/audio/speech'" in apres
    assert "api.elevenlabs.io" not in apres
    # Ce qui entoure ne bouge pas : c'est tout l'interet de la couture choisie.
    assert "async function speak(text) {\n  return await requestSpeech(text);\n}" in apres
    assert "function readCache(text) {\n  return null;\n}" in apres
    assert faits


def test_le_module_http_est_ajoute():
    """Il manquait : on ne parlait jusqu'ici qu'a des serveurs distants."""
    apres, _ = brancher_voix.brancher(AVANT)

    assert "const http = require('http');" in apres
    assert "const https = require('https');" in apres, "https sert peut-etre ailleurs"


def test_le_commentaire_de_l_ancien_appel_disparait():
    """Un commentaire qui ment est pire qu'un commentaire absent.

    « On utilise l'endpoint /stream » decrivait ElevenLabs. Le laisser au-dessus
    d'un appel a Nova Core enverrait le prochain lecteur chercher un endpoint
    qui n'existe plus.
    """
    apres, _ = brancher_voix.brancher(AVANT)

    assert "/stream" not in apres
    assert "Appel a Nova Core" in apres


def test_le_delai_passe_a_trente_secondes():
    """⚠️ QUINZE SECONDES FERAIENT ECHOUER LA PREMIERE PHRASE DE CHAQUE SESSION.

    Un service distant repond en ~300 ms ou pas du tout. Un modele local doit
    d'abord etre lu depuis le disque — plusieurs secondes, une fois par session,
    et c'est justement la phrase qu'on entend.
    """
    apres, _ = brancher_voix.brancher(AVANT)

    assert "timeout: 30000" in apres


def test_relancer_ne_rebranche_pas():
    une_fois, _ = brancher_voix.brancher(AVANT)
    deux_fois, faits = brancher_voix.brancher(une_fois)

    assert deux_fois == une_fois
    assert faits == []


def test_un_fichier_sans_requestSpeech_n_est_pas_touche():
    etranger = "const https = require('https');\nfunction autre() { return 1; }\n"
    apres, faits = brancher_voix.brancher(etranger)

    assert "requestSpeech" not in apres
    assert "'/v1/audio/speech'" not in apres
    assert faits == ["module `http` importe"]
