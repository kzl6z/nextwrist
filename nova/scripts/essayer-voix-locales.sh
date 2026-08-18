#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════
#  ESSAYER LES VOIX LOCALES — écouter avant de choisir
#
#  POURQUOI CE SCRIPT EXISTE
#
#  La voix d'ElevenLabs a cessé de fonctionner sur un quota épuisé :
#
#      "This request exceeds your quota of 10000. You have 3 credits
#       remaining, while 10 credits are required for this request."
#
#  Dix mille crédits par mois, une réponse de Nova ~150 caractères : environ
#  soixante réponses mensuelles. Ce n'est pas une panne, c'est un plafond
#  structurel — et il tombait en silence, sur la voix du système, sans que
#  rien ne dise pourquoi.
#
#  ⚠️ CE QUE CE SCRIPT NE FERA PAS : ÉGALER ELEVENLABS.
#
#  Leurs modèles tournent sur des GPU de serveur. Ici on vise « bon », pas
#  « meilleur ». Le dire d'avance évite de chercher pendant deux jours un
#  réglage qui n'existe pas.
#
#  CE QU'IL FAIT
#
#  Il fabrique la MÊME phrase avec chaque moteur disponible et te laisse
#  écouter. Aucune fiche technique ne remplace l'oreille : c'est le même
#  principe que `bench_models.py`, qui a écarté qwen3:4b sur une mesure et
#  non sur ses caractéristiques annoncées.
#
#  Les trois familles essayées :
#
#      macOS    déjà installé, zéro Mo, zéro seconde  — la référence basse
#      Piper    ~60 Mo, quasi instantané sur M1       — le raisonnable
#      Kokoro   ~350 Mo + torch, plus lent            — le plus proche
#
#  Tout est installé DANS UN DOSSIER À PART. Rien ne touche l'environnement
#  de Nova : si tu n'aimes aucune de ces voix, tu supprimes le dossier et il
#  ne reste rien.
# ══════════════════════════════════════════════════════════════════════════
set -uo pipefail   # PAS de -e : un moteur qui échoue ne doit pas emporter les autres

RACINE="${1:-$HOME/Desktop/nova-voix}"
ESSAIS="$RACINE/essais"
VENV="$RACINE/venv"
VOIX="$RACINE/modeles"

# Deux phrases, choisies pour ce qu'elles révèlent :
#   — la première a des liaisons et un « où » accentué ;
#   — la seconde est une vraie réponse de Nova, avec un chiffre et une
#     ponctuation qui décide du rythme.
PHRASE1="Un trou noir est une région de l'espace où la gravité est si forte que rien ne s'en échappe."
PHRASE2="Il est deux heures. Tu devrais dormir, Hugo."

mkdir -p "$ESSAIS" "$VOIX"
echo "Dossier d'essai : $RACINE"
echo ""

# ── 1. Les voix macOS : déjà là, gratuites, illimitées ───────────────────
#
# On commence par elles parce qu'elles sont la vraie référence basse : si
# Piper ne fait pas mieux que Sandy, Piper n'a aucune raison d'exister ici.
echo "── Voix macOS ────────────────────────────────────────────"
if command -v say >/dev/null 2>&1; then
  for v in Sandy Shelley Amélie Thomas; do
    if say -v "$v" -o "$ESSAIS/macos-$v-1.aiff" "$PHRASE1" 2>/dev/null; then
      say -v "$v" -o "$ESSAIS/macos-$v-2.aiff" "$PHRASE2" 2>/dev/null
      echo "  ✓ $v"
    else
      echo "  – $v (absente de cette machine)"
    fi
  done
else
  echo "  ✗ commande « say » introuvable — ce script est prévu pour macOS"
fi
echo ""

# ── 2. L'environnement Python, à part ────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  echo "✗ « uv » introuvable. Installe-le :  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
[ -d "$VENV" ] || uv venv "$VENV" >/dev/null 2>&1
PY="$VENV/bin/python"

# ── 3. Piper ─────────────────────────────────────────────────────────────
#
# Le plus léger des deux, et de loin. Trois voix françaises valent d'être
# comparées : elles viennent de corpus différents, et l'écart entre elles est
# plus grand que ce qu'on imagine.
#
#   siwis   corpus de lecture, voix féminine posée
#   upmc    deux locuteurs — le 0 est féminin, le 1 masculin
#   mls     corpus de livres audio, plus de variété d'intonation
echo "── Piper ─────────────────────────────────────────────────"
if uv pip install --python "$PY" piper-tts >/dev/null 2>&1; then
  for modele in fr_FR-siwis-medium fr_FR-upmc-medium fr_FR-mls-medium; do
    printf "  %-22s " "$modele"
    if ! "$PY" -m piper.download_voices "$modele" --data-dir "$VOIX" >/dev/null 2>&1; then
      echo "téléchargement impossible"
      continue
    fi
    # `upmc` contient deux locuteurs ; on prend le premier, qui est féminin.
    if echo "$PHRASE1" | "$PY" -m piper -m "$modele" --data-dir "$VOIX" \
         -f "$ESSAIS/piper-$modele-1.wav" >/dev/null 2>&1; then
      echo "$PHRASE2" | "$PY" -m piper -m "$modele" --data-dir "$VOIX" \
         -f "$ESSAIS/piper-$modele-2.wav" >/dev/null 2>&1
      echo "✓"
    else
      echo "synthèse échouée"
    fi
  done
else
  echo "  ✗ installation de piper-tts impossible"
fi
echo ""

# ── 4. Kokoro ────────────────────────────────────────────────────────────
#
# ⚠️ IL A BESOIN D'espeak-ng, ET ÇA N'EST PAS DIT DANS SA DOCUMENTATION
# D'INSTALLATION.
#
# Sans lui, le français échoue à la phonémisation avec une erreur qui parle
# de tout sauf de ça. On vérifie donc AVANT d'installer 300 Mo de modèle.
echo "── Kokoro ────────────────────────────────────────────────"
if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "  ⚠ espeak-ng absent — indispensable au français."
  echo "    Installe-le puis relance :   brew install espeak-ng"
elif uv pip install --python "$PY" kokoro soundfile >/dev/null 2>&1; then
  "$PY" - "$ESSAIS" "$PHRASE1" "$PHRASE2" <<'PY' || echo "  ✗ synthèse Kokoro échouée"
import sys, warnings
warnings.filterwarnings("ignore")
import soundfile as sf
from kokoro import KPipeline

sortie, phrases = sys.argv[1], sys.argv[2:]
# 'f' = français. La voix `ff_siwis` est la seule voix française de Kokoro
# a ce jour — feminine, meme corpus que le `siwis` de Piper, ce qui rend la
# comparaison des deux moteurs particulierement lisible : meme locutrice,
# meme materiau, seule la synthese change.
pipeline = KPipeline(lang_code="f")
for n, phrase in enumerate(phrases, start=1):
    morceaux = [audio for _, _, audio in pipeline(phrase, voice="ff_siwis")]
    if not morceaux:
        continue
    import numpy as np
    sf.write(f"{sortie}/kokoro-ff_siwis-{n}.wav", np.concatenate(morceaux), 24000)
    print(f"  ✓ phrase {n}")
PY
else
  echo "  ✗ installation de kokoro impossible"
fi
echo ""

# ── 5. Écouter ───────────────────────────────────────────────────────────
echo "── Résultat ──────────────────────────────────────────────"
nombre=$(find "$ESSAIS" -type f \( -name '*.wav' -o -name '*.aiff' \) | wc -l | tr -d ' ')
echo "  $nombre extraits dans $ESSAIS"
echo ""
echo "  Écoute-les dans l'ordre, la MÊME phrase à chaque fois :"
find "$ESSAIS" -name '*-1.*' | sort | sed 's|.*/|    |'
echo ""
echo "  Poids sur la machine — ça compte autant que le rendu, sur 8 Go :"
du -sh "$VOIX" 2>/dev/null | sed 's|^|    modeles  |'
du -sh "$VENV" 2>/dev/null | sed 's|^|    python   |'
echo ""
[ -d "$ESSAIS" ] && open "$ESSAIS" 2>/dev/null
echo "  Pour tout supprimer si rien ne te convient :  rm -rf $RACINE"
