"""Emballer le corpus prepare pour l'entrainer ailleurs.

    uv run python scripts/exporter_pour_affinage.py

POURQUOI L'ENTRAINEMENT NE SE FAIT PAS ICI

Affiner un modele VITS demande des milliers de passes sur le corpus. Sur le M1
de cette machine, en calcul flottant et sans CUDA, ca se compte en JOURS — et
pendant tout ce temps Nova n'aurait plus de memoire vive. Sur un GPU gratuit de
Colab, deux a quatre heures suffisent.

Ce script produit donc une archive autonome : les WAV, la fiche, et un fichier
`COMMANDES.txt` qui contient les lignes exactes a coller. Tout ce qui peut etre
verifie l'est AVANT le depart — une erreur de format decouverte apres trois
heures de GPU coute trois heures.

⚠️ CE QU'IL VERIFIE, ET POURQUOI CHAQUE POINT A DEJA COUTE QUELQUE CHOSE

    l'alignement audio/texte   un corpus desaligne fait apprendre des sons a un
                               texte qui n'est pas le leur, sans que rien ne le
                               signale a l'entrainement
    le taux d'echantillonnage  22 050 Hz : un modele entraine sur du 16 kHz
                               reechantillonne sonne sourd, et tous les
                               fichiers restent valides
    la duree de parole         un affinage sous-alimente ne rate pas
                               bruyamment, il rend une voix approximative
"""

from __future__ import annotations

import sys
import wave
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "data" / "voix-clone-prete"
ARCHIVE = RACINE / "data" / "voix-nova-affinage.zip"

TAUX_ATTENDU = 22050
MINUTES_MIN = 12

#: Le point de depart de l'affinage. On ne repart pas de zero : le modele
#: connait deja le francais, l'affinage ne fait que deplacer le timbre. C'est
#: ce qui permet de s'en tirer avec quinze minutes de voix au lieu de dix
#: heures.
BASE = "fr_FR-siwis-medium"

COMMANDES = """\
# ══════════════════════════════════════════════════════════════════════════
#  AFFINER LA VOIX DE NOVA — a coller dans un carnet Google Colab
#
#  Avant de commencer : Execution > Modifier le type d'execution > GPU T4.
#  Sans GPU, ces commandes tournent mais mettront des jours.
#
#  Duree attendue : 2 a 4 heures. Colab coupe les sessions inactives, alors
#  garde l'onglet ouvert. Les points de reprise sont ecrits regulierement :
#  si la session tombe, on repart du dernier au lieu de tout refaire.
# ══════════════════════════════════════════════════════════════════════════

# ── 1. Installer ──────────────────────────────────────────────────────────
!pip install -q "piper-tts[train]" cython

# ── 1 bis. Compiler l'extension Cython ────────────────────────────────────
#
# ⚠️ A FAIRE AVANT L'ENTRAINEMENT, PAS APRES.
#
# `monotonic_align` est le seul morceau de Piper ecrit en Cython : il aligne
# les phonemes sur l'audio, et la version Python pure serait trop lente. Le
# paquet publie sur PyPI ne le compile pas pour toutes les versions de Python.
#
# Quand il manque, l'entrainement demarre normalement — chargement des poids,
# mise en cache du corpus, « Epoch 0 » affiche — et ne s'effondre qu'au
# premier lot, sur un `ModuleNotFoundError`. Autrement dit, on paie les
# minutes de preparation pour rien.
import glob
import shutil
import subprocess
import sys
from pathlib import Path

dossier = Path(
    glob.glob("/usr/local/lib/python*/dist-packages/piper/train/vits/monotonic_align")[0]
)
(dossier / "setup_nova.py").write_text(
    "from setuptools import setup\\n"
    "from Cython.Build import cythonize\\n"
    "import numpy\\n"
    "setup(ext_modules=cythonize('core.pyx', language_level=3),\\n"
    "      include_dirs=[numpy.get_include()])\\n"
)
subprocess.run(
    [sys.executable, "setup_nova.py", "build_ext", "--inplace"], cwd=dossier, check=True
)

# Selon les versions, l'import cherche `monotonic_align.core` ou
# `monotonic_align.monotonic_align.core`. On satisfait les deux : un fichier
# en trop ne coute rien, un import rate coute une heure de GPU.
niche = dossier / "monotonic_align"
niche.mkdir(exist_ok=True)
(niche / "__init__.py").touch()
for produit in sorted(dossier.rglob("core*.so")):
    if produit.parent != niche:
        shutil.copy2(produit, niche / produit.name)
    if produit.parent != dossier:
        shutil.copy2(produit, dossier / produit.name)

subprocess.run(
    [
        sys.executable,
        "-c",
        "import piper.train.vits.monotonic_align as m; "
        "print('✓ monotonic_align operationnel :', m.maximum_path)",
    ],
    check=True,
)

# ── 2. Deposer l'archive ──────────────────────────────────────────────────
# Glisse `voix-nova-affinage.zip` dans le panneau Fichiers de Colab, puis :
!unzip -q -o voix-nova-affinage.zip -d /content/corpus
!ls /content/corpus/wavs | head -3
!wc -l /content/corpus/metadata.csv

# ── 3. Recuperer le point de depart francais ──────────────────────────────
#
# ⚠️ ON PART D'UN MODELE QUI PARLE DEJA FRANCAIS.
#
# Repartir de zero demanderait des dizaines d'heures de voix. Ici le modele
# connait la langue ; l'affinage ne fait que deplacer le timbre vers celui du
# corpus. C'est toute la difference entre quinze minutes et dix heures.
#
# ⚠️ `rhasspy/piper-checkpoints` est un depot de type DATASET, pas MODEL.
# `hf_hub_download(...)` sans `repo_type="dataset"` renvoie un 401 qui ressemble
# a un probleme d'authentification alors que le depot est public.
from huggingface_hub import hf_hub_download

base = hf_hub_download(
    repo_id="rhasspy/piper-checkpoints",
    repo_type="dataset",
    filename="fr/fr_FR/siwis/medium/epoch=3304-step=2050940.ckpt",
)
print(base)

# ── 3 bis. Nettoyer le point de depart ────────────────────────────────────
#
# ⚠️ CETTE ETAPE N'EST PAS FACULTATIVE.
#
# Le checkpoint publie contient des `pathlib.PosixPath` serialises. Depuis
# PyTorch 2.6, `torch.load` refuse par defaut tout objet qui n'est pas un
# tenseur (`weights_only=True`) et leve `UnpicklingError`. L'option
# `--weights_only false` de la ligne de commande NE SERT A RIEN ici : Lightning
# force `weights_only=True` en interne quand il lit un checkpoint.
#
# On reecrit donc une copie ou ces chemins sont de simples chaines.
import torch

point = torch.load(base, map_location="cpu", weights_only=False)


def _en_texte(valeur):
    from pathlib import PurePath

    if isinstance(valeur, PurePath):
        return str(valeur)
    if isinstance(valeur, dict):
        return {c: _en_texte(v) for c, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return type(valeur)(_en_texte(v) for v in valeur)
    return valeur


point = _en_texte(point)
torch.save(point, "/content/base-propre.ckpt")
torch.load("/content/base-propre.ckpt", map_location="cpu")  # doit passer
print("✓ relu en mode strict")

# ── 4. Entrainer ──────────────────────────────────────────────────────────
#
# ⚠️ `--model.warmstart_ckpt` ET NON `--ckpt_path`.
#
# `--ckpt_path` demande une REPRISE complete : poids, optimiseur, compteur
# d'epoques et hyperparametres enregistres. Les deux derniers font echouer
# l'affinage, et pour deux raisons distinctes :
#
#   1. les hyperparametres du checkpoint publie contiennent des cles que la
#      version actuelle du CLI ne connait plus, d'ou
#      « Subcommand 'fit' does not accept option 'model.sample_bytes' » ;
#   2. le compteur repartirait de l'epoque du modele de base (3304 ici), donc
#      un `--trainer.max_epochs 600` arreterait l'entrainement immediatement,
#      sans erreur et sans avoir rien appris.
#
# `--model.warmstart_ckpt` charge les POIDS SEULS. C'est l'entree dediee a
# l'affinage : compteur a zero, optimiseur neuf, hyperparametres pris sur la
# ligne de commande.
#
# `--data.trim_silence false` : le corpus a DEJA ete rogne, avec une marge de
# 60 ms choisie pour ne pas manger l'attaque des consonnes. Laisser Piper
# rogner une seconde fois couperait cette marge.
#
# `--data.validation_split 0.0` : sur deux cent quarante prises, mettre de cote
# de quoi valider revient a s'amputer d'une part utile du corpus pour une
# mesure qu'on ne regardera pas. On juge a l'oreille, a la fin.
#
# 600 epoques est un plafond, pas un objectif : `last.ckpt` est reecrit a
# chaque epoque, et vers 200 la voix est souvent deja bonne. Interrompre la
# cellule pour passer a l'export est parfaitement legitime.
!python -m piper.train fit \\
  --data.voice_name "nova" \\
  --data.csv_path /content/corpus/metadata.csv \\
  --data.audio_dir /content/corpus/wavs \\
  --data.cache_dir /content/cache \\
  --data.config_path /content/nova.json \\
  --data.espeak_voice fr \\
  --data.batch_size 16 \\
  --data.validation_split 0.0 \\
  --data.num_test_examples 0 \\
  --data.trim_silence false \\
  --model.sample_rate 22050 \\
  --model.warmstart_ckpt /content/base-propre.ckpt \\
  --trainer.max_epochs 600 \\
  --trainer.accelerator gpu \\
  --trainer.devices 1 \\
  --trainer.default_root_dir /content/sortie

# ── 5. Exporter en .onnx ──────────────────────────────────────────────────
!ls /content/sortie/lightning_logs/version_0/checkpoints/
!python -m piper.train.export_onnx \\
  --checkpoint /content/sortie/lightning_logs/version_0/checkpoints/last.ckpt \\
  --output-file /content/nova.onnx
!cp /content/nova.json /content/nova.onnx.json
!ls -lh /content/nova.onnx

# ── 6. Recuperer les deux fichiers ────────────────────────────────────────
# `nova.onnx` ET `nova.onnx.json` : le second decrit le taux et les phonemes.
# Sans lui, Piper refuse de charger le modele.
from google.colab import files
files.download('/content/nova.onnx')
files.download('/content/nova.onnx.json')

# ══════════════════════════════════════════════════════════════════════════
#  ENSUITE, SUR LE MAC
#
#      mkdir -p ~/Desktop/nova-git/nova/data/voix
#      # deposer nova.onnx et nova.onnx.json dedans
#
#      cd ~/Desktop/nova-git/nova
#      cat >> .env <<'FIN'
#      NOVA_VOIX_MOTEUR=piper
#      NOVA_VOIX_MODELE=~/Desktop/nova-git/nova/data/voix/nova.onnx
#      FIN
#
#  Puis relancer `make serve`. Rien d'autre a changer : le moteur Piper est
#  deja branche, et il accepte un chemin .onnx precisement pour ce cas.
# ══════════════════════════════════════════════════════════════════════════
"""


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    archive = Path(sys.argv[2]) if len(sys.argv) > 2 else ARCHIVE

    wavs = sorted((source / "wavs").glob("*.wav"))
    fiche = source / "metadata.csv"

    if not wavs or not fiche.exists():
        print(f"✗ corpus prepare introuvable dans {source}")
        print("  Lance d'abord :  uv run python scripts/preparer_affinage.py")
        return 1

    textes: dict[str, str] = {}
    for ligne in fiche.read_text(encoding="utf-8").splitlines():
        morceaux = ligne.split("|")
        if len(morceaux) >= 2:
            textes[morceaux[0]] = morceaux[1]

    # ── Les trois verifications qui doivent passer AVANT le GPU ───────────
    ennuis: list[str] = []

    sans_texte = [w.stem for w in wavs if w.stem not in textes]
    sans_audio = [i for i in textes if not (source / "wavs" / f"{i}.wav").exists()]
    if sans_texte or sans_audio:
        ennuis.append(
            f"corpus desaligne : {len(sans_texte)} audio(s) sans texte, "
            f"{len(sans_audio)} texte(s) sans audio"
        )

    secondes = 0.0
    mauvais_taux = []
    for chemin in wavs:
        with wave.open(str(chemin), "rb") as f:
            if f.getframerate() != TAUX_ATTENDU:
                mauvais_taux.append(chemin.stem)
            secondes += f.getnframes() / f.getframerate()
    if mauvais_taux:
        ennuis.append(f"{len(mauvais_taux)} fichier(s) pas en {TAUX_ATTENDU} Hz")
    if secondes < MINUTES_MIN * 60:
        ennuis.append(f"{secondes / 60:.1f} min de parole, il en faut {MINUTES_MIN}")

    print(f"\n  {len(wavs)} prises · {secondes / 60:.1f} min · point de depart {BASE}")

    if ennuis:
        print("\n✗ A corriger avant d'entrainer :")
        for ennui in ennuis:
            print(f"    {ennui}")
        print("\n  Une erreur decouverte apres trois heures de GPU coute trois heures.")
        return 1

    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr("metadata.csv", fiche.read_text(encoding="utf-8"))
        for chemin in wavs:
            zip_.write(chemin, f"wavs/{chemin.name}")

    (archive.parent / "COMMANDES.txt").write_text(COMMANDES, encoding="utf-8")

    print(f"\n✓ {archive}  ({archive.stat().st_size / 1e6:.0f} Mo)")
    print(f"  Commandes : {archive.parent / 'COMMANDES.txt'}")
    print("\n  1. ouvre colab.research.google.com, nouveau carnet")
    print("  2. Execution > Modifier le type d'execution > GPU T4")
    print("  3. glisse l'archive dans le panneau Fichiers")
    print("  4. colle les commandes, bloc par bloc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
