"""Verifier un corpus enregistre AVANT de lancer l'affinage.

    uv run python scripts/verifier_voix_clone.py

POURQUOI CE SCRIPT EXISTE

Quelqu'un donne vingt-cinq minutes de son temps pour lire deux cent quarante-cinq
phrases. Si la prise est mauvaise, on ne s'en apercoit qu'apres l'entrainement —
c'est-a-dire apres avoir demande a cette personne de tout recommencer.

L'enregistreur verifie deja chaque phrase isolement : duree, niveau, saturation.
Ce qu'il ne peut PAS voir, c'est ce qui ne se lit qu'en comparant les phrases
entre elles :

    LA DERIVE DE NIVEAU     la personne s'est rapprochee ou eloignee du micro
                            au fil de la seance. Chaque prise est correcte, et
                            l'ensemble apprend au modele deux distances.

    LE BRUIT DE FOND        un ventilateur, une rue, un frigo. Inaudible quand
                            on parle, parfaitement appris par le modele — qui
                            le restituera sous chaque phrase de Nova.

    LES BLANCS EN BORD      une seconde de silence avant ou apres chaque phrase
                            apprend au modele a se taire au demarrage. C'est le
                            defaut qui donne ces clones qui « hesitent » avant
                            de parler.

Ces trois defauts ont en commun de ne jamais rendre un fichier invalide. Tout
passe, tout se lit, et le modele sort mediocre sans qu'aucune etape n'ait
signale quoi que ce soit.

⚠️ LANCE-LE APRES DIX PHRASES, PAS A LA FIN.

C'est tout l'interet : dix phrases suffisent a voir un bruit de fond ou un
mauvais placement. Vingt-cinq minutes suffisent a les rendre irrattrapables.
"""

from __future__ import annotations

import sys
import wave
from array import array
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "data" / "voix-clone"

TAUX_ATTENDU = 22050

#: Ecart de niveau tolere entre la premiere moitie et la seconde, en decibels.
#: Au-dela, la distance au micro a change en cours de seance.
DERIVE_MAX_DB = 3.0

#: Rapport signal/bruit minimal. En dessous, le modele apprend le fond sonore
#: en meme temps que la voix, et le restitue sous chaque phrase.
SNR_MIN_DB = 25.0

#: Minutes de PAROLE NETTE requises — silences exclus.
#:
#: Piper part d'un point de depart francais deja entraine : l'affinage n'a pas
#: a tout reapprendre, seulement a deplacer le timbre. Douze minutes suffisent,
#: vingt sont confortables, au-dela de trente le gain devient marginal.
MINUTES_PAROLE_MIN = 12

#: Silence tolere en debut et fin de prise, en secondes.
BLANC_MAX_S = 0.5

#: Proportion d'echantillons au plafond au-dela de laquelle on parle
#: d'ecretage. Un seul echantillon a 32767 est un hasard ; un pour mille est
#: une saturation.
ECRETAGE_MAX = 0.001


def _lire(chemin: Path) -> tuple[array, int]:
    with wave.open(str(chemin), "rb") as f:
        taux = f.getframerate()
        brut = f.readframes(f.getnframes())
    valeurs = array("h")
    valeurs.frombytes(brut[: len(brut) - len(brut) % 2])
    if sys.byteorder == "big":
        valeurs.byteswap()
    return valeurs, taux


def _db(valeur: float) -> float:
    """Decibels, avec un plancher : log(0) n'existe pas et casserait tout."""
    import math

    return 20 * math.log10(max(valeur, 1e-9))


def _rms(valeurs) -> float:
    if not len(valeurs):
        return 0.0
    return (sum((v / 32768.0) ** 2 for v in valeurs) / len(valeurs)) ** 0.5


def _plancher_de_bruit(valeurs, taux: int) -> float:
    """Le niveau des passages les PLUS CALMES du fichier.

    On decoupe en fenetres de 50 ms et on prend le dixieme percentile. La
    moyenne ne dirait rien : elle est dominee par la parole, qui est justement
    ce qu'on veut exclure.
    """
    fenetre = max(1, taux // 20)
    niveaux = [
        _rms(valeurs[i : i + fenetre])
        for i in range(0, max(1, len(valeurs) - fenetre), fenetre)
    ]
    if not niveaux:
        return 0.0
    niveaux.sort()
    return niveaux[len(niveaux) // 10]


def _blancs(valeurs, taux: int, seuil: float) -> tuple[float, float]:
    """Duree de silence au debut et a la fin, en secondes."""
    fenetre = max(1, taux // 100)   # 10 ms
    debut = fin = 0.0
    for i in range(0, len(valeurs) - fenetre, fenetre):
        if _rms(valeurs[i : i + fenetre]) > seuil:
            break
        debut += fenetre / taux
    for i in range(len(valeurs) - fenetre, 0, -fenetre):
        if _rms(valeurs[i : i + fenetre]) > seuil:
            break
        fin += fenetre / taux
    return debut, fin


def _ecretage(valeurs) -> float:
    if not len(valeurs):
        return 0.0
    return sum(1 for v in valeurs if abs(v) >= 32700) / len(valeurs)


def main() -> int:
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else DOSSIER
    wavs = sorted((dossier / "wavs").glob("*.wav"))

    if not wavs:
        print(f"✗ aucun enregistrement dans {dossier / 'wavs'}")
        return 1

    # ── La coherence entre l'audio et les transcriptions ──────────────────
    #
    # ⚠️ UN CORPUS DESALIGNE EST LE PIRE DES CAS.
    #
    # Le modele apprend alors a associer des sons a un texte qui n'est pas le
    # leur. Le resultat n'est pas « moins bon » : il est faux, et rien dans
    # l'entrainement ne le signale.
    fiche = dossier / "metadata.csv"
    textes: dict[str, str] = {}
    if fiche.exists():
        for ligne in fiche.read_text(encoding="utf-8").splitlines():
            morceaux = ligne.split("|")
            if len(morceaux) >= 2:
                textes[morceaux[0]] = morceaux[1]

    sans_texte = [w.stem for w in wavs if w.stem not in textes]
    sans_audio = [i for i in textes if not (dossier / "wavs" / f"{i}.wav").exists()]

    print(f"\n── {len(wavs)} enregistrement(s) ──────────────────────────────\n")

    # ⚠️ ON DECIDE D'ABORD SI LA MESURE DE BRUIT A ENCORE UN SENS.
    #
    # Sur un corpus prepare, le rognage a retire les silences : le rapport
    # signal/bruit n'y est plus mesurable (voir plus bas). Quelques prises en
    # gardent pourtant un peu, par hasard. Les juger, elles seules, revient a
    # condamner une minorite par une regle a laquelle la majorite echappe —
    # sur le corpus reel, 15 prises accusees pendant que 231 y echappaient.
    #
    # Une regle qui ne s'applique qu'a ceux qu'elle peut atteindre n'est pas
    # une regle : c'est un tirage au sort.
    avec_silence = 0
    for chemin in wavs:
        v, t = _lire(chemin)
        f = _plancher_de_bruit(v, t)
        a, b = _blancs(v, t, max(f * 3, 0.005))
        if a + b >= 0.2:
            avec_silence += 1
    corpus_prepare = avec_silence < len(wavs) / 2

    problemes: list[str] = []
    a_rogner: list[str] = []
    non_mesurables = 0
    parole_nette = 0.0
    niveaux: list[float] = []
    total = 0.0

    for chemin in wavs:
        valeurs, taux = _lire(chemin)
        duree = len(valeurs) / taux
        total += duree
        niveau = _rms(valeurs)
        niveaux.append(niveau)

        fond = _plancher_de_bruit(valeurs, taux)
        snr = _db(niveau) - _db(fond)
        avant, apres = _blancs(valeurs, taux, max(fond * 3, 0.005))
        ecrete = _ecretage(valeurs)
        parole_nette += max(0.0, duree - avant - apres)

        # ⚠️ DEUX COLONNES, ET LES CONFONDRE COUTE UNE SEANCE ENTIERE.
        #
        # La premiere version rangeait tout dans « a refaire ». Sur le corpus
        # reel, ca donnait :
        #
        #     233 prise(s) a refaire
        #       232 x  blancs 0.5 a 2.0 s
        #         1 x  bruit de fond
        #
        # Les blancs se ROGNENT — deux secondes de calcul. L'outil allait donc
        # faire recommencer vingt-cinq minutes de lecture a quelqu'un pour du
        # silence qu'un programme enleve tout seul.
        #
        # Un diagnostic qui ne distingue pas le reparable de l'irreparable
        # n'est pas un diagnostic, c'est une facture.
        reparables = []
        a_refaire = []

        # ⚠️ LE RAPPORT SIGNAL/BRUIT NE SE MESURE PAS SANS SILENCE.
        #
        # `_plancher_de_bruit` prend le dixieme percentile de fenetres de
        # 50 ms. Tant qu'il reste du silence en bord, ce percentile tombe
        # dedans et mesure le vrai fond sonore. Sur une prise ROGNEE, il n'y a
        # plus de silence : il tombe alors dans les creux entre les syllabes,
        # qui sont de la voix faible et non du bruit. Le rapport s'effondre
        # mecaniquement.
        #
        # Releve en conditions reelles, le meme corpus avant et apres rognage :
        #
        #     avant  →    1 prise signalee
        #     apres  →  140 prises signalees
        #
        # L'audio etait identique — meilleur, meme. Seule la mesure avait
        # cesse d'etre valide, et elle accusait le traitement qui venait de
        # l'ameliorer.
        #
        # On ne bricole donc pas le seuil : on refuse de conclure quand la
        # mesure n'a plus de sens. Un chiffre faux est pire qu'un silence.
        mesurable = (avant + apres >= 0.2) and not corpus_prepare

        if taux != TAUX_ATTENDU:
            a_refaire.append(f"{taux} Hz au lieu de {TAUX_ATTENDU}")
        if mesurable and snr < SNR_MIN_DB:
            # Le bruit est melange a la voix : aucun traitement ne l'en sort
            # sans abimer la voix elle-meme.
            a_refaire.append(f"bruit de fond (rapport {snr:.0f} dB)")
        elif not mesurable:
            non_mesurables += 1
        if ecrete > ECRETAGE_MAX:
            # L'ecretage a DETRUIT l'information : les cretes coupees ne se
            # reconstituent pas.
            a_refaire.append(f"saturation ({ecrete * 100:.1f} % des echantillons)")
        if avant > BLANC_MAX_S or apres > BLANC_MAX_S:
            reparables.append(f"blancs {avant:.1f} s / {apres:.1f} s")

        if a_refaire:
            problemes.append(f"  {chemin.stem}  {' · '.join(a_refaire)}")
        elif reparables:
            a_rogner.append(f"  {chemin.stem}  {' · '.join(reparables)}")

    # ── La derive : ce qu'aucune prise isolee ne peut montrer ─────────────
    moitie = len(niveaux) // 2
    derive = 0.0
    if moitie:
        debut = sum(niveaux[:moitie]) / moitie
        fin = sum(niveaux[moitie:]) / (len(niveaux) - moitie)
        derive = _db(fin) - _db(debut)

    # ⚠️ CE QUI COMPTE EST LA PAROLE, PAS LA DUREE DES FICHIERS.
    #
    # Le seuil venait d'un calcul en mots par minute — donc du temps de PAROLE.
    # Il etait applique a la duree des fichiers, silences compris. Sur le corpus
    # reel : 19,7 min de fichiers pour 14,9 min de parole. Avant rognage le
    # verdict passait grace au silence ; apres rognage il echouait alors que
    # l'audio etait devenu meilleur.
    #
    # Un seuil doit porter sur la grandeur qui l'a produit.
    print(f"  duree totale      {total / 60:5.1f} min")
    print(f"  parole nette      {parole_nette / 60:5.1f} min")
    print(f"  niveau moyen      {_db(sum(niveaux) / len(niveaux)):5.1f} dB")
    print(f"  derive 1re/2e     {derive:+5.1f} dB", end="")
    print("   ⚠ la distance au micro a change" if abs(derive) > DERIVE_MAX_DB else "")

    if sans_texte:
        print(f"\n  ✗ {len(sans_texte)} audio(s) sans transcription : {sans_texte[:5]}")
    if sans_audio:
        print(f"  ✗ {len(sans_audio)} transcription(s) sans audio : {sans_audio[:5]}")

    if corpus_prepare:
        print("\n  Corpus PREPARE : les silences ont ete rognes, le bruit de fond n'y")
        print("  est donc plus mesurable. Ne rien dire vaut mieux qu'un chiffre faux,")
        print("  et juger les rares prises encore mesurables reviendrait a condamner")
        print("  une minorite par une regle a laquelle le reste echappe.")
        print("  Pour juger le bruit, verifie le corpus D'ORIGINE.")

    if a_rogner:
        print(f"\n  {len(a_rogner)} prise(s) avec des blancs — RIEN A REFAIRE.")
        print("  Le rognage est automatique :  uv run python scripts/preparer_affinage.py")

    if problemes:
        print(f"\n── {len(problemes)} prise(s) VRAIMENT a refaire ──────────────\n")
        for ligne in problemes[:25]:
            print(ligne)
        if len(problemes) > 25:
            print(f"  … et {len(problemes) - 25} autre(s)")
        print("\n  Celles-la ont perdu de l'information : le bruit ne se separe pas")
        print("  de la voix, et une crete ecretee ne se reconstitue pas.")
        print("  Supprime le .wav ET sa ligne dans metadata.csv, puis relance")
        print("  l'enregistreur : il repropose les phrases manquantes.")
        print("  Si elles sont peu nombreuses, preparer_affinage.py les ecarte")
        print("  tout seul — quelques phrases sur deux cent quarante-cinq ne")
        print("  manqueront a personne.")

    print("\n── Verdict ───────────────────────────────────────────────")
    pret = True
    if parole_nette < MINUTES_PAROLE_MIN * 60:
        print(f"  ⏳ {parole_nette / 60:.0f} min de parole sur "
              f"{MINUTES_PAROLE_MIN} minimum — continue.")
        pret = False
    if abs(derive) > DERIVE_MAX_DB:
        print("  ⚠ La derive de niveau apprendra deux distances au modele.")
        print("    Refais les prises les plus faibles, ou toute une moitie.")
        pret = False
    if problemes:
        # Un corpus reste utilisable si les prises perdues sont rares :
        # `preparer_affinage.py` les ecarte, et quelques phrases sur deux cent
        # quarante-cinq ne changent rien a ce que le modele apprend.
        part = len(problemes) / len(wavs)
        print(f"  {'⚠' if part >= 0.05 else '·'} {len(problemes)} prise(s) "
              f"irrecuperable(s) sur {len(wavs)} ({part * 100:.0f} %)"
              + ("" if part >= 0.05 else " — elles seront ecartees"))
        pret = pret and part < 0.05
    if sans_texte or sans_audio:
        print("  ✗ Corpus desaligne — a corriger avant tout entrainement.")
        pret = False

    if pret:
        print("  ✓ Corpus utilisable. Prochaine etape :")
        print("      uv run python scripts/preparer_affinage.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
