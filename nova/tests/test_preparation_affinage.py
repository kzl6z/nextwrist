"""La preparation d'un corpus enregistre.

⚠️ CE FICHIER GARDE UNE ERREUR QUI ALLAIT COUTER VINGT-CINQ MINUTES A QUELQU'UN.

Le verificateur a rendu ceci sur le corpus reel :

    233 prise(s) a refaire
      232 x  blancs 0.5 s a 2.0 s
        1 x  bruit de fond (rapport 12 dB)

Les blancs ne se REFONT pas, ils se ROGNENT — deux secondes de calcul. En les
rangeant dans la meme colonne que le bruit, l'outil allait faire recommencer
toute la lecture pour du silence qu'un programme enleve tout seul.

Un diagnostic qui ne distingue pas le REPARABLE de l'IRREPARABLE n'est pas un
diagnostic : c'est une facture. Ce banc protege cette distinction, et le
traitement qui la rend vraie.
"""

from __future__ import annotations

import csv
import importlib.util
import math
import random
import wave
from array import array
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "preparer", RACINE / "scripts" / "preparer_affinage.py"
)
preparer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preparer)

TAUX = 22050


def _prise(niveau: float, bruit: float, blanc: float, duree: float = 2.0) -> array:
    """Silence, parole a enveloppe syllabique qui touche zero, silence."""
    aleatoire = random.Random(3)
    valeurs = array("h")

    def ajouter(x: float) -> None:
        valeurs.append(max(-32768, min(32767, int(x * 32767))))

    for _ in range(int(blanc * TAUX)):
        ajouter(aleatoire.gauss(0, bruit))
    for i in range(int(duree * TAUX)):
        t = i / TAUX
        enveloppe = max(0.0, math.sin(2 * math.pi * 3.0 * t)) ** 2
        son = sum(
            math.sin(2 * math.pi * f * t) / k
            for k, f in enumerate((190, 380, 570, 760), start=1)
        )
        ajouter(niveau * enveloppe * son / 2 + aleatoire.gauss(0, bruit))
    for _ in range(int(blanc * TAUX)):
        ajouter(aleatoire.gauss(0, bruit))
    return valeurs


def _corpus(dossier: Path, prises: dict[str, array]) -> None:
    (dossier / "wavs").mkdir(parents=True, exist_ok=True)
    with (dossier / "metadata.csv").open("w", encoding="utf-8", newline="") as f:
        ecrivain = csv.writer(f, delimiter="|", quoting=csv.QUOTE_NONE, escapechar="\\")
        for nom, valeurs in prises.items():
            preparer._ecrire(dossier / "wavs" / f"{nom}.wav", valeurs, TAUX)
            ecrivain.writerow([nom, "Une phrase.", "Une phrase."])


def _duree(chemin: Path) -> float:
    with wave.open(str(chemin), "rb") as f:
        return f.getnframes() / f.getframerate()


def test_le_rognage_retire_le_silence_mais_garde_une_marge():
    """⚠️ ROGNER AU RAS COUPE L'ATTAQUE DES CONSONNES.

    Le « p » de « pain » commence par un silence de fermeture qui fait partie
    du son. Trop garder, a l'inverse, apprend au modele a hesiter avant de
    parler — c'est le defaut le plus reconnaissable des clones bacles.
    """
    valeurs = _prise(0.2, 0.0001, blanc=1.5, duree=2.0)
    rognee = preparer.rogner(valeurs, TAUX, seuil=0.004)

    # 5,0 s en entree (1,5 + 2,0 + 1,5), 2,0 s de parole.
    duree = len(rognee) / TAUX
    tolerance = 3 * preparer.MARGE_S

    # Le silence part…
    assert duree < 2.0 + tolerance, f"{duree:.2f} s — du silence subsiste"
    # …mais la parole reste entiere. La borne basse compte AUTANT que la
    # haute : un rognage trop gourmand mange l'attaque, et ca ne se voit pas
    # dans la duree totale — seulement a l'oreille, une fois le modele
    # entraine.
    assert duree > 2.0 - tolerance, f"{duree:.2f} s — la parole a ete amputee"


def test_une_prise_deja_serree_n_est_pas_amputee():
    valeurs = _prise(0.2, 0.0001, blanc=0.05, duree=2.0)
    rognee = preparer.rogner(valeurs, TAUX, seuil=0.004)

    assert len(rognee) >= int(1.9 * TAUX)


def test_le_gain_est_GLOBAL_et_pas_par_fichier(tmp_path):
    """⚠️ C'EST LE REGLAGE QUI DECIDE SI LE CLONE A DES NUANCES.

    Normaliser chaque prise separement mettrait une question murmuree et une
    exclamation au meme niveau. Le modele apprendrait un debit plat, sans
    variation d'intensite — precisement ce qui fait sonner un clone comme une
    machine.

    Un gain unique remonte l'ensemble sans toucher aux rapports entre phrases :
    la forte reste forte, la douce reste douce.
    """
    _corpus(tmp_path / "src", {
        "phrase-0000": _prise(0.30, 0.0001, blanc=0.3),   # forte
        "phrase-0001": _prise(0.06, 0.0001, blanc=0.3),   # douce
    })

    preparer.main.__globals__["sys"].argv = [
        "x", str(tmp_path / "src"), str(tmp_path / "out")
    ]
    assert preparer.main() == 0

    forte, _ = preparer._lire(tmp_path / "out" / "wavs" / "phrase-0000.wav")
    douce, _ = preparer._lire(tmp_path / "out" / "wavs" / "phrase-0001.wav")

    rapport = preparer._rms(forte) / preparer._rms(douce)
    assert 4.0 < rapport < 6.0, (
        f"rapport {rapport:.1f} — le contraste entre les deux prises a ete "
        f"ecrase, chaque fichier a donc ete normalise separement"
    )


def test_les_prises_bruitees_sont_ecartees_et_nommees(tmp_path, capsys):
    """Le bruit ne se separe pas de la voix : aucun traitement ne le repare."""
    _corpus(tmp_path / "src", {
        "phrase-0000": _prise(0.2, 0.0001, blanc=0.3),
        "phrase-0001": _prise(0.2, 0.05, blanc=0.3),      # bruitee
        "phrase-0002": _prise(0.2, 0.0001, blanc=0.3),
    })

    preparer.main.__globals__["sys"].argv = [
        "x", str(tmp_path / "src"), str(tmp_path / "out")
    ]
    preparer.main()

    restants = sorted(p.stem for p in (tmp_path / "out" / "wavs").glob("*.wav"))
    assert restants == ["phrase-0000", "phrase-0002"]
    assert "phrase-0001" in capsys.readouterr().out


def test_l_original_n_est_jamais_touche(tmp_path):
    """⚠️ VINGT-CINQ MINUTES DE LA VOIX DE QUELQU'UN NE SE REGENERENT PAS.

    Si un reglage de ce script se revele mauvais, il faut pouvoir recommencer
    depuis la matiere brute. Ecrire par-dessus l'aurait rendu impossible.
    """
    _corpus(tmp_path / "src", {"phrase-0000": _prise(0.2, 0.0001, blanc=1.0)})
    avant = (tmp_path / "src" / "wavs" / "phrase-0000.wav").read_bytes()

    preparer.main.__globals__["sys"].argv = [
        "x", str(tmp_path / "src"), str(tmp_path / "out")
    ]
    preparer.main()

    assert (tmp_path / "src" / "wavs" / "phrase-0000.wav").read_bytes() == avant
    assert _duree(tmp_path / "out" / "wavs" / "phrase-0000.wav") < _duree(
        tmp_path / "src" / "wavs" / "phrase-0000.wav"
    )


def test_le_gain_ne_fait_jamais_saturer(tmp_path):
    """Une seule prise ecretee suffit a apprendre l'ecretage au modele.

    Le gain vise -23 dB, mais il est borne par la crete la plus haute du
    corpus : atteindre la cible en saturant serait pire que de la manquer.
    """
    _corpus(tmp_path / "src", {
        "phrase-0000": _prise(0.9, 0.0001, blanc=0.3),   # deja tres forte
        "phrase-0001": _prise(0.02, 0.0001, blanc=0.3),  # tres faible
    })

    preparer.main.__globals__["sys"].argv = [
        "x", str(tmp_path / "src"), str(tmp_path / "out")
    ]
    preparer.main()

    for chemin in (tmp_path / "out" / "wavs").glob("*.wav"):
        valeurs, _ = preparer._lire(chemin)
        assert max(abs(v) for v in valeurs) <= 32700, f"{chemin.name} sature"


def test_la_fiche_ne_garde_que_ce_qui_reste(tmp_path):
    """Un corpus desaligne fait apprendre des sons a un texte qui n'est pas
    le leur — et rien dans l'entrainement ne le signale."""
    _corpus(tmp_path / "src", {
        "phrase-0000": _prise(0.2, 0.0001, blanc=0.3),
        "phrase-0001": _prise(0.2, 0.05, blanc=0.3),      # sera ecartee
    })

    preparer.main.__globals__["sys"].argv = [
        "x", str(tmp_path / "src"), str(tmp_path / "out")
    ]
    preparer.main()

    lignes = (tmp_path / "out" / "metadata.csv").read_text(encoding="utf-8").splitlines()
    identifiants = [ligne.split("|")[0] for ligne in lignes if ligne.strip()]
    wavs = sorted(p.stem for p in (tmp_path / "out" / "wavs").glob("*.wav"))

    assert sorted(identifiants) == wavs


def test_un_clic_isole_ne_bride_pas_tout_le_corpus(tmp_path):
    """⚠️ RELEVE EN CONDITIONS REELLES : UN FICHIER PLAFONNAIT LES 244 AUTRES.

    Niveau RMS du corpus 0,027, crete a 0,56 — un facteur vingt-et-un. Ce n'est
    pas de la voix, c'est un claquement de touche. En se calant sur la crete
    ABSOLUE, le gain tombait a x1,75 et laissait tout le corpus a -26,6 dB au
    lieu de -23.

    On se cale donc sur le 99,9e percentile : l'accident isole est rabote — un
    clic ecrete ne s'entend pas — et la voix atteint son niveau.
    """
    prises = {f"phrase-{i:04d}": _prise(0.03, 0.0001, blanc=0.3) for i in range(20)}
    avec_clic = _prise(0.03, 0.0001, blanc=0.3)
    for j in range(40):
        avec_clic[int(0.5 * TAUX) + j] = 30000    # le claquement
    prises["phrase-0007"] = avec_clic
    _corpus(tmp_path / "src", prises)

    preparer.main.__globals__["sys"].argv = [
        "x", str(tmp_path / "src"), str(tmp_path / "out")
    ]
    assert preparer.main() == 0

    # Le corpus doit avoir atteint sa cible, clic ou pas.
    total = [preparer._lire(p)[0] for p in (tmp_path / "out" / "wavs").glob("*.wav")]
    global_rms = (
        sum(preparer._rms(v) ** 2 * len(v) for v in total) / sum(len(v) for v in total)
    ) ** 0.5
    atteint = preparer._db(global_rms)

    assert atteint > preparer.CIBLE_DB - 2.0, (
        f"{atteint:.1f} dB au lieu de {preparer.CIBLE_DB} — un accident isole "
        f"a plafonne la normalisation de tout le corpus"
    )
