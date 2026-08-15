#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════
#  INSTALLER LES MODULES NOVA DANS L'APPLICATION DE BUREAU
#
#  POURQUOI CE SCRIPT EXISTE, ET CE QU'IL REPARE
#
#  Trois des quatre modules devaient etre « colles a la fin de script.js », a
#  la main, apres chaque `git pull`. C'etait ecrit dans un tableau du README
#  et nulle part ailleurs. Resultat previsible : seul `brain.js`, dont
#  l'installation etait rappelee a chaque fois, a jamais ete installe.
#
#  `rendu-econome.js` est reste sur l'etagere pendant que la machine se
#  figeait a chaque reponse — c'est-a-dire que le correctif etait ecrit,
#  mesure, teste, et inactif. Une instruction qu'il faut se rappeler
#  d'appliquer n'est pas une instruction : c'est un piege a retardement.
#
#  CE QU'IL GARANTIT
#
#    — idempotent : le relancer dix fois donne le meme fichier qu'une fois ;
#    — reversible : `script.js` est sauvegarde avant toute ecriture ;
#    — verifiable : il dit ce qui est actif, et se termine en erreur si non.
# ══════════════════════════════════════════════════════════════════════════
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../ui/electron" && pwd)"
CIBLE="${1:-$HOME/Desktop/nova-project}"

DEBUT="// ─── NOVA : début des modules installés automatiquement ───"
FIN="// ─── NOVA : fin des modules installés automatiquement ───"

if [ ! -d "$CIBLE" ]; then
  echo "✗ Application introuvable : $CIBLE"
  echo "  Usage : $0 [chemin/vers/nova-project]"
  exit 1
fi

echo "Application : $CIBLE"

# ── 1. brain.js : un fichier a lui seul, simple copie ────────────────────
mkdir -p "$CIBLE/electron"
cp "$SOURCE/brain.js" "$CIBLE/electron/brain.js"
echo "  ✓ electron/brain.js"

# ── 2. Les modules qui s'ajoutent a script.js ────────────────────────────
#
# On les REMPLACE en bloc entre deux marqueurs plutot que d'ajouter a la
# suite. Sans ces marqueurs, chaque installation empilait une copie de plus,
# et trois `rendu-econome` charges en meme temps enveloppent
# `requestAnimationFrame` trois fois — soit trois fois le travail qu'on
# cherchait a supprimer.
SCRIPT="$CIBLE/script.js"
if [ ! -f "$SCRIPT" ]; then
  echo "✗ $SCRIPT introuvable — est-ce bien le dossier de l'application ?"
  exit 1
fi

cp "$SCRIPT" "$SCRIPT.avant-nova"

python3 - "$SCRIPT" "$DEBUT" "$FIN" <<'PY'
import sys, pathlib
chemin, debut, fin = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
texte = chemin.read_text(encoding="utf-8")
if debut in texte and fin in texte:
    avant = texte.split(debut)[0]
    apres = texte.split(fin, 1)[1]
    chemin.write_text(avant.rstrip() + "\n" + apres.lstrip("\n"), encoding="utf-8")
PY

{
  echo ""
  echo "$DEBUT"
  echo "// Ne pas modifier a la main : ce bloc est reecrit par scripts/installer-ui.sh"
  for module in reveil-vocal.js parole-en-flux.js rendu-econome.js; do
    echo ""
    echo "// ── $module ──"
    cat "$SOURCE/$module"
  done
  echo "$FIN"
} >> "$SCRIPT"

for module in reveil-vocal.js parole-en-flux.js rendu-econome.js; do
  echo "  ✓ script.js ← $module"
done

# ── 3. Verification ───────────────────────────────────────────────────────
#
# Copier n'est pas installer. On relit le fichier ecrit : c'est la seule
# preuve qui vaille, et c'est precisement l'etape qui manquait.
manquants=0
for module in reveil-vocal.js parole-en-flux.js rendu-econome.js; do
  grep -q "── $module ──" "$SCRIPT" || { echo "  ✗ $module ABSENT"; manquants=1; }
done
grep -q "analyserEnFlux" "$CIBLE/electron/brain.js" || { echo "  ✗ brain.js incomplet"; manquants=1; }

if [ "$manquants" -ne 0 ]; then
  echo ""
  echo "✗ Installation incomplete. Sauvegarde : $SCRIPT.avant-nova"
  exit 1
fi

echo ""
echo "✓ Les quatre modules sont en place."
echo "  Relance l'application, puis cherche cette ligne dans la console :"
echo "    [NOVA/rendu] cadence adaptative — 4 images/s pendant qu'elle réfléchit"
echo "  Si elle n'y est pas, le rendu econome ne tourne pas."
