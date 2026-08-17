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

# ── 2b. Les copies collées A LA MAIN, avant que ce script n'existe ───────
#
# ⚠️ C'EST LE DÉFAUT QUI A COÛTÉ LE PLUS CHER, ET IL ÉTAIT DANS CE FICHIER.
#
# Les marqueurs protégeaient ce script de LUI-MÊME : réinstaller n'empilait
# pas. Ils ne protégeaient de rien d'autre. Sur la machine réelle, les
# modules avaient été collés à la main avant que `make ui` n'existe ; le
# script a ajouté sa copie à côté, et tout s'est mis à tourner en double :
#
#     deux « cadence adaptative »  -> rAF enveloppé deux fois
#     deux « parole en flux »      -> deux requêtes de synthèse par phrase,
#                                     lectures concurrentes, AbortError,
#                                     repli sur la voix du système
#
# ⚠️ ON A CRU QUE LE GARDE-FOU SUFFISAIT. LA MACHINE A DIT NON.
#
# Chaque module refuse de s'activer deux fois, donc ce script se contentait
# d'AVERTIR quand il trouvait une copie manuelle — « ça ne casse plus rien,
# c'est juste du code mort ». Releve sur la machine reelle, apres un
# `make ui` qui affichait pourtant ses trois avertissements sans broncher :
#
#     [NOVA/reveil] ecoute par la parole active    script.js:3476
#     [NOVA/reveil] ecoute par la parole active    script.js:4019
#     Request sent to ElevenLabs (117 car.)        <- deux fois, MEME texte
#     PLAYBACK BLOCKED: AbortError
#     [VOIX] lecture echouee -> repli voix systeme
#
# Le drapeau est POSE PAR LA COPIE NEUVE. Les copies manuelles datent d'AVANT
# son existence : elles ne le posent pas. L'ancienne s'active donc en premier
# sans rien dire, la neuve trouve le drapeau absent, et s'active a son tour.
# Le garde-fou protegeait une copie neuve d'une autre copie neuve — le seul
# cas qui ne se produisait pas.
#
# On RETIRE donc, au lieu d'avertir. Un avertissement demande a quelqu'un de
# faire le travail plus tard, a la main, dans un fichier de 4000 lignes : la
# meme erreur que le tableau du README qui a laisse `rendu-econome.js` sur
# l'etagere pendant des semaines.
#
# Le retrait est verifie par `node --check` et annule s'il casse le fichier.
#
# ⚠️ ON COMPTE ICI, ET PAS PLUS HAUT. Notre propre bloc vient d'être retiré
# par le python ci-dessus ; compter avant l'aurait fait dénoncer comme une
# copie manuelle dès la deuxième installation — un avertissement qui accuse
# celui qui le lit ne sert qu'à le faire ignorer.
#
# ⚠️ PAS DE `case` DANS UN `$( )`. macOS LIVRE BASH 3.2.
#
# La première version écrivait `empreinte=$(case "$module" in …)`. Bash 3.2
# prend la parenthèse fermante d'un motif de `case` pour la fin de la
# substitution :
#
#     installer-ui.sh: line 79: syntax error near unexpected token ';;'
#
# Ça passait ici (bash 5) et échouait chez l'utilisateur — c'est-à-dire au
# seul endroit qui compte. Deux listes parallèles évitent la construction au
# lieu de la contourner.
MODULES="reveil-vocal.js parole-en-flux.js rendu-econome.js"
EMPREINTES="reveilLocal paroleEnFlux renduEconome"

avertis=0
rang=1
for module in $MODULES; do
  empreinte=$(echo "$EMPREINTES" | cut -d' ' -f"$rang")
  rang=$((rang + 1))
  copies=$(grep -c "function $empreinte" "$SCRIPT" || true)
  if [ "${copies:-0}" -gt 0 ]; then
    echo "  ⚠ $module etait colle a la main ($copies copie(s)) — retrait"
    avertis=1
  fi
done

if [ "$avertis" -ne 0 ]; then
  python3 "$(dirname "${BASH_SOURCE[0]}")/retirer-copies-manuelles.py" "$SCRIPT" || {
    echo "  ⚠ retrait impossible — les copies manuelles restent en place."
    echo "    Elles vont s'executer EN PLUS des nouvelles : deux ecoutes, deux"
    echo "    voix. Retire-les a la main, ou restaure $SCRIPT.avant-nova"
  }
fi

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

# ⚠️ VERIFIER LA PRESENCE NE VERIFIE PAS L'UNICITE — ET C'EST L'UNICITE QUI
# MANQUAIT.
#
# Cette section relisait le fichier pour prouver que chaque module etait bien
# la. Elle passait au vert avec DEUX copies de chacun, puisque deux copies sont
# au moins une. L'installation etait donc declaree reussie pendant que Nova
# ouvrait deux micros et commandait deux fois la meme synthese vocale.
#
# Compter est aussi peu couteux que chercher, et repond a la vraie question.
rang=1
for module in $MODULES; do
  empreinte=$(echo "$EMPREINTES" | cut -d' ' -f"$rang")
  rang=$((rang + 1))
  copies=$(grep -c "function $empreinte" "$SCRIPT" || true)
  if [ "${copies:-0}" -ne 1 ]; then
    echo "  ✗ $module present en ${copies:-0} exemplaire(s) — il en faut exactement 1"
    manquants=1
  fi
done

if [ "$manquants" -ne 0 ]; then
  echo ""
  echo "✗ Installation incomplete. Sauvegarde : $SCRIPT.avant-nova"
  exit 1
fi

echo ""
if [ "$avertis" -ne 0 ]; then
  echo "D'anciennes copies collées à la main ont été retirées."
  echo "  Elles s'exécutaient EN PLUS des nouvelles : deux écoutes du micro,"
  echo "  deux requêtes de synthèse par phrase, et cette « deuxième voix » qui"
  echo "  répondait par-dessus Nova."
  echo "  Sauvegarde avant retrait : $SCRIPT.avant-nova"
  echo ""
fi
echo "✓ Les quatre modules sont en place."
echo "  Relance l'application, puis cherche cette ligne dans la console :"
echo "    [NOVA/rendu] cadence adaptative — 4 images/s pendant qu'elle réfléchit"
echo "  Si elle n'y est pas, le rendu econome ne tourne pas."
