"""Le message d'erreur que l'application effaçait.

⚠️ CE FICHIER GARDE TROIS ALLERS-RETOURS DE DIAGNOSTIC PERDUS.

`electron/tts.js` lisait le corps de la reponse d'ElevenLabs, puis l'ecrasait :

    let detail = buf.toString('utf8').slice(0, 300);         // la verite
    if (res.statusCode === 401) detail = 'cle API refusee';  // ... remplacee

L'application affichait donc « HTTP 401 — cle API refusee » a chaque echec. Or
ElevenLabs renvoie 401 pour au moins trois causes sans rapport entre elles :

    invalid_api_key             la cle est fausse
    quota_exceeded              la cle est bonne, le compte est a sec
    detected_unusual_activity   le compte est suspendu

C'etait la deuxieme, et le message le disait mot pour mot :

    "This request exceeds your quota of 10000. You have 3 credits remaining,
     while 10 credits are required for this request."

On a change la cle deux fois, verifie les permissions, teste l'URL au curl et
lu le code de lecture du fichier — pour une information que le programme tenait
dans une variable et jetait a la ligne suivante.

LA REGLE QUE CE BANC PROTEGE

Un programme peut RESUMER ce qu'il a recu, jamais l'EFFACER. Le resume sert
l'utilisateur pressé ; l'original sert celui qui cherche — et c'est toujours le
second qui en a besoin. « quota ElevenLabs depasse » reste plus lisible qu'un
JSON : on garde donc les deux, l'etiquette PUIS le brut.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "reparer_tts", RACINE / "scripts" / "reparer-tts-diagnostic.py"
)
reparer_tts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reparer_tts)


#: Le bloc tel qu'il etait sur la machine, avant correction.
ORIGINE = """\
        const buf = Buffer.concat(chunks);
        if (res.statusCode !== 200) {
          let detail = buf.toString('utf8').slice(0, 300);
          if (res.statusCode === 401) detail = 'clé API refusée';
          if (res.statusCode === 404) detail = 'Voice ID introuvable';
          if (res.statusCode === 429) detail = 'quota ElevenLabs dépassé';
          if (res.statusCode === 400 && /output_format|format/i.test(detail))
            detail = 'format audio refusé — les débits supérieurs à 128 kbps exigent un abonnement payant';
          console.error('[NOVA] ElevenLabs a REFUSÉ la requête : HTTP ' + res.statusCode + ' — ' + detail);
          return reject(new Error(`HTTP ${res.statusCode} — ${detail}`));
        }
"""

#: La rustine posee en urgence pendant l'enquete, sur le seul cas 401. Le
#: correctif doit converger vers le meme resultat depuis les deux etats — sinon
#: il depend de l'ordre dans lequel on a bricole, ce qui n'est pas une propriete.
RUSTINE = ORIGINE.replace(
    "detail = 'clé API refusée';", "detail = 'clé API refusée — ' + detail;"
)


def test_le_corps_brut_est_conserve():
    corrige, faits = reparer_tts.reparer(ORIGINE)

    assert "const brut = buf.toString('utf8').slice(0, 300);" in corrige
    assert "if (detail !== brut) detail += ' — ' + brut;" in corrige
    assert faits


def test_l_etiquette_lisible_survit():
    """On ajoute le brut, on ne supprime pas la traduction."""
    corrige, _ = reparer_tts.reparer(ORIGINE)

    for etiquette in ("clé API refusée", "Voice ID introuvable", "quota ElevenLabs dépassé"):
        assert f"detail = '{etiquette}';" in corrige


def test_le_test_du_code_400_lit_le_brut():
    """Sinon il examine parfois une etiquette qu'on vient d'ecrire soi-meme."""
    corrige, _ = reparer_tts.reparer(ORIGINE)

    assert "/output_format|format/i.test(brut)" in corrige
    assert "/output_format|format/i.test(detail)" not in corrige


def test_les_deux_etats_de_depart_convergent():
    depuis_origine, _ = reparer_tts.reparer(ORIGINE)
    depuis_rustine, _ = reparer_tts.reparer(RUSTINE)

    assert depuis_origine == depuis_rustine


def test_relancer_ne_change_plus_rien():
    """Un outil qui annonce du travail sans en faire apprend a ne plus etre cru."""
    une_fois, _ = reparer_tts.reparer(ORIGINE)
    deux_fois, faits = reparer_tts.reparer(une_fois)

    assert deux_fois == une_fois
    assert faits == [], f"annonce des corrections imaginaires : {faits}"


def test_un_fichier_sans_le_motif_n_est_pas_touche():
    etranger = "function autreChose() { return 1; }\n"
    corrige, faits = reparer_tts.reparer(etranger)

    assert corrige == etranger
    assert faits == []
