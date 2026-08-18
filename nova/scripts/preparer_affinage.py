"""Nettoyer un corpus enregistre et le rendre pret pour l'affinage.

    uv run python scripts/preparer_affinage.py

POURQUOI CE SCRIPT EXISTE — ET CE QU'IL A EVITE

Le verificateur a signale 233 prises « a refaire » sur 245. Le detail disait
autre chose :

    232 x  blancs 0.5 s a 2.0 s en debut/fin
      1 x  bruit de fond (rapport 12 dB)

Les blancs ne se REFONT pas, ils se ROGNENT — deux secondes de calcul. En les
rangeant dans la meme colonne que le bruit, le verificateur allait faire
recommencer vingt-cinq minutes de lecture a quelqu'un pour du silence qu'un
programme enleve tout seul.

Un diagnostic qui ne distingue pas le reparable de l'irreparable n'est pas un
diagnostic : c'est une facture. Ce script est la moitie manquante.

CE QU'IL FAIT, ET DANS QUEL ORDRE

    1. ROGNE les silences de bord, en gardant une petite marge
    2. NORMALISE le niveau de tout le corpus, d'un seul gain
    3. ECARTE les prises irrecuperables, en les nommant
    4. ECRIT un dossier neuf — l'original n'est jamais modifie
"""

from __future__ import annotations

import csv
import shutil
import sys
import wave
from array import array
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "data" / "voix-clone"
SORTIE = RACINE / "data" / "voix-clone-prete"

#: Marge de silence gardee de part et d'autre, en secondes.
#:
#: ⚠️ NI ZERO, NI PLUS. Rogner au ras coupe l'attaque des consonnes — le « p »
#: de « pain » commence par un silence de fermeture qui fait partie du son.
#: Trop garder apprend au modele a hesiter avant de parler.
MARGE_S = 0.06

#: Niveau vise apres normalisation, en dB RMS. -23 dB est la valeur usuelle
#: des corpus de synthese : assez haut pour couvrir le bruit de quantification,
#: assez bas pour qu'aucune crete ne sature.
CIBLE_DB = -23.0

#: Proportion d'echantillons qu'on accepte d'ecreter pour atteindre le niveau
#: vise. Sur seize millions d'echantillons, un dix-millieme en represente mille
#: six cents — soit quelques clics et chocs, inaudibles une fois rabotes. C'est
#: le reglage qui empeche un accident isole de brider tout le corpus.
ECRETAGE_TOLERE = 1e-4

#: En dessous de ce rapport signal/bruit, la prise est ECARTEE. Le modele
#: apprendrait le fond sonore en meme temps que la voix, et le restituerait
#: sous chaque phrase.
SNR_MIN_DB = 20.0


def _lire(chemin: Path) -> tuple[array, int]:
    with wave.open(str(chemin), "rb") as f:
        taux = f.getframerate()
        brut = f.readframes(f.getnframes())
    valeurs = array("h")
    valeurs.frombytes(brut[: len(brut) - len(brut) % 2])
    if sys.byteorder == "big":
        valeurs.byteswap()
    return valeurs, taux


def _ecrire(chemin: Path, valeurs: array, taux: int) -> None:
    sortie = array("h", valeurs)
    if sys.byteorder == "big":
        sortie.byteswap()
    with wave.open(str(chemin), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(taux)
        f.writeframes(sortie.tobytes())


def _rms(valeurs) -> float:
    if not len(valeurs):
        return 0.0
    return (sum((v / 32768.0) ** 2 for v in valeurs) / len(valeurs)) ** 0.5


def _db(valeur: float) -> float:
    import math

    return 20 * math.log10(max(valeur, 1e-9))


def _plancher_de_bruit(valeurs, taux: int) -> float:
    fenetre = max(1, taux // 20)
    niveaux = [
        _rms(valeurs[i : i + fenetre])
        for i in range(0, max(1, len(valeurs) - fenetre), fenetre)
    ]
    if not niveaux:
        return 0.0
    niveaux.sort()
    return niveaux[len(niveaux) // 10]


def rogner(valeurs: array, taux: int, seuil: float, marge_s: float = MARGE_S) -> array:
    """Retire le silence de bord, en gardant `marge_s` de chaque cote.

    ⚠️ ON CHERCHE PAR FENETRES, PAS ECHANTILLON PAR ECHANTILLON.

    Un seul echantillon peut depasser le seuil par hasard — un craquement de
    chaise, un clic de clavier. Une fenetre de 10 ms ne depasse que si quelque
    chose de sonore s'y produit vraiment.
    """
    fenetre = max(1, taux // 100)
    if len(valeurs) <= fenetre:
        return valeurs

    debut = 0
    for i in range(0, len(valeurs) - fenetre, fenetre):
        if _rms(valeurs[i : i + fenetre]) > seuil:
            debut = i
            break

    fin = len(valeurs)
    for i in range(len(valeurs) - fenetre, 0, -fenetre):
        if _rms(valeurs[i : i + fenetre]) > seuil:
            fin = i + fenetre
            break

    marge = int(marge_s * taux)
    return valeurs[max(0, debut - marge) : min(len(valeurs), fin + marge)]


def appliquer_gain(valeurs: array, gain: float) -> array:
    """Multiplie, en bornant AVANT la conversion — sinon un depassement
    repasse par zero et devient un claquement au lieu d'une saturation."""
    return array("h", (max(-32768, min(32767, int(v * gain))) for v in valeurs))


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    sortie = Path(sys.argv[2]) if len(sys.argv) > 2 else SORTIE

    wavs = sorted((source / "wavs").glob("*.wav"))
    if not wavs:
        print(f"✗ aucun enregistrement dans {source / 'wavs'}")
        return 1

    textes: dict[str, str] = {}
    fiche = source / "metadata.csv"
    if fiche.exists():
        for ligne in fiche.read_text(encoding="utf-8").splitlines():
            morceaux = ligne.split("|")
            if len(morceaux) >= 2:
                textes[morceaux[0]] = morceaux[1]

    print(f"\n── {len(wavs)} prise(s) ─────────────────────────────────\n")

    # ── 1. Rogner, et mesurer ce qu'on garde ─────────────────────────────
    gardees: list[tuple[str, array, int]] = []
    ecartees: list[tuple[str, str]] = []
    secondes_avant = secondes_apres = 0.0

    for chemin in wavs:
        valeurs, taux = _lire(chemin)
        secondes_avant += len(valeurs) / taux

        fond = _plancher_de_bruit(valeurs, taux)
        snr = _db(_rms(valeurs)) - _db(fond)

        # Le bruit, lui, ne se repare pas : on ecarte. Une prise sur deux cent
        # quarante-cinq ne manquera a personne, et la garder contaminerait
        # toutes les autres.
        if snr < SNR_MIN_DB:
            ecartees.append((chemin.stem, f"bruit de fond (rapport {snr:.0f} dB)"))
            continue
        if chemin.stem not in textes:
            ecartees.append((chemin.stem, "aucune transcription"))
            continue

        rognee = rogner(valeurs, taux, max(fond * 3, 0.004))
        if len(rognee) < taux * 0.5:
            ecartees.append((chemin.stem, "plus rien apres rognage"))
            continue

        secondes_apres += len(rognee) / taux
        gardees.append((chemin.stem, rognee, taux))

    if not gardees:
        print("✗ aucune prise exploitable")
        return 1

    # ── 2. Normaliser d'UN SEUL gain, pour tout le corpus ────────────────
    #
    # ⚠️ SURTOUT PAS UN GAIN PAR FICHIER.
    #
    # Normaliser chaque prise separement mettrait une question murmuree et une
    # exclamation au meme niveau. Le modele apprendrait alors un debit plat,
    # sans nuance d'intensite — precisement ce qui fait sonner un clone comme
    # une machine.
    #
    # Un gain unique remonte l'ensemble sans toucher aux rapports entre
    # phrases. Il est borne par la prise la plus forte : depasser ferait
    # saturer celle-la, et une seule prise ecretee suffit a apprendre
    # l'ecretage.
    # ⚠️ LA MEDIANE, ET SURTOUT PAS LA MOYENNE D'ENERGIE.
    #
    # La premiere version faisait la moyenne quadratique de tout le corpus.
    # Un claquement de touche de quarante echantillons a 30000 y pese alors
    # PLUS, en energie, que les deux secondes de voix du meme fichier :
    #
    #     energie du clic    40 x (30000/32768)²  = 33,5
    #     energie de la voix 41716 x (0,0056)²    =  1,3
    #
    # Le corpus paraissait a -41,4 dB alors qu'il etait a -45. Le gain calcule
    # etait donc trop faible de 3,5 dB, et l'accident se payait DEUX fois : une
    # fois en bridant le plafond, une fois en faussant la mesure.
    #
    # La mediane des niveaux par fichier ignore les valeurs extremes par
    # construction. Elle repond a la vraie question — « a quel niveau parle-t-on
    # dans ce corpus ? » — au lieu de « combien d'energie contient-il ? ».
    niveaux = sorted(_rms(v) for _, v, _ in gardees)
    global_rms = niveaux[len(niveaux) // 2]
    gain_vise = (10 ** (CIBLE_DB / 20)) / max(global_rms, 1e-9)

    # ⚠️ LE PLAFOND SE FIXE SUR LES ECHANTILLONS, PAS SUR LES FICHIERS.
    #
    # Deux versions se sont trompees ici, et la seconde de facon instructive.
    #
    # La premiere se calait sur la crete ABSOLUE du corpus. Un claquement de
    # touche — quarante echantillons dans un seul fichier — plafonnait alors le
    # gain a x1,75 et laissait les 244 autres prises a -26,6 dB au lieu de -23.
    #
    # La deuxieme prenait le 99,9e percentile des cretes PAR FICHIER. Sur 244
    # fichiers, ca n'ecarte que 0,24 fichier : le deuxieme plus haut, qui reste
    # une crete. Le gain est passe de x1,75 a x1,83 — la correction avait l'air
    # d'agir, et ne corrigeait presque rien.
    #
    # La bonne question n'est pas « quel fichier est le plus fort ? » mais
    # « combien d'echantillons accepte-t-on d'ecreter ? ». Sur seize millions
    # d'echantillons, en rogner deux mille est inaudible — ce sont des clics.
    # Laisser tout le corpus trois decibels trop bas s'entend partout.
    #
    # L'histogramme evite de trier seize millions de valeurs : les amplitudes
    # sont deja des entiers de 0 a 32767, donc les compter suffit.
    histogramme = [0] * 32768
    total_echantillons = 0
    for _, valeurs, _ in gardees:
        total_echantillons += len(valeurs)
        for x in valeurs:
            histogramme[abs(x) if x != -32768 else 32767] += 1

    autorises = int(total_echantillons * ECRETAGE_TOLERE)
    cumul = 0
    reference = 1
    for amplitude in range(32767, 0, -1):
        cumul += histogramme[amplitude]
        if cumul > autorises:
            reference = amplitude
            break

    gain_max = 32000 / max(reference, 1)
    gain = min(gain_vise, gain_max)

    # Les prises qui depassent apres gain : on les NOMME. Une pointe isolee est
    # souvent un bruit parasite, et savoir laquelle permet de l'ecouter.
    bruyantes = [nom for nom, v, _ in gardees
                 if max((abs(x) for x in v), default=0) * gain > 32700]

    # ── 3. Ecrire un dossier NEUF ────────────────────────────────────────
    #
    # L'original n'est jamais touche. Vingt-cinq minutes de la voix de
    # quelqu'un ne se regenerent pas : si un reglage de ce script se revele
    # mauvais, il faut pouvoir recommencer depuis la matiere brute.
    if sortie.exists():
        shutil.rmtree(sortie)
    (sortie / "wavs").mkdir(parents=True)

    with (sortie / "metadata.csv").open("w", encoding="utf-8", newline="") as f:
        ecrivain = csv.writer(f, delimiter="|", quoting=csv.QUOTE_NONE, escapechar="\\")
        for nom, valeurs, taux in gardees:
            _ecrire(sortie / "wavs" / f"{nom}.wav", appliquer_gain(valeurs, gain), taux)
            ecrivain.writerow([nom, textes[nom], textes[nom]])

    print(f"  rognage      {secondes_avant / 60:.1f} → {secondes_apres / 60:.1f} min"
          f"   ({(secondes_avant - secondes_apres) / 60:.1f} min de silence retire)")
    print(f"  niveau       {_db(global_rms):.1f} → {_db(global_rms * gain):.1f} dB"
          f"   (gain x{gain:.2f}" + (", borne par la crete)" if gain == gain_max else ")"))
    if bruyantes:
        print(f"  cretes rabotees dans {len(bruyantes)} prise(s) : "
              + ", ".join(bruyantes[:4]) + ("…" if len(bruyantes) > 4 else ""))
        print("    (une pointe isolee est souvent un choc ou un clic — ecoute-les")
        print("     si le clone grince, mais ca ne bloque rien)")
    print(f"  gardees      {len(gardees)} / {len(wavs)}")

    if ecartees:
        print(f"\n  ecartees ({len(ecartees)}) :")
        for nom, raison in ecartees[:10]:
            print(f"    {nom}  {raison}")
        if len(ecartees) > 10:
            print(f"    … et {len(ecartees) - 10} autre(s)")

    print(f"\n✓ Corpus pret : {sortie}")
    print(f"  {len(gardees)} prises · {secondes_apres / 60:.1f} min de parole nette")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
