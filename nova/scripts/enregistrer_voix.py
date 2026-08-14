"""Enregistre les phrases de reference du banc de transcription.

    uv run python scripts/enregistrer_voix.py

POURQUOI CE SCRIPT EXISTE

`bench_whisper.py` a besoin de phrases dites PAR TOI, avec le texte exact en
regard. Le faire a la main — Dictaphone, exporter en .wav, creer un .txt,
recopier la phrase, recommencer dix fois — prend vingt minutes et se rate
facilement : un fichier mal nomme, une phrase recopiee de travers, et la
mesure ment sans qu'on le voie.

Ici : tu appuies sur Entree, tu dis la phrase affichee, tu appuies sur
Entree. Le .wav et le .txt sont ecrits ensemble, donc toujours d'accord.

AUCUNE DEPENDANCE NOUVELLE

PyAV est deja installe : c'est lui qui decode l'audio pour faster-whisper.
On s'en sert ici pour l'entree micro, via avfoundation sur macOS.
"""

from __future__ import annotations

import sys
import threading
import wave
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "data" / "voix-test"

#: 16 kHz mono : exactement l'entree de Whisper. Enregistrer plus fin ne
#: donnerait rien de plus, et rendrait les fichiers plus lourds pour rien.
TAUX = 16000

#: Le peripherique d'entree par defaut sur macOS. « :0 » veut dire « aucune
#: video, premier peripherique audio ». Se change en argument si le micro
#: utile n'est pas le premier : `uv run python scripts/enregistrer_voix.py :1`
PERIPHERIQUE = ":0"

#: Les phrases a dire. Choisies pour couvrir ce que Nova rate aujourd'hui,
#: et ce qu'elle doit continuer de reussir.
PHRASES: tuple[str, ...] = (
    # Celles qui echouent en conditions reelles.
    "Quel est le diamètre de la Terre ?",
    "Quelles sont les planètes du système solaire ?",
    "Qu'est-ce qu'un trou noir ?",
    "Quelle est la plus grande planète du système solaire ?",
    # Noms propres : ce que le lexique personnel doit rattraper.
    "Qui était Charles Aznavour ?",
    "Ouvre Discord.",
    "Lance EcoleDirecte.",
    "Est-ce qu'Adam est rentré ?",
    # Formes courtes : le raccourci ne doit pas se declencher a tort.
    "Quelle heure est-il ?",
    "Quel jour sommes-nous ?",
    # Phrases longues : la ou le decodage glouton derape.
    "Explique-moi la relativité générale en deux phrases.",
    "Rappelle-moi d'appeler Bérangère demain matin.",
)


def ecrire_wav(chemin: Path, pcm: bytes, taux: int = TAUX) -> None:
    """Ecrit du PCM 16 bits mono dans un fichier WAV lisible par Whisper."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)   # 16 bits
        fichier.setframerate(taux)
        fichier.writeframes(pcm)


def duree_secondes(pcm: bytes, taux: int = TAUX) -> float:
    """Duree d'un flux PCM 16 bits mono."""
    return len(pcm) / 2 / taux


class Micro:
    """Capture le micro jusqu'a ce qu'on demande l'arret.

    Isole dans une classe pour une raison precise : c'est la seule partie
    qu'aucun test ne peut couvrir sans micro. Tout le reste — ecriture WAV,
    nommage, duree — se teste normalement.
    """

    def __init__(self, peripherique: str = PERIPHERIQUE) -> None:
        self.peripherique = peripherique
        self._morceaux: list[bytes] = []
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self.erreur: Exception | None = None

    def _capturer(self) -> None:
        try:
            import av

            format_entree = "avfoundation" if sys.platform == "darwin" else "alsa"
            flux = av.open(
                self.peripherique,
                format=format_entree,
                options={"channels": "1", "sample_rate": str(TAUX)},
            )
            reechantillonneur = av.AudioResampler(format="s16", layout="mono", rate=TAUX)
            for trame in flux.decode(audio=0):
                if self._arret.is_set():
                    break
                for sortie in reechantillonneur.resample(trame):
                    self._morceaux.append(sortie.to_ndarray().tobytes())
            flux.close()
        except Exception as exc:  # noqa: BLE001
            self.erreur = exc

    def demarrer(self) -> None:
        self._arret.clear()
        self._morceaux.clear()
        self.erreur = None
        self._fil = threading.Thread(target=self._capturer, daemon=True)
        self._fil.start()

    def arreter(self) -> bytes:
        self._arret.set()
        if self._fil:
            self._fil.join(timeout=3.0)
        return b"".join(self._morceaux)


def prochain_numero() -> int:
    """Reprend la numerotation la ou elle s'est arretee.

    Relancer le script ne doit pas ecraser ce qui est deja enregistre : on
    peut en faire cinq aujourd'hui et cinq demain.
    """
    existants = [
        int(f.stem) for f in DOSSIER.glob("*.wav") if f.stem.isdigit()
    ]
    return max(existants, default=0) + 1


def main() -> int:
    peripherique = sys.argv[1] if len(sys.argv) > 1 else PERIPHERIQUE
    DOSSIER.mkdir(parents=True, exist_ok=True)
    numero = prochain_numero()

    print(f"""
ENREGISTREMENT DES PHRASES DE REFERENCE

Dossier      : {DOSSIER}
Peripherique : {peripherique}
Deja fait    : {numero - 1} phrase(s)

Pour chaque phrase : Entree pour demarrer, tu la dis, Entree pour arreter.
Tape « p » puis Entree pour passer une phrase, « q » pour arreter la seance.

Parle normalement, comme tu parles a Nova — ni plus fort, ni plus lentement.
Une mesure faite en articulant exagerement ne dirait rien de l'usage reel.

macOS affiche parfois des avertissements sur les cameras (« ContinuityCamera »)
au moment d'ouvrir le micro : il enumere tous les peripheriques, y compris
ceux dont on ne se sert pas. C'est sans consequence, l'enregistrement tourne.
""")

    a_faire = PHRASES[numero - 1 :]
    if not a_faire:
        print(f"Les {len(PHRASES)} phrases sont deja enregistrees.")
        print("Lance la mesure :  uv run python scripts/bench_whisper.py\n")
        return 0

    enregistrees = 0
    for phrase in a_faire:
        print(f"\n  [{numero}/{len(PHRASES)}]  « {phrase} »")
        reponse = input("      Entree pour demarrer > ").strip().lower()
        if reponse == "q":
            break
        if reponse == "p":
            continue

        micro = Micro(peripherique)
        micro.demarrer()
        input("      ● enregistrement… Entree pour arreter > ")
        pcm = micro.arreter()

        if micro.erreur is not None:
            print(f"\n  Micro inaccessible : {micro.erreur}")
            print("\n  Sur macOS, verifie que le Terminal a le droit d'acceder au")
            print("  microphone : Reglages Systeme > Confidentialite > Microphone.")
            print("  Si le bon micro n'est pas le premier, essaie :")
            print("      uv run python scripts/enregistrer_voix.py :1\n")
            return 1

        duree = duree_secondes(pcm)
        if duree < 0.4:
            print(f"      trop court ({duree:.1f} s) — on recommence cette phrase.")
            continue

        audio = DOSSIER / f"{numero:02d}.wav"
        ecrire_wav(audio, pcm)
        audio.with_suffix(".txt").write_text(phrase, encoding="utf-8")
        print(f"      enregistre : {audio.name}  ({duree:.1f} s)")
        numero += 1
        enregistrees += 1

    total = len(list(DOSSIER.glob("*.wav")))
    print(f"\n{enregistrees} phrase(s) enregistree(s), {total} au total.")
    if total >= 8:
        print("\nAssez pour trancher. Lance la mesure :")
        print("    uv run python scripts/bench_whisper.py\n")
    else:
        print(f"\nIl en faut au moins huit pour un chiffre fiable ({total} pour l'instant).")
        print("Relance ce script quand tu veux, il reprend ou il s'est arrete.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
