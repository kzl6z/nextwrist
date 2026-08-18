"""Synthese vocale locale (Kokoro).

POURQUOI CETTE BRIQUE EXISTE

La voix de Nova passait par ElevenLabs. Elle s'est arretee un soir, en pleine
conversation, sur ceci :

    "This request exceeds your quota of 10000. You have 3 credits remaining,
     while 10 credits are required for this request."

Dix mille credits par mois, une reponse de Nova ~150 caracteres : environ
soixante reponses mensuelles. Ce n'etait pas une panne, c'etait un plafond — et
il tombait en silence, sur la voix du systeme, masculine et anglophone, sans que
rien n'explique pourquoi.

Un assistant dont la voix depend d'un quota mensuel n'est pas un assistant
personnel : c'est un abonnement qui parle. En ramenant la synthese ici, on gagne
exactement ce que la transcription avait gagne en revenant de l'API vers la
machine — plus de cle, plus de quota, plus de latence reseau, et la voix ne
quitte plus l'ordinateur.

CE QU'ON PERD, ET IL FAUT LE DIRE

Kokoro ne vaut pas ElevenLabs. Leurs modeles tournent sur des GPU de serveur ;
celui-ci fait 82 millions de parametres et tourne sur un M1 partage avec un
modele de langue. On vise « bon », pas « meilleur ». Le choix de `ff_siwis`
n'est pas un compromis technique mais un choix d'oreille : elle a ete retenue
apres ecoute comparee de sept voix (`scripts/essayer-voix-locales.sh`), parce
que c'est celle qui se rapprochait le plus de la voix d'origine.

DEPENDANCE OPTIONNELLE

Comme `faster-whisper`, `kokoro` n'est pas installe par defaut : c'est une
brique lourde (torch, ~350 Mo de modele) qui ne sert qu'a ceux qui veulent
entendre Nova. Elle demarre et fonctionne parfaitement sans.

    brew install espeak-ng          # indispensable au francais, et jamais dit
    uv pip install -e ".[speech]"
"""

from __future__ import annotations

import io
import sys
import time
from functools import lru_cache

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)

#: Frequence de sortie de Kokoro. Ce n'est pas un reglage : le modele produit
#: du 24 kHz, et ecrire autre chose dans l'en-tete WAV donnerait une voix trop
#: lente ou trop aigue — la meme erreur que `reveil-vocal.js` evite en notant le
#: taux REELLEMENT obtenu du micro plutot que celui qu'il avait demande.
ECHANTILLONNAGE = 24000


class SyntheseIndisponible(RuntimeError):
    """La dependance de synthese n'est pas installee."""


@lru_cache(maxsize=1)
def _pipeline(langue: str):
    """Le moteur, charge une seule fois et garde en memoire.

    ⚠️ `maxsize=1` ET PAS DAVANTAGE, DELIBEREMENT.

    Sur la machine de reference (8 Go), Nova tient deja un modele de langue de
    3,3 Go et Whisper. Chaque pipeline supplementaire se paierait deux fois :
    en memoire, puis en lenteur de tout le reste — c'est la mecanique mesuree
    dans `settings.py`, ou un Whisper `small` resident divisait par trois la
    vitesse du modele de langue.

    Une seule langue a la fois est donc un choix, pas une limitation oubliee.
    """
    try:
        from kokoro import KPipeline
    except ImportError as exc:
        raise SyntheseIndisponible(
            "kokoro n'est pas installe.\n"
            'Installe-le :  brew install espeak-ng && uv pip install -e ".[speech]"'
        ) from exc

    depart = time.perf_counter()
    log.info("Chargement du moteur de synthese (langue %s)…", langue)
    pipeline = KPipeline(lang_code=langue)
    log.info("Synthese prete en %.1f s.", time.perf_counter() - depart)
    return pipeline


def _en_wav(echantillons) -> bytes:
    """Enveloppe des flottants [-1, 1] dans un WAV, sans une dependance de plus.

    ⚠️ NI `soundfile` NI `numpy` ICI, ET CE N'EST PAS DE L'ASCETISME.

    La premiere version utilisait `numpy`, importe en tete de `synthetiser` —
    donc AVANT la verification que Kokoro est installe. Sur une machine sans la
    brique de synthese, l'absence de Kokoro remontait donc comme un
    `ModuleNotFoundError: numpy` : un message qui designe la mauvaise
    dependance, pour une panne dont le remede est ailleurs. Exactement le
    defaut qu'on venait de corriger dans `tts.js`, a un etage pres.

    `wave` et `array` sont dans la bibliotheque standard. Le code ne peut donc
    plus se tromper de diagnostic, et il devient testable sans installer un
    gigaoctet de torch — c'est le meme raisonnement que `reveil-vocal.js`, qui
    construit son WAV octet par octet plutot que d'embarquer un encodeur.
    """
    import wave
    from array import array

    # Kokoro rend du flottant dans [-1, 1] ; le WAV veut du 16 bits signe.
    # On BORNE AVANT DE CONVERTIR : sans ca, un depassement repasse par zero en
    # arithmetique entiere et produit un claquement au lieu d'une saturation.
    # Le fichier reste un WAV parfaitement valide — le defaut ne s'entend que
    # sur les syllabes fortes, et aucun test de bout en bout ne le verrait.
    pcm = array("h", (int(max(-1.0, min(1.0, v)) * 32767) for v in echantillons))
    if sys.byteorder == "big":
        pcm.byteswap()   # le WAV est petit-boutiste par definition

    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(ECHANTILLONNAGE)
        fichier.writeframes(pcm.tobytes())
    return tampon.getvalue()


# ══════════════════════════════════════════════════════════════════════════
#  PIPER — le moteur qui pese soixante megaoctets
#
#  POURQUOI UN SECOND MOTEUR PLUTOT QU'UN REMPLACEMENT
#
#  Kokoro est generaliste : il connait toutes ses voix, donc il pese 350 Mo et
#  traine torch derriere lui — environ un gigaoctet resident. Sur une machine
#  de 8 Go qui tient deja un modele de langue de 3,3 Go, ce gigaoctet se paie
#  deux fois : en memoire, puis en lenteur de tout le reste.
#
#  Un modele Piper ne connait qu'UNE voix. Il pese 60 Mo, tourne sur onnx sans
#  torch, et synthetise environ dix fois plus vite. C'est le format d'un modele
#  AFFINE : le jour ou l'on entraine une voix sur mesure, elle arrive
#  exactement sous cette forme, et il n'y a rien a rebrancher.
#
#  Les deux coexistent donc a dessein — `NOVA_VOIX_MOTEUR` choisit. Garder
#  Kokoro permet de comparer a l'oreille sans reinstaller, ce qui est
#  precisement comment la voix a ete choisie la premiere fois.
#
#  ⚠️ PIPER EMBARQUE SON PROPRE espeak-ng.
#
#  Contrairement a Kokoro, il n'a pas besoin du `brew install espeak-ng` qui
#  n'est documente nulle part et sans lequel le francais echoue sur un message
#  incomprehensible. Une dependance systeme de moins, c'est une panne de moins.
# ══════════════════════════════════════════════════════════════════════════
@lru_cache(maxsize=1)
def _voix_piper(modele: str):
    """Charge un modele Piper. `modele` est un nom connu ou un chemin .onnx.

    ⚠️ LE CHEMIN EST CE QUI REND LE CLONE BRANCHABLE SANS UNE LIGNE DE CODE.

    Un modele affine sur une vraie voix arrive sous forme de fichier .onnx. En
    acceptant un chemin ici, on rend son installation aussi simple que :

        NOVA_VOIX_MOTEUR=piper
        NOVA_VOIX_MODELE=/chemin/vers/nova.onnx

    Sans ca, il aurait fallu publier le modele quelque part pour que Piper le
    telecharge — pour un fichier qui n'existe que sur cette machine.
    """
    from pathlib import Path

    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise SyntheseIndisponible(
            "piper n'est pas installe.\n"
            'Installe-le :  uv pip install -e ".[piper]"'
        ) from exc

    depart = time.perf_counter()
    chemin = Path(modele).expanduser()
    if chemin.suffix == ".onnx":
        if not chemin.exists():
            raise SyntheseIndisponible(f"modele Piper introuvable : {chemin}")
        log.info("Chargement du modele de synthese %s…", chemin.name)
        voix = PiperVoice.load(chemin)
    else:
        # Nom de voix du catalogue : Piper le telecharge au premier usage et le
        # garde. `download_dir` par defaut suffit — un chemin a nous obligerait
        # a le recreer sur chaque machine.
        log.info("Chargement du modele de synthese %s…", modele)
        voix = PiperVoice.load(modele, download_dir=None)
    log.info("Synthese prete en %.1f s.", time.perf_counter() - depart)
    return voix


def _synthetiser_piper(texte: str, modele: str) -> bytes:
    """WAV rendu par Piper.

    On passe par `synthesize_wav`, qui ecrit l'en-tete AVEC le taux declare par
    le modele. C'est volontaire : les modeles « medium » sont en 22 050 Hz et
    les « high » en 22 050 aussi, mais rien ne garantit qu'un modele affine le
    soit. Laisser Piper ecrire l'en-tete supprime la classe entiere des bugs de
    frequence — celle qui donne une voix trop lente sans qu'aucun fichier ne
    soit invalide.
    """
    import wave

    # ⚠️ CHARGER AVANT D'OUVRIR LE WAV, ET C'EST LOIN D'ETRE COSMETIQUE.
    #
    # En appelant `_voix_piper` A L'INTERIEUR du `with`, son echec traverse la
    # fermeture du fichier — qui tente alors d'ecrire un en-tete jamais
    # configure et leve a son tour :
    #
    #     wave.Error: # channels not specified
    #
    # L'erreur de menage REMPLACE l'erreur reelle. « modele Piper introuvable »
    # devenait un message sur des canaux audio, et le 503 qui dit quoi
    # installer devenait un 500 qui ne dit rien. Meme mecanique que `tts.js`
    # ecrasant le message d'ElevenLabs, un etage plus bas et sans le vouloir.
    voix = _voix_piper(modele)

    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as fichier:
        voix.synthesize_wav(texte, fichier)
    return tampon.getvalue()


def _synthetiser_kokoro(texte: str, voix: str, langue: str) -> bytes:
    # `_pipeline` d'abord : si la brique manque, on veut l'apprendre ici et
    # nulle part ailleurs.
    moteur = _pipeline(langue)

    # `.tolist()` couvre les tableaux numpy comme les tenseurs torch, sans que
    # ce module ait a savoir lequel Kokoro rend aujourd'hui — ni lequel il
    # rendra demain.
    valeurs: list[float] = []
    for _, _, audio in moteur(texte, voice=voix):
        valeurs.extend(audio.tolist() if hasattr(audio, "tolist") else audio)

    if not valeurs:
        log.warning("Synthese : aucun echantillon produit pour « %s »", texte[:60])
    return _en_wav(valeurs)


def _duree_wav(wav: bytes) -> float:
    """Duree reelle, lue dans l'en-tete — jamais deduite d'un taux suppose."""
    import wave

    try:
        with wave.open(io.BytesIO(wav), "rb") as f:
            return f.getnframes() / f.getframerate()
    except Exception:  # noqa: BLE001
        return 0.0


def synthetiser(texte: str, *, voix: str | None = None, langue: str | None = None) -> bytes:
    """Rend la phrase en WAV. Leve `SyntheseIndisponible` si la brique manque.

    On rend des OCTETS et non un chemin de fichier : l'appelant est une reponse
    HTTP qui les renvoie tels quels. Un fichier temporaire ajouterait une
    ecriture disque, un nettoyage a ne pas oublier, et une course entre deux
    phrases prononcees coup sur coup.
    """
    reglages = get_settings()
    langue = langue or reglages.voix_langue
    voix = voix or reglages.voix_modele

    texte = (texte or "").strip()
    if not texte:
        # Un texte vide n'est pas une erreur : la parole en flux decoupe par
        # phrases, et un fragment de ponctuation seule peut arriver ici. On
        # rend un WAV valide et muet plutot que de faire echouer la lecture.
        return _en_wav([])

    depart = time.perf_counter()
    if reglages.voix_moteur == "piper":
        wav = _synthetiser_piper(texte, voix)
    else:
        wav = _synthetiser_kokoro(texte, voix, langue)

    duree = _duree_wav(wav)
    ecoule = time.perf_counter() - depart

    # Le rapport temps de calcul / duree audio est LA mesure qui compte pour la
    # parole en flux : au-dessus de 1, Nova prend du retard sur elle-meme et la
    # file d'attente des phrases s'allonge sans jamais se resorber.
    log.info(
        "Synthese %s : %d car. → %.1f s d'audio en %.1f s (x%.2f temps reel)",
        reglages.voix_moteur, len(texte), duree, ecoule,
        ecoule / duree if duree else 0.0,
    )
    return wav


def disponible() -> bool:
    """La synthese locale peut-elle servir ? Ne charge rien, ne leve jamais."""
    moteur = get_settings().voix_moteur
    try:
        if moteur == "piper":
            import piper  # noqa: F401
        else:
            import kokoro  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True
