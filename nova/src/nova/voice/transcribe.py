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

import re
import tempfile
import unicodedata
from functools import lru_cache
from pathlib import Path

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)


class TranscriptionIndisponible(RuntimeError):
    """La dependance vocale n'est pas installee."""


# ── Hallucinations de Whisper sur le quasi-silence ────────────────────────
#
# Whisper a ete entraine sur des millions de sous-titres de videos. Quand il
# recoit un extrait sans parole claire, il ne rend pas une chaine vide : il
# produit ce qui terminait le plus souvent ces fichiers. En francais, c'est
# presque toujours la meme poignee de phrases.
#
# Observe sur cette machine, envoye tel quel au modele de langue, qui a mis
# 22 secondes a repondre a une phrase que personne n'avait prononcee :
#
#     « les sous-titres realises par la communaute d'Amara.org »
#
# Ces phrases ne sont jamais des demandes. On les traite comme du silence.
_HALLUCINATIONS = (
    "sous titres realises par la communaute d amara org",
    "sous titrage societe radio canada",
    "sous titrage m6 video",
    "merci d avoir regarde cette video",
    "merci a tous et a bientot",
    "abonnez vous a la chaine",
    "n hesitez pas a vous abonner",
    "amara org",
)


def _reduire(texte: str) -> str:
    """Minuscules, sans accents ni ponctuation : forme de comparaison."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", sans_accents.lower()).split())


def est_hallucination(texte: str) -> bool:
    """Cet extrait est-il une formule de sous-titrage plutot qu'une parole ?

    On n'examine que les extraits courts : au-dela, il y a une vraie phrase
    autour, et supprimer le tout ferait perdre une demande legitime.
    """
    reduit = _reduire(texte)
    if not reduit:
        return False
    if len(reduit) > 90:
        return False
    return any(motif in reduit for motif in _HALLUCINATIONS)


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
    audio: bytes,
    *,
    langue: str = "fr",
    modele: str | None = None,
    amorce: str | None = None,
    beam: int | None = None,
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
            # 1 = glouton, le plus rapide. Au-dela, le modele garde plusieurs
            # hypotheses en parallele et tranche une fois la phrase connue.
            beam_size=beam or settings.whisper_beam,
            # L'amorce oriente le vocabulaire : c'est ce qui fait la difference
            # entre entendre « Nova » et entendre « Nouveau ».
            initial_prompt=amorce,
            # Chaque extrait est independant : sans ce reglage, le modele se
            # laisse influencer par ce qu'il a transcrit juste avant et derive.
            condition_on_previous_text=False,
            # Repli progressif : si le decodage glouton produit un resultat
            # incoherent (repetitions, charabia), Whisper recommence avec plus
            # d'aleatoire au lieu de rendre le charabia. C'est ce qui evite les
            # « ... ... ... » observes en conditions reelles.
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.4,
            # Un extrait juge silencieux ne doit pas etre meuble d'inventions.
            no_speech_threshold=0.6,
        )
        morceaux = [segment.text.strip() for segment in segments]
        texte = " ".join(morceaux).strip()

        if est_hallucination(texte):
            log.info("Formule de sous-titrage ignoree (aucune parole) : « %s »", texte)
            return ""

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
