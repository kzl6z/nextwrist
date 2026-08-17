"""Le retrait des modules colles a la main dans script.js.

⚠️ CE FICHIER GARDE UN GARDE-FOU QUI NE GARDAIT RIEN.

Chaque module refuse de s'activer deux fois :

    if (window.__novaReveilVocal) return;
    window.__novaReveilVocal = true;

`test-doublon.cjs` le verifie, et il passe. On en avait conclu qu'un doublon ne
coutait plus rien, et `make ui` se contentait donc d'AVERTIR. Puis la machine
reelle a rendu ceci, apres un `make ui` qui avait affiche ses avertissements :

    [NOVA/reveil] ecoute par la parole active    script.js:3476
    [NOVA/reveil] ecoute par la parole active    script.js:4019
    Request sent to ElevenLabs (117 car.)        <- deux fois, MEME texte
    PLAYBACK BLOCKED: AbortError
    [VOIX] lecture echouee -> repli voix systeme

CE QUE LE BANC D'ESSAI NE POUVAIT PAS VOIR

Il chargeait deux fois LE MEME fichier. Or le drapeau est pose PAR LA COPIE
NEUVE, et les copies manuelles datent d'AVANT son existence : elles ne le posent
pas. L'ancienne s'active donc sans rien signaler, la neuve trouve le drapeau
absent, et s'active a son tour.

Le garde-fou protegeait une copie neuve d'une autre copie neuve — le seul cas
qui ne se produisait pas. Un test qui ne fait s'affronter que la version
courante avec elle-meme ne peut pas decouvrir ca ; il faut simuler l'ANCIENNE,
celle qui ignore la convention.

C'est ce que fait ce fichier, et c'est pour ca qu'il ne remplace pas
`test-doublon.cjs` : les deux repondent a des questions differentes.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
MODULES = RACINE / "ui" / "electron"

_spec = importlib.util.spec_from_file_location(
    "retirer_copies", RACINE / "scripts" / "retirer-copies-manuelles.py"
)
retirer_copies = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(retirer_copies)


APPLICATION = """// application d'origine — ne doit jamais disparaitre
let appState = 'IDLE';
function traiterDemande(t) { return t; }
let cycleVocal = async function () {};
let startWakeLoop, stopWakeLoop, wakeOn;
"""


def _script_avec_copies() -> str:
    """script.js tel qu'il etait sur la machine : l'app, puis les trois modules."""
    colles = "\n".join(
        (MODULES / nom).read_text(encoding="utf-8")
        for nom in ("reveil-vocal.js", "parole-en-flux.js", "rendu-econome.js")
    )
    return APPLICATION + "\n" + colles


def test_les_trois_copies_partent():
    source = _script_avec_copies()
    nettoye, retires = retirer_copies.retirer(source)

    assert retires == 3
    for empreinte in ("reveilLocal", "paroleEnFlux", "renduEconome"):
        assert f"function {empreinte}(" not in nettoye


def test_le_code_de_l_application_survit():
    """Le vrai risque du retrait : emporter du code qui n'est pas a nous."""
    nettoye, _ = retirer_copies.retirer(_script_avec_copies())

    assert "application d'origine" in nettoye
    assert "function traiterDemande" in nettoye
    assert "let startWakeLoop, stopWakeLoop, wakeOn;" in nettoye


def test_le_resultat_reste_du_javascript_valide(tmp_path):
    """Decouper avec un compteur de parentheses n'est pas analyser. On verifie."""
    if shutil.which("node") is None:
        pytest.skip("node absent")

    chemin = tmp_path / "script.js"
    nettoye, _ = retirer_copies.retirer(_script_avec_copies())
    chemin.write_text(nettoye, encoding="utf-8")

    verif = subprocess.run(["node", "--check", str(chemin)], capture_output=True)
    assert verif.returncode == 0, verif.stderr.decode()


def test_un_fichier_sans_copie_n_est_pas_touche():
    nettoye, retires = retirer_copies.retirer(APPLICATION)
    assert retires == 0
    assert nettoye == APPLICATION


def test_une_iife_desequilibree_ne_fait_rien_plutot_que_de_mutiler():
    """Mieux vaut du code mort qu'une application qui ne demarre plus."""
    tronque = APPLICATION + "\n(function renduEconome() {\n  if (true) {\n"
    nettoye, retires = retirer_copies.retirer(tronque)

    assert retires == 0
    assert nettoye == tronque


def test_les_parentheses_des_chaines_et_regex_ne_comptent_pas():
    """`parole-en-flux.js` contient une regex ; une chaine peut contenir « ) »."""
    piege = (
        APPLICATION
        + "\n(function renduEconome() {\n"
        + "  const s = 'une parenthese ) dans une chaine';\n"
        + "  const r = /[)(]/g;\n"
        + "  // un commentaire avec ) dedans\n"
        + "  return s.replace(r, '');\n"
        + "})();\n"
        + "const apres = 1;\n"
    )
    nettoye, retires = retirer_copies.retirer(piege)

    assert retires == 1
    assert "renduEconome" not in nettoye
    assert "const apres = 1;" in nettoye
