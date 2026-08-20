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

import os
import re
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from nova.core import chrono
from nova.logging_setup import get_logger
from nova.settings import get_settings
from nova.voice import corrections as corrections_homophones

log = get_logger(__name__)


class TranscriptionIndisponible(RuntimeError):
    """La dependance vocale n'est pas installee."""


@dataclass(frozen=True)
class Transcription:
    """Le texte, ET ce que le modele pense de son propre travail.

    Rendre une simple chaine faisait perdre `avg_logprob` — la seule mesure
    de doute disponible sans rien calculer. Un objet coute une ligne et rend
    tout le pipeline de comprehension possible.

    `str(transcription)` donne le texte : les appelants qui n'ont besoin que
    de lui ne changent pas.
    """

    texte: str
    #: Confiance du modele : 0 = certain, -1 = il a devine. `None` si inconnue.
    logprob: float | None = None
    duree: float = 0.0

    def __str__(self) -> str:
        return self.texte

    def __bool__(self) -> bool:
        return bool(self.texte)


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


def _modele(nom: str | None = None):
    """Charge le modele une seule fois, puis le garde en memoire.

    Le premier appel telecharge le modele (~500 Mo pour `small`) et prend
    plusieurs dizaines de secondes. Les suivants sont immediats. D'ou le cache :
    recharger a chaque phrase rendrait la dictee inutilisable.

    Le nom est resolu AVANT le cache. Sans ca, `_modele(None)` et
    `_modele("small")` sont deux cles differentes pour le meme modele, et la
    machine en garde deux copies en memoire — sur 8 Go partages avec le modele
    de langue, c'est exactement ce qu'il ne faut pas faire.
    """
    return _charger(nom or get_settings().whisper_model)


@lru_cache(maxsize=2)
def _charger(nom: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # noqa: BLE001
        raise TranscriptionIndisponible(
            'faster-whisper n\'est pas installe.\nInstalle-le :  uv pip install -e ".[voice]"'
        ) from exc

    settings = get_settings()
    fils = _fils_de_calcul()
    log.info("Chargement du modele de transcription %s (%d fil(s))…", nom, fils)
    # int8 : quantification. Sur un Mac 8 Go c'est le seul reglage raisonnable —
    # trois fois plus leger que float16, pour une perte de precision inaudible
    # sur de la dictee courte.
    return WhisperModel(
        nom, device="cpu", compute_type=settings.whisper_compute, cpu_threads=fils
    )


def piste_du_silence(vad_actif: bool) -> str:
    """Ou chercher quand l'audio arrive et que rien n'en sort.

    ⚠️ CE MESSAGE ACCUSAIT UN REGLAGE QUI ETAIT ETEINT.

    Il disait « filtre VAD trop strict (NOVA_WHISPER_VAD) » a chaque
    transcription vide. Or `whisper_vad` vaut False par defaut : la piste
    envoyait chercher la panne dans un reglage qui ne tournait pas.

    Un diagnostic faux coute plus cher que pas de diagnostic — le premier
    fait perdre du temps AVEC confiance. On ne cite donc le VAD que s'il est
    reellement actif, et sinon on nomme les causes qui restent.
    """
    if vad_actif:
        return (
            "filtre VAD actif (NOVA_WHISPER_VAD=true) — il rejette parfois toute "
            "la piste sur un enregistrement court"
        )
    return "micro trop loin, voix trop basse, ou silence apres le mot de reveil"


def _fils_de_calcul() -> int:
    """Combien de coeurs la transcription a le droit de prendre.

    ⚠️ L'ARGUMENT ABSENT ETAIT UN CHOIX, SANS QUE PERSONNE NE L'AIT FAIT.

    `WhisperModel` etait construit sans `cpu_threads`. La valeur par defaut de
    la bibliotheque est 0, et 0 y signifie « tous les coeurs ». Pendant chaque
    transcription, la machine entiere se retrouvait donc sans un seul coeur
    libre — pas seulement Nova : le systeme, le navigateur, le traitement de
    texte ouvert a cote.

    Un assistant qui prend toute la machine pour ecouter une phrase de trois
    secondes n'est pas un assistant. On lui en laisse deux : un pour le
    systeme, un pour ce que la personne est en train de faire.
    """
    demandes = get_settings().whisper_threads
    if demandes > 0:
        return demandes
    return max(1, (os.cpu_count() or 1) - 2)


def transcrire(
    audio: bytes,
    *,
    langue: str = "fr",
    modele: str | None = None,
    amorce: str | None = None,
    beam: int | None = None,
) -> Transcription:
    """Transcrit un enregistrement audio. Retourne le texte ET sa confiance.

    `audio` est le contenu brut du fichier (webm, wav, mp4, ogg…). On l'ecrit
    sur disque temporairement parce que le decodeur audio sous-jacent travaille
    sur des fichiers, pas sur de la memoire.
    """
    if len(audio) < 2000:
        # Enregistrement trop court : silence ou declenchement rate.
        return Transcription(texte="", logprob=None, duree=0.0)

    settings = get_settings()
    # Le chargement du modele est mesure SEPAREMENT du decodage : un cout
    # fixe de plusieurs secondes qui n'apparait qu'au premier appel ne se
    # corrige pas comme un decodage lent, et les melanger a deja fait
    # chercher au mauvais endroit (voir `api/app.py`).
    with chrono.mesurer("whisper — chargement"):
        moteur = _modele(modele)
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as fichier:
        fichier.write(audio)
        chemin = Path(fichier.name)

    debut_decodage = time.perf_counter()
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
        # ── LA CONFIANCE QU'ON JETAIT ──
        #
        # `avg_logprob` est la confiance que Whisper accorde a son PROPRE
        # travail : 0 = certain, -1 = il a devine. Elle est disponible depuis
        # toujours et etait ignoree — c'est pourtant le signal le plus honnete
        # du pipeline, puisque c'est le modele lui-meme qui dit qu'il a doute.
        #
        # On garde la MOYENNE PONDEREE par la duree : un segment d'une demi
        # seconde ne doit pas peser autant qu'un segment de trois.
        segments = list(segments)
        morceaux = [segment.text.strip() for segment in segments]
        texte = " ".join(morceaux).strip()

        duree_totale = sum(max(s.end - s.start, 0.01) for s in segments) or 1.0
        logprob = (
            sum(getattr(s, "avg_logprob", 0.0) * max(s.end - s.start, 0.01) for s in segments)
            / duree_totale
            if segments
            else None
        )

        # ══════════════════════════════════════════════════════════════════
        #  ⚠️ SANS UN SEUL MOT, CE N'EST PAS UNE DEMANDE.
        #
        #  Sur du silence, Whisper ne rend pas toujours une chaine vide : il
        #  rend parfois de la ponctuation seule. Releve en conditions reelles,
        #  a partir d'un enregistrement declenche par un bruit :
        #
        #      [NOVA/ecoute] transcrit en 3284 ms : « . . . »
        #      [NOVA] User Input Received « . . . »
        #      [NOVA] LECTURE de la question : 8313 ms
        #
        #  Ces trois points sont partis au modele de langue, qui a mis huit
        #  secondes a repondre — et a repondu quelque chose, puisqu'un modele
        #  repond toujours. Nova a donc parle toute seule, longuement, sur une
        #  phrase que personne n'avait prononcee.
        #
        #  Le filtre d'hallucinations ne couvrait pas ce cas : il compare a des
        #  formules de sous-titrage, et « ... » n'en est pas une. Il se
        #  declarait meme explicitement incompetent, puisque `_reduire("...")`
        #  vaut la chaine vide et que `est_hallucination` rend False dessus.
        #
        #  Un texte sans aucun caractere alphanumerique ne peut etre ni une
        #  question ni une commande. C'est du silence, quelle que soit la
        #  ponctuation qui l'habille.
        # ══════════════════════════════════════════════════════════════════
        if texte and not _reduire(texte):
            log.info("Ponctuation seule, aucune parole : « %s » — ignore", texte)
            return Transcription(texte="", logprob=logprob, duree=info.duration)

        if est_hallucination(texte):
            log.info("Formule de sous-titrage ignoree (aucune parole) : « %s »", texte)
            return Transcription(texte="", logprob=logprob, duree=info.duration)

        # Homophones : « sais », « c'est », « ces », « ses » et « s'est » se
        # prononcent tous /sɛ/. Aucun reglage de Whisper ne les distingue —
        # le son est reellement identique. On corrige donc apres coup, et
        # uniquement les formes qui n'existent pas en francais.
        texte, corrections = corrections_homophones.corriger(texte)
        if corrections:
            log.info("Homophone corrige : %s → forme correcte", ", ".join(corrections))

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
                    "%.2f s d'audio mais aucune parole reconnue : %s.",
                    info.duration, piste_du_silence(get_settings().whisper_vad),
                )
        return Transcription(texte=texte, logprob=logprob, duree=info.duration)
    finally:
        # Dans le `finally` : une transcription qui echoue au bout de huit
        # secondes a coute ces huit secondes, exactement comme une reussie.
        chrono.enregistrer(
            "whisper — decodage", (time.perf_counter() - debut_decodage) * 1000
        )
        chemin.unlink(missing_ok=True)


def disponible() -> bool:
    """La transcription locale est-elle utilisable ?"""
    try:
        from faster_whisper import WhisperModel  # noqa: F401

        return True
    except ImportError:
        return False
