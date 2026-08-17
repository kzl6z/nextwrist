#!/usr/bin/env python3
"""Retirer de script.js les modules Nova colles a la main.

⚠️ POURQUOI SIGNALER NE SUFFISAIT PAS — ET POURQUOI LE GARDE-FOU NON PLUS.

Chaque module refuse de s'activer deux fois :

    if (window.__novaReveilVocal) return;      // dans la copie NEUVE
    window.__novaReveilVocal = true;

On en avait conclu qu'un doublon ne coutait plus rien, et `installer-ui.sh` se
contentait donc d'AVERTIR quand il trouvait une copie manuelle. C'etait faux, et
la machine reelle l'a montre :

    [NOVA/reveil] ecoute par la parole active    script.js:3476
    [NOVA/reveil] ecoute par la parole active    script.js:4019   <- deux fois
    Request sent to ElevenLabs (117 car.)                          <- deux fois
    PLAYBACK BLOCKED: AbortError — play() interrupted by pause()
    [VOIX] lecture echouee -> repli voix systeme

Le drapeau est POSE PAR LA COPIE NEUVE. Les copies manuelles, elles, datent
d'AVANT son existence : elles ne le posent pas. L'ancienne s'active donc en
premier sans rien signaler, la neuve trouve le drapeau absent, et s'active a son
tour. Le garde-fou protege une copie neuve d'une autre copie neuve — c'est-a-dire
le seul cas qui ne se produisait pas.

Un garde-fou qui suppose que l'autre copie lui ressemble ne garde rien. La seule
defense qui tienne est de RETIRER le code mort.

COMMENT, SANS CASSER script.js

On repere `(function <nom>() {` et on compte les parentheses jusqu'a l'equilibre,
en ignorant celles qui vivent dans une chaine, un commentaire ou une expression
reguliere (`parole-en-flux.js` en contient une).

Puis on VERIFIE avec `node --check`. Si le fichier ne parse plus, on restaure et
on ne touche a rien : mieux vaut du code mort qu'une application qui ne demarre
pas. C'est cette verification qui rend l'operation acceptable — pas la finesse du
decoupage.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

#: Nom de la fonction englobante de chaque module, dans l'ordre d'installation.
EMPREINTES = ("reveilLocal", "paroleEnFlux", "renduEconome")

#: Caracteres apres lesquels un « / » ouvre une expression reguliere et non une
#: division. Liste volontairement large : se tromper ici ne fait que decaler le
#: comptage, et `node --check` rattrape.
AVANT_REGEX = "(,=:[!&|?{};+-*%~^\n"


def _fin_de_liffe(texte: str, depart: int) -> int | None:
    """Index juste apres l'IIFE commencee a `depart`, ou None si desequilibree.

    `depart` doit pointer sur la parenthese ouvrante de `(function nom()`.
    """
    profondeur = 0
    i = depart
    n = len(texte)
    dernier_signifiant = ""

    while i < n:
        c = texte[i]

        # ── Commentaires ──
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
            # ── Expression reguliere ──
            if dernier_signifiant in AVANT_REGEX or dernier_signifiant == "":
                i += 1
                while i < n and texte[i] != "/":
                    if texte[i] == "\\":
                        i += 1
                    elif texte[i] == "\n":
                        return None  # une regex ne traverse pas une ligne
                    i += 1
                i += 1
                dernier_signifiant = "/"
                continue

        # ── Chaines ──
        if c in "\"'`":
            fermeture = c
            i += 1
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
            dernier_signifiant = fermeture
            continue

        # ── Parentheses ──
        if c == "(":
            profondeur += 1
        elif c == ")":
            profondeur -= 1
            if profondeur == 0:
                # On a ferme `(function ... )`. Reste l'appel : `();`
                j = i + 1
                while j < n and texte[j] in " \t\r\n":
                    j += 1
                if j < n and texte[j] == "(":
                    j += 1
                    while j < n and texte[j] in " \t\r\n":
                        j += 1
                    if j < n and texte[j] == ")":
                        j += 1
                while j < n and texte[j] in " \t\r\n;":
                    j += 1
                return j

        if not c.isspace():
            dernier_signifiant = c
        i += 1

    return None


def _debut_de_bloc(texte: str, position: int) -> int:
    """Recule jusqu'au debut du commentaire d'en-tete qui precede l'IIFE.

    Les modules sont precedes d'un long bandeau `// ═══...`. Le laisser derriere
    donnerait des centaines de lignes de commentaire orphelin decrivant du code
    absent — pire que du code mort, parce que ca se lit comme une specification.
    """
    debut_ligne = texte.rfind("\n", 0, position) + 1
    lignes = texte[:debut_ligne].split("\n")
    garde = len(lignes) - 1
    i = garde - 1
    while i >= 0 and lignes[i].lstrip().startswith("//"):
        garde = i
        i -= 1
    return len("\n".join(lignes[:garde])) + (1 if garde else 0)


def retirer(source: str) -> tuple[str, int]:
    """Retourne (texte nettoye, nombre de copies retirees)."""
    retires = 0
    for nom in EMPREINTES:
        motif = f"(function {nom}("
        while (position := source.find(motif)) != -1:
            fin = _fin_de_liffe(source, position)
            if fin is None:
                break  # desequilibre : on n'y touche pas
            debut = _debut_de_bloc(source, position)
            source = source[:debut].rstrip() + "\n" + source[fin:].lstrip("\n")
            retires += 1
    return source, retires


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: retirer-copies-manuelles.py <script.js>", file=sys.stderr)
        return 2

    chemin = Path(sys.argv[1])
    original = chemin.read_text(encoding="utf-8")
    nettoye, retires = retirer(original)

    if retires == 0:
        return 0

    chemin.write_text(nettoye, encoding="utf-8")

    # ⚠️ LA VERIFICATION EST LA VRAIE SECURITE, PAS LE DECOUPAGE.
    #
    # On decoupe du JavaScript avec un compteur de parentheses. C'est
    # raisonnable, ce n'est pas un analyseur syntaxique. `node --check` l'est.
    # S'il refuse le resultat, on remet l'original : du code mort se supporte,
    # une application qui ne demarre plus non plus.
    verif = subprocess.run(
        ["node", "--check", str(chemin)], capture_output=True, text=True
    )
    if verif.returncode != 0:
        chemin.write_text(original, encoding="utf-8")
        print("  ⚠ retrait annule : le fichier ne parsait plus", file=sys.stderr)
        print(f"    {verif.stderr.strip().splitlines()[0] if verif.stderr else ''}",
              file=sys.stderr)
        return 1

    print(f"  ✓ {retires} copie(s) manuelle(s) retiree(s) de script.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
