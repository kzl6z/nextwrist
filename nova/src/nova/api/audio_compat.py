"""Transcription : /v1/audio/transcriptions, au format OpenAI.

Nova porte maintenant un troisieme masque. Le format OpenAI a ete choisi
plutot qu'un format maison pour la meme raison que les deux autres : c'est un
standard, donc n'importe quel client sait deja lui parler.

Cote application de bureau, le changement se limite a l'adresse : elle envoyait
deja un formulaire multipart avec un champ `file`, exactement ce qu'attend ce
point d'entree.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from nova import orchestrator
from nova.logging_setup import get_logger
from nova.settings import get_settings
from nova.voice import transcribe, wake

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["audio"])


@router.post("/audio/transcriptions")
def transcriptions(
    file: UploadFile = File(...),
    # Champs acceptes puis ignores. Les clients en envoient de toutes sortes
    # (model, model_id, language, language_code) : les refuser ferait echouer
    # la requete pour une raison sans importance.
    model: str | None = Form(None),
    model_id: str | None = Form(None),
    language: str | None = Form(None),
    language_code: str | None = Form(None),
) -> dict:
    """Transcrit un enregistrement. Retourne {"text": "..."}."""
    audio = file.file.read()
    langue = (language or language_code or "fr")[:2].lower()

    try:
        texte = transcribe.transcrire(
            audio,
            langue=langue,
            # L'amorce est construite par l'orchestrateur : elle contient les
            # noms propres que Nova a en memoire, et c'est lui qui a le droit
            # de consulter la memoire.
            amorce=orchestrator.amorce_dictee(),
            beam=get_settings().whisper_beam,
        )
    except transcribe.TranscriptionIndisponible as exc:
        # 503 et non 500 : le service est absent, pas casse. La distinction
        # compte pour le client, qui peut alors se replier proprement.
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.error("Transcription impossible : %s", exc)
        raise HTTPException(500, f"transcription impossible : {exc}") from exc

    return {"text": texte}


@router.post("/audio/wake")
def detection_reveil(file: UploadFile = File(...)) -> dict:
    """Ce court extrait audio contient-il le mot de reveil ?

    Appele en boucle par l'application de bureau des que le micro depasse un
    seuil sonore. Doit donc etre RAPIDE : on utilise le petit modele dedie,
    pas celui de la dictee.

    Retourne aussi `commande` : si l'utilisateur a dit « Nova, quelle heure
    est-il », on evite de lui faire repeter sa question.
    """
    audio = file.file.read()
    reglages = get_settings()
    try:
        texte = transcribe.transcrire(
            audio,
            langue="fr",
            modele=reglages.whisper_wake_model,
            amorce=reglages.whisper_amorce,
            beam=reglages.whisper_beam_reveil,
        )
    except transcribe.TranscriptionIndisponible as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("Detection de reveil impossible : %s", exc)
        return {"wake": False, "text": "", "commande": ""}

    detecte = wake.contient_reveil(texte)

    # La question n'est enchainee que si le mot de reveil a ete reconnu
    # franchement. S'il a fallu le deviner, la transcription est mauvaise et
    # la question qui suit ne vaut pas mieux : on laisse l'application
    # reenregistrer proprement plutot que d'envoyer du charabia au modele.
    franc = detecte and wake.reveil_franc(texte)
    if detecte:
        log.info(
            "Mot de reveil detecte (%s) : « %s »",
            "net" if franc else "approche, question non enchainee",
            texte,
        )
    return {
        "wake": detecte,
        "text": texte,
        "commande": wake.commande_apres_reveil(texte) if franc else "",
    }
