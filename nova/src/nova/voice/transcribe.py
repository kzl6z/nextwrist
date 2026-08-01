"""Transcription locale de la parole (Whisper).

POURQUOI C'EST ICI ET PAS AILLEURS

La transcription est la derniere piece qui faisait sortir des donnees de la
machine : la voix partait chez un tiers pour etre transcrite. En la ramenant
dans Nova Core, on gagne quatre choses d'un coup — plus de cle, plus de quota,
plus de latence reseau, et la voix ne quitte plus l'ordinateur.

DEPENDANCE OPTIONNELLE

`faster-whisper` n'est pas installe par defaut : c'est une brique lourde
(~500 Mo de modele) qui ne sert qu'a ceux qui veulent parler a Nova. Nova
demarre et fonctionne parfaitement sans. C'est la regle du projet : chaque
capacite est facultative, et son absence n'empeche jamais le reste.

    uv pip install -e ".[voice]"
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)


class TranscriptionIndisponible(RuntimeError):
    """La dependance vocale n'est pas installee."""


@lru_cache(maxsize=2)
def _modele(nom: str | None = None):
    """Charge le modele une seule fois, puis le garde en memoire.

    Le premier appel telecharge le modele (~500 Mo pour `small`) et prend
    plusieurs dizaines de secondes. Les suivants sont immediats. D'ou le cache :
    recharger a chaque phrase rendrait la dictee inutilisable.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # noqa: BLE001
        raise TranscriptionIndisponible(
            'faster-whisper n\'est pas installe.\nInstalle-le :  uv pip install -e ".[voice]"'
        ) from exc

    settings = get_settings()
    nom = nom or settings.whisper_model
    log.info("Chargement du modele de transcription %s…", nom)
    # int8 : quantification. Sur un Mac 8 Go c'est le seul reglage raisonnable —
    # trois fois plus leger que float16, pour une perte de precision inaudible
    # sur de la dictee courte.
    return WhisperModel(nom, device="cpu", compute_type=settings.whisper_compute)


def transcrire(
    audio: bytes, *, langue: str = "fr", modele: str | None = None, amorce: str | None = None
) -> str:
    """Transcrit un enregistrement audio en texte.

    `audio` est le contenu brut du fichier (webm, wav, mp4, ogg…). On l'ecrit
    sur disque temporairement parce que le decodeur audio sous-jacent travaille
    sur des fichiers, pas sur de la memoire.
    """
    if len(audio) < 2000:
        return ""  # enregistrement trop court : silence ou declenchement rate

    settings = get_settings()
    moteur = _modele(modele)
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as fichier:
        fichier.write(audio)
        chemin = Path(fichier.name)

    try:
        segments, info = moteur.transcribe(
            str(chemin),
            language=langue,
            vad_filter=settings.whisper_vad,
            beam_size=1,  # 1 = le plus rapide ; suffisant pour de la dictee
            # L'amorce oriente le vocabulaire : c'est ce qui fait la difference
            # entre entendre « Nova » et entendre « Nouveau ».
            initial_prompt=amorce,
            # Chaque extrait est independant : sans ce reglage, le modele se
            # laisse influencer par ce qu'il a transcrit juste avant et derive.
            condition_on_previous_text=False,
        )
        morceaux = [segment.text.strip() for segment in segments]
        texte = " ".join(morceaux).strip()

        # Journalisation detaillee : sans elle, une transcription vide est
        # indiscernable d'un echec de decodage. Les deux se corrigent
        # differemment, il faut donc pouvoir les distinguer.
        log.info(
            "Transcription : %d octets, %.2f s d'audio, %d segment(s) → « %s »",
            len(audio),
            info.duration,
            len(morceaux),
            texte,
        )
        if not texte:
            if info.duration < 0.3:
                log.warning(
                    "Audio decode a %.2f s : le fichier est probablement illisible "
                    "(format ou en-tete incomplet), pas silencieux.",
                    info.duration,
                )
            else:
                log.warning(
                    "%.2f s d'audio mais aucune parole reconnue. "
                    "Micro trop loin, ou filtre VAD trop strict (NOVA_WHISPER_VAD).",
                    info.duration,
                )
        return texte
    finally:
        chemin.unlink(missing_ok=True)


def disponible() -> bool:
    """La transcription locale est-elle utilisable ?"""
    try:
        from faster_whisper import WhisperModel  # noqa: F401

        return True
    except ImportError:
        return False
