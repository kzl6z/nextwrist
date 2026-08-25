"""Transcription : /v1/audio/transcriptions, au format OpenAI.

Nova porte maintenant un troisieme masque. Le format OpenAI a ete choisi
plutot qu'un format maison pour la meme raison que les deux autres : c'est un
standard, donc n'importe quel client sait deja lui parler.

Cote application de bureau, le changement se limite a l'adresse : elle envoyait
deja un formulaire multipart avec un champ `file`, exactement ce qu'attend ce
point d'entree.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

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
        transcription = transcribe.transcrire(
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

    # ── LE PIPELINE DE COMPREHENSION ──
    #
    # C'est ici, et pas dans `transcribe`, parce que comprendre demande le
    # LEXIQUE — donc la memoire — et que la couche voix n'a pas le droit de
    # la consulter. L'orchestrateur le construit, on l'applique.
    comprise = orchestrator.comprendre_la_parole(transcription)

    # `text` reste le champ historique : aucun client existant ne casse. Les
    # champs suivants sont un ajout, et un client qui les ignore obtient
    # exactement le comportement d'avant.
    return {
        "text": comprise.texte,
        "brut": comprise.origine,
        "confiance": comprise.confiance,
        "sure": comprise.sure,
        "a_confirmer": comprise.a_confirmer,
        "question": None if comprise.sure else comprise.question(),
        "intention": (
            {"nom": comprise.intention.nom, "cible": comprise.intention.cible}
            if comprise.intention.reconnue
            else None
        ),
        "corrections": [
            {"entendu": c.entendu, "propose": c.propose, "confiance": round(c.confiance, 3)}
            for c in comprise.corrections
        ],
        "raisons": list(comprise.raisons),
    }


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

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ DEUX LECTURES DU MEME AUDIO — SOUVENT PAR LE MEME MODELE.
    #
    #  Le decoupage « detecter vite, puis relire proprement » suppose deux
    #  outils differents : un petit modele glouton pour chercher un mot, un
    #  meilleur pour comprendre la phrase. Mais rien ne l'IMPOSE, et sur la
    #  machine de reference les deux reglages ont converge vers la meme
    #  valeur — `base`, faisceau 1 — pour les raisons mesurees dans
    #  `settings.py` (un modele resident se paie deux fois).
    #
    #  La deuxieme lecture faisait donc tourner LE MEME MODELE sur LE MEME
    #  AUDIO avec LE MEME faisceau. Seule l'amorce changeait. Releve dans le
    #  journal : 2304 ms et 4096 ms entre la fin de la phrase et la reponse,
    #  dont environ la moitie pour ce doublon.
    #
    #  Quand les deux outils sont identiques, une seule lecture suffit — a
    #  condition de lui donner les DEUX amorces. Celle du reveil apprend le
    #  mot « Nova », celle de la dictee apporte les noms propres de la
    #  memoire : les concatener ne coute rien et ne perd ni l'un ni l'autre.
    #
    #  Quand ils different (dictee en `small`, reveil en `base`), on garde
    #  les deux lectures : la relecture apporte alors reellement autre chose.
    # ══════════════════════════════════════════════════════════════════════
    meme_outil = (
        reglages.whisper_wake_model == reglages.whisper_model
        and reglages.whisper_beam_reveil == reglages.whisper_beam
    )
    amorce = reglages.whisper_amorce
    if meme_outil:
        amorce = f"{reglages.whisper_amorce} {orchestrator.amorce_dictee()}"

    try:
        premiere = transcribe.transcrire(
            audio,
            langue="fr",
            modele=reglages.whisper_wake_model,
            amorce=amorce,
            beam=reglages.whisper_beam_reveil,
        )
        texte = str(premiere)
    except transcribe.TranscriptionIndisponible as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("Detection de reveil impossible : %s", exc)
        return {"wake": False, "text": "", "commande": ""}

    detecte = wake.contient_reveil(texte)

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ PENDANT UNE CONVERSATION OUVERTE, « NOVA » DEVIENT FACULTATIF.
    #
    #  L'application envoie ici tout extrait qui depasse le seuil sonore, et
    #  n'agit que si l'on repond `wake: true`. Il suffit donc de repondre
    #  `true` pendant la fenetre d'ecoute : le comportement voulu apparait
    #  sans qu'une ligne de l'application change.
    #
    #  ⚠️ ET C'EST LA QUE LA FENETRE SE REFERME.
    #
    #  Une phrase de conge — « c'est bon », « mets-toi en veille » — doit
    #  fermer AVANT de decider quoi que ce soit d'autre, sinon elle serait
    #  traitee comme une demande et rouvrirait la fenetre en repondant.
    # ══════════════════════════════════════════════════════════════════════
    from nova.voice import session

    # ⚠️ UN CONGE NE REVEILLE JAMAIS, MEME HORS CONVERSATION.
    #
    # Releve en conditions reelles, sur un simple bruit :
    #
    #     [reveil] 1536 ms → « Oh! »
    #     enchaine sur : « Au revoir. »
    #     Nova : « Au revoir. Le temps est calme et la nuit commence a
    #              s'approcher. »
    #
    # « au revoir » figure dans `wake.VARIANTES_DEBUT` — Whisper, ne
    # connaissant pas « Nova », le rend parfois ainsi. Un bruit transcrit
    # « au revoir » reveillait donc Nova pour lui dire au revoir, et elle
    # repondait.
    #
    # On teste le conge AVANT tout le reste, et sans condition de session :
    # dire au revoir ne peut pas etre une facon de dire bonjour.
    if session.demande_de_veille(texte):
        session.fermer("conge")
        return {"wake": False, "text": texte, "commande": "", "confiance": None}

    enchaine = session.est_ouverte() and not detecte
    if enchaine:
        log.info("Conversation ouverte (%.0f s restantes) : « %s »",
                 session.restant(), texte)
    if detecte:
        session.ouvrir()

    # La question n'est enchainee que si le mot de reveil a ete reconnu
    # franchement. S'il a fallu le deviner, la transcription est mauvaise et
    # la question qui suit ne vaut pas mieux : on laisse l'application
    # reenregistrer proprement plutot que d'envoyer du charabia au modele.
    franc = (detecte and wake.reveil_franc(texte)) or enchaine
    if detecte:
        log.info(
            "Mot de reveil detecte (%s) : « %s »",
            "net" if franc else "approche, question non enchainee",
            texte,
        )

    if not franc:
        return {"wake": detecte, "text": texte, "commande": "", "confiance": None}

    # ══════════════════════════════════════════════════════════════════════
    #  DETECTER VITE, PUIS RELIRE PROPREMENT
    #
    #  Ce point d'entree tourne EN BOUCLE des que le micro depasse un seuil.
    #  Il doit donc etre le plus leger possible, et c'est pourquoi il utilise
    #  le petit modele en decodage glouton : chercher un seul mot connu ne
    #  demande aucune finesse.
    #
    #  Mais la meme transcription servait AUSSI de question. Un reglage
    #  choisi pour reconnaitre « Nova » decidait donc de ce que Nova
    #  comprenait de toute la phrase. Releve en conditions reelles :
    #
    #      dit      « quel est le diametre de la Terre »
    #      entendu  « quelle est-il de germetre de la terre »
    #      dit      « quelles sont les planetes du systeme solaire »
    #      entendu  « quelle sont les planeles de notre systeme solaire »
    #
    #  Aucun de ces mots n'est rare : ce n'etait pas un manque de
    #  vocabulaire, mais le mauvais outil pour la tache.
    #
    #  On relit donc le MEME audio avec les reglages de dictee — meilleur
    #  modele, amorce enrichie de la memoire, pipeline de comprehension.
    #  Le surcout n'est paye que lorsqu'une question suit reellement le mot
    #  de reveil, jamais pendant l'ecoute continue.
    # ══════════════════════════════════════════════════════════════════════
    # Pendant une conversation ouverte, la phrase ENTIERE est la commande :
    # il n'y a pas de mot de reveil a retirer devant.
    commande = texte if enchaine else wake.commande_apres_reveil(texte)
    if not commande:
        return {"wake": True, "text": texte, "commande": "", "confiance": None}

    try:
        # La lecture unique a deja tout ce qu'il faut : meme modele, meme
        # faisceau, et les deux amorces. Relire serait payer une seconde fois
        # pour obtenir le meme texte.
        soignee = (
            premiere
            if meme_outil
            else transcribe.transcrire(
                audio,
                langue="fr",
                amorce=orchestrator.amorce_dictee(),
                beam=reglages.whisper_beam,
            )
        )
        comprise = orchestrator.comprendre_la_parole(soignee)
        relue = (
            comprise.texte
            if enchaine
            else (wake.commande_apres_reveil(comprise.texte) or comprise.texte)
        )
    except Exception as exc:  # noqa: BLE001
        # La relecture est une AMELIORATION, pas une dependance : si elle
        # echoue, la commande du modele de reveil reste utilisable.
        log.warning("Relecture soignee impossible, commande de reveil conservee : %s", exc)
        return {"wake": True, "text": texte, "commande": commande, "confiance": None}

    if relue.lower() != commande.lower():
        log.info("Relecture : « %s » → « %s »", commande, relue)

    return {
        "wake": True,
        "text": texte,
        "commande": relue,
        # Les champs du pipeline de comprehension. Un client qui les ignore
        # obtient exactement le comportement d'avant.
        "confiance": comprise.confiance,
        "sure": comprise.sure,
        "a_confirmer": comprise.a_confirmer,
        "question": None if comprise.sure else comprise.question(),
        "raisons": list(comprise.raisons),
    }


# ══════════════════════════════════════════════════════════════════════════
#  SYNTHESE : /v1/audio/speech
#
#  Le chemin inverse de la transcription, et pour la meme raison. La voix de
#  Nova partait chez ElevenLabs jusqu'au soir ou elle s'est tue :
#
#      "This request exceeds your quota of 10000. You have 3 credits
#       remaining, while 10 credits are required for this request."
#
#  Soixante reponses par mois. Un assistant dont la voix depend d'un quota
#  mensuel n'est pas un assistant personnel, c'est un abonnement qui parle.
#
#  ⚠️ CE POINT D'ENTREE EST DANS LE CHEMIN DE LA PAROLE EN FLUX.
#
#  L'application demande une synthese PAR PHRASE, des la premiere, pendant
#  que le modele ecrit encore les suivantes. Chaque appel est donc court et
#  frequent — c'est exactement le regime ou un chargement de modele a chaque
#  requete se verrait immediatement. Le pipeline est garde resident
#  (`_pipeline`, lru_cache) pour cette raison.
#
#  Nom OpenAI, comme les deux autres points d'entree audio : `/v1/audio/speech`
#  est ce que sait deja appeler n'importe quel client, et le champ s'appelle
#  `input` chez eux. On accepte aussi `text`, parce que l'application de
#  bureau l'envoyait deja sous ce nom et qu'un renommage casserait pour rien.
# ══════════════════════════════════════════════════════════════════════════
@router.post("/audio/speech")
def synthese_vocale(demande: dict) -> Response:
    from nova.voice import synthese

    texte = (demande.get("input") or demande.get("text") or "").strip()
    if not texte:
        raise HTTPException(400, "champ « input » (ou « text ») vide ou absent")

    try:
        wav = synthese.synthetiser(
            texte,
            voix=demande.get("voice") or None,
            langue=demande.get("language") or None,
        )
    except synthese.SyntheseIndisponible as exc:
        # 503 et non 500 : la brique est absente, pas cassee. Meme distinction
        # que pour la transcription — elle dit a l'appelant qu'il n'y a rien a
        # deboguer, seulement quelque chose a installer.
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        # ⚠️ ON RELAIE LA VRAIE CAUSE, ON NE LA RESUME PAS.
        #
        # C'est la lecon directe de `tts.js`, qui lisait le message d'erreur
        # d'ElevenLabs puis l'ecrasait par « cle API refusee ». Trois codes
        # distincts rendaient la meme phrase inutile, et la vraie raison —
        # quota epuise — n'est jamais sortie du programme.
        log.exception("Synthese impossible")
        raise HTTPException(500, f"synthese impossible : {exc}") from exc

    return Response(content=wav, media_type="audio/wav")
