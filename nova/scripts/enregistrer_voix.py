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
import time
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


def lire_en_boucle(flux, reechantillonneur, arret, garder, patience: float = 5.0) -> None:
    """Lit le flux jusqu'a l'arret, en tolerant « pas encore de donnees ».

    ⚠️ ERRNO 35 N'EST PAS UNE PANNE, C'EST UNE ATTENTE.

    avfoundation livre ses trames de facon ASYNCHRONE. Tant que la carte son
    n'en a pas produit, toute lecture rend EAGAIN — « reessaie plus tard ».
    Le diagnostic le montrait noir sur blanc :

        :0  — ouvre mais ne capte rien ([Errno 35])
        :1  — ouvre mais ne capte rien ([Errno 35])

    Deux micros s'ouvraient parfaitement. J'abandonnais a la premiere
    occurrence, donc systematiquement — la premiere lecture arrive toujours
    avant la premiere trame.

    Le generateur de PyAV se referme quand une exception le traverse : on le
    RECREE plutot que de reprendre celui qui est mort. C'est la subtilite qui
    fait qu'un simple `try` autour de la boucle ne suffit pas.

    `patience` borne l'attente : sans elle, un micro reellement muet ferait
    tourner cette boucle indefiniment, ce qui ressemble a un blocage.
    """
    import av

    limite = time.monotonic() + patience
    recu = False
    while not arret.is_set():
        try:
            for trame in flux.decode(audio=0):
                if arret.is_set():
                    return
                recu = True
                for sortie in reechantillonneur.resample(trame):
                    garder(sortie.to_ndarray().tobytes())
        except av.error.BlockingIOError:
            # Rien de pret. On rend la main brievement, puis on redemande.
            if not recu and time.monotonic() > limite:
                raise TimeoutError(
                    "le peripherique s'ouvre mais ne produit aucun son "
                    f"apres {patience:.0f} s"
                ) from None
            arret.wait(0.01)
        except StopIteration:
            return


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

    def _ouvrir(self):
        """Ouvre le micro dans SON format, pas dans celui qui nous arrange.

        ⚠️ NE PAS IMPOSER `sample_rate` NI `channels`.

        On demandait 16 kHz mono, parce que c'est ce que Whisper attend.
        avfoundation a refuse : « [Errno 35] Resource temporarily
        unavailable ». Un micro capte a SA frequence native — souvent
        48 kHz — et refuser d'ouvrir plutot que de convertir est son droit.

        La conversion, c'est le travail du reechantillonneur juste en
        dessous, et il la fait de toute facon. Imposer le format au materiel
        n'apportait donc rien, et fermait la porte sur la moitie des micros.
        """
        import av

        format_entree = "avfoundation" if sys.platform == "darwin" else "alsa"
        # avfoundation rend parfois EAGAIN au tout premier essai, le temps
        # que le peripherique soit pret. Deux tentatives suffisent.
        derniere: Exception | None = None
        for essai in range(3):
            try:
                return av.open(self.peripherique, format=format_entree)
            except Exception as exc:  # noqa: BLE001
                derniere = exc
                self._arret.wait(0.3 * (essai + 1))
        raise derniere  # type: ignore[misc]

    def _capturer(self) -> None:
        try:
            import av

            flux = self._ouvrir()
            reechantillonneur = av.AudioResampler(format="s16", layout="mono", rate=TAUX)
            lire_en_boucle(flux, reechantillonneur, self._arret, self._morceaux.append)
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


def tester_les_peripheriques() -> int:
    """Essaie chaque entree audio et dit laquelle fonctionne.

    POURQUOI CE MODE EXISTE

    « Resource temporarily unavailable » ne dit pas SI le peripherique
    n'existe pas, S'IL est pris par une autre application, ou si le format
    demande est refuse. Trois causes, un seul message — donc trois tours a
    deviner. Essayer reellement chaque entree repond en une fois.
    """
    import av

    format_entree = "avfoundation" if sys.platform == "darwin" else "alsa"
    print(f"\nRecherche des entrees audio ({format_entree})…\n")

    trouves = 0
    for index in range(6):
        nom = f":{index}" if sys.platform == "darwin" else f"hw:{index}"
        print(f"  {nom:8} ", end="", flush=True)
        try:
            flux = av.open(nom, format=format_entree)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).split("\n")[0][:60]
            print(f"— indisponible ({message})")
            continue

        try:
            # Lire vraiment prouve que le peripherique DONNE du son, pas
            # seulement qu'il s'ouvre : un micro coupe s'ouvre tres bien.
            # On lit par la MEME fonction que l'enregistrement, sinon le
            # diagnostic testerait autre chose que ce qui sert ensuite.
            reechantillonneur = av.AudioResampler(format="s16", layout="mono", rate=TAUX)
            recolte: list[bytes] = []
            arret = threading.Event()
            threading.Timer(1.5, arret.set).start()
            lire_en_boucle(flux, reechantillonneur, arret, recolte.append, patience=3.0)
            octets = sum(len(m) for m in recolte)
            if octets == 0:
                print("— ouvre mais reste muet")
            else:
                print(f"— OK, {duree_secondes(b'0' * octets):.2f} s captees")
                trouves += 1
        except Exception as exc:  # noqa: BLE001
            print(f"— ouvre mais ne capte rien ({str(exc)[:45]})")
        finally:
            flux.close()

    if trouves:
        print("\nUtilise un des peripheriques marques OK :")
        print("    uv run python scripts/enregistrer_voix.py :1\n")
        return 0

    print("""
Aucune entree audio utilisable.

  1. L'application NOVA tient-elle le micro ? Elle ecoute en permanence
     pour detecter le mot de reveil. Ferme-la et refais ce test.
  2. Le Terminal a-t-il l'autorisation ? Reglages Systeme >
     Confidentialite et securite > Microphone > Terminal.
  3. Si rien n'y fait, le mode sans micro est decrit par :
         uv run python scripts/bench_whisper.py
""")
    return 1


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
    if "--tester" in sys.argv:
        return tester_les_peripheriques()

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
            print("""
  Dans l'ordre de probabilite :

  1. L'APPLICATION NOVA TIENT LE MICRO. Elle ecoute en permanence pour
     detecter le mot de reveil, et ne le lache jamais. Ferme-la, puis
     relance ce script.

  2. Le bon micro n'est pas le premier peripherique. Essaie :
         uv run python scripts/enregistrer_voix.py :1
         uv run python scripts/enregistrer_voix.py :2

  3. Le Terminal n'a pas l'autorisation : Reglages Systeme >
     Confidentialite et securite > Microphone > Terminal.

  Rien n'est perdu : la seance reprendra ou elle s'est arretee.
""")
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
