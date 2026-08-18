"""L'emballage du corpus pour l'entrainement.

⚠️ CE BANC PROTEGE TROIS HEURES DE GPU.

L'affinage tourne ailleurs — deux a quatre heures sur un GPU gratuit. Une
erreur de format n'y est decouverte qu'a l'arrivee, c'est-a-dire apres avoir
depense ces heures. Tout ce qui peut etre verifie avant le depart doit l'etre
avant le depart.

Les trois controles ont chacun deja coute quelque chose dans ce projet :

    l'alignement       un corpus desaligne fait apprendre des sons a un texte
                       qui n'est pas le leur, sans rien signaler
    le taux            22 050 Hz : un modele entraine sur du 16 kHz
                       reechantillonne sonne sourd, et tous les fichiers
                       restent parfaitement valides
    la duree           un affinage sous-alimente ne rate pas bruyamment, il
                       rend une voix approximative
"""

from __future__ import annotations

import importlib.util
import wave
import zipfile
from array import array
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "exporter", RACINE / "scripts" / "exporter_pour_affinage.py"
)
exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exporter)


def _corpus(dossier: Path, prises: int, taux: int = 22050, secondes: float = 4.0,
            aligne: bool = True) -> None:
    (dossier / "wavs").mkdir(parents=True, exist_ok=True)
    lignes = []
    for i in range(prises):
        nom = f"phrase-{i:04d}"
        with wave.open(str(dossier / "wavs" / f"{nom}.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(taux)
            f.writeframes(array("h", [100] * int(secondes * taux)).tobytes())
        if aligne or i > 0:
            lignes.append(f"{nom}|Une phrase.|Une phrase.")
    (dossier / "metadata.csv").write_text("\n".join(lignes) + "\n", encoding="utf-8")


def _exporter(source: Path, archive: Path) -> int:
    exporter.main.__globals__["sys"].argv = ["x", str(source), str(archive)]
    return exporter.main()


def test_un_corpus_complet_est_emballe(tmp_path):
    _corpus(tmp_path / "src", prises=200)

    assert _exporter(tmp_path / "src", tmp_path / "a.zip") == 0

    with zipfile.ZipFile(tmp_path / "a.zip") as zip_:
        noms = zip_.namelist()
    assert "metadata.csv" in noms
    assert sum(1 for n in noms if n.startswith("wavs/")) == 200


def test_un_corpus_trop_court_est_refuse(tmp_path, capsys):
    """Un affinage sous-alimente rend une voix approximative, sans le dire."""
    _corpus(tmp_path / "src", prises=20)

    assert _exporter(tmp_path / "src", tmp_path / "a.zip") == 1
    assert "min de parole" in capsys.readouterr().out
    assert not (tmp_path / "a.zip").exists()


def test_un_mauvais_taux_est_refuse(tmp_path, capsys):
    """⚠️ 16 kHz REECHANTILLONNE DONNE UN MODELE SOURD, SANS RIEN CASSER.

    Les aigus n'ont jamais ete captes : aucun traitement ne les invente. Et
    tous les fichiers restent parfaitement valides, donc rien d'autre ne le
    verrait.
    """
    _corpus(tmp_path / "src", prises=200, taux=16000)

    assert _exporter(tmp_path / "src", tmp_path / "a.zip") == 1
    assert "22050 Hz" in capsys.readouterr().out


def test_un_corpus_desaligne_est_refuse(tmp_path, capsys):
    """Le modele apprendrait des sons associes au mauvais texte."""
    _corpus(tmp_path / "src", prises=200, aligne=False)

    assert _exporter(tmp_path / "src", tmp_path / "a.zip") == 1
    assert "desaligne" in capsys.readouterr().out


def test_les_commandes_sont_ecrites_a_cote_de_l_archive(tmp_path):
    """L'archive sans les commandes obligerait a les retrouver ailleurs."""
    _corpus(tmp_path / "src", prises=200)
    _exporter(tmp_path / "src", tmp_path / "sortie" / "a.zip")

    commandes = (tmp_path / "sortie" / "COMMANDES.txt").read_text(encoding="utf-8")
    assert "piper.train fit" in commandes
    assert "--data.trim_silence false" in commandes, (
        "le corpus est deja rogne avec une marge choisie ; rogner deux fois "
        "mangerait l'attaque des consonnes"
    )
    assert "export_onnx" in commandes
    assert "nova.onnx.json" in commandes, (
        "sans le fichier de configuration, Piper refuse de charger le modele"
    )


def test_les_commandes_affinent_au_lieu_de_reprendre(tmp_path):
    """`--ckpt_path` echoue de deux facons, dont une silencieuse.

    Il exige les hyperparametres enregistres du checkpoint publie — que le CLI
    actuel rejette — et il restaure le compteur d'epoques du modele de base.
    Ce second point ne leve aucune erreur : l'entrainement s'arrete aussitot,
    en ayant l'air d'avoir reussi.
    """
    _corpus(tmp_path / "src", prises=200)
    _exporter(tmp_path / "src", tmp_path / "sortie" / "a.zip")

    commandes = (tmp_path / "sortie" / "COMMANDES.txt").read_text(encoding="utf-8")
    assert "--model.warmstart_ckpt" in commandes

    # Les commentaires ont le droit de citer `--ckpt_path` — c'est meme le seul
    # endroit ou la raison du choix est ecrite. On ne regarde donc que les
    # lignes executees.
    lignes = commandes.splitlines()
    executees = [x for x in lignes if not x.lstrip().startswith("#")]
    assert not any("--ckpt_path" in x for x in executees), (
        "une reprise complete rejoue le compteur d'epoques du modele de base"
    )
    assert 'repo_type="dataset"' in commandes, (
        "piper-checkpoints est un depot dataset ; sans ca le 401 fait croire "
        "a un probleme d'authentification"
    )
    assert "weights_only=False" in commandes, (
        "le checkpoint publie contient des PosixPath que PyTorch 2.6 refuse"
    )


def test_l_extension_cython_est_compilee_avant_l_entrainement(tmp_path):
    """⚠️ `monotonic_align` MANQUANT NE SE VOIT QU'AU PREMIER LOT.

    L'entrainement charge les poids, met le corpus en cache, affiche
    « Epoch 0 » — puis tombe sur un ModuleNotFoundError. Toute la preparation
    est payee pour rien. La compilation doit donc venir avant, pas apres.
    """
    _corpus(tmp_path / "src", prises=200)
    _exporter(tmp_path / "src", tmp_path / "sortie" / "a.zip")

    commandes = (tmp_path / "sortie" / "COMMANDES.txt").read_text(encoding="utf-8")
    assert "monotonic_align" in commandes
    assert commandes.index("monotonic_align") < commandes.index("piper.train fit"), (
        "compiler apres l'entrainement ne sert a rien : il aura deja echoue"
    )

    # Cette etape est du Python, pas du shell, et elle vit dans une chaine :
    # une barre oblique mal echappee ne se verrait qu'au collage dans Colab.
    debut = commandes.index("import glob")
    fin = commandes.index("# ── 2. Deposer")
    compile(commandes[debut:fin], "<etape-1-bis>", "exec")
