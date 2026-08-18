"""Le corpus d'enregistrement pour cloner une voix.

⚠️ CE BANC EXISTE PARCE QU'UN CORPUS TROP PAUVRE NE RATE PAS BRUYAMMENT.

Un affinage sous-alimente ne leve aucune erreur et ne produit aucun
avertissement : il rend simplement une voix metallique, approximative, dont
personne ne sait dire pourquoi elle sonne faux. Le defaut est dans les donnees,
et les donnees ont l'air parfaitement normales.

La premiere version du corpus comptait quatre-vingt-dix phrases. C'est la
quantite qui PARAIT raisonnable a la lecture — et qui ne fait que six minutes
dites, pour un besoin de vingt a trente. Le comptage l'a dit tout de suite ; la
relecture ne l'aurait jamais dit.

Meme histoire pour la couverture phonetique : « œ » etait absent des deux
premieres versions, sur cent quatre-vingt-cinq phrases. Or « cœur », « sœur »,
« œuvre », « œil » sont des mots du quotidien. Un phoneme absent du corpus
n'est pas mal prononce par le modele : il est INVENTE, par interpolation depuis
ce qu'il connait — et ca s'entend precisement sur les mots les plus courants.

Ce banc mesure les deux. Une couverture phonetique se compte ; elle ne se juge
pas a l'oeil.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "enregistrer_clone", RACINE / "scripts" / "enregistrer_voix_clone.py"
)
enregistrer_clone = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enregistrer_clone)

CORPUS = enregistrer_clone.CORPUS

#: Debit de lecture soignee, a voix haute, avec les pauses. Volontairement
#: prudent : surestimer le debit ferait croire le corpus plus long qu'il n'est,
#: ce qui est exactement l'erreur qu'on cherche a empecher.
MOTS_PAR_MINUTE = 150

#: Plancher de l'affinage Piper depuis un point de depart francais.
MINUTES_MINIMUM = 18


def test_le_corpus_dure_assez_longtemps():
    """⚠️ SIX MINUTES PARAISSENT SUFFISANTES ET NE LE SONT PAS."""
    mots = sum(len(phrase.split()) for phrase in CORPUS)
    minutes = mots / MOTS_PAR_MINUTE

    assert minutes >= MINUTES_MINIMUM, (
        f"{mots} mots = ~{minutes:.0f} min, il en faut au moins "
        f"{MINUTES_MINIMUM}. Un affinage sous-alimente rend une voix "
        f"approximative sans jamais le signaler."
    )


def test_aucune_phrase_en_double():
    """Une phrase dite deux fois pese double dans l'apprentissage.

    Sans intention : elle deforme la distribution vers ses propres sons.
    """
    assert len(CORPUS) == len(set(CORPUS))


def test_les_sons_du_francais_sont_tous_representes():
    """Un phoneme absent n'est pas mal appris : il est invente."""
    texte = " ".join(CORPUS).lower()

    rares = {
        son: texte.count(son)
        for son in ("on", "an", "en", "in", "ou", "oi", "ui", "eu", "ai",
                    "au", "gn", "ch", "ill", "tion", "œ", "ê", "à", "ç")
        if texte.count(son) < 5
    }

    assert not rares, f"sons trop rares dans le corpus : {rares}"


def test_les_questions_sont_representees():
    """⚠️ LA PROSODIE MONTANTE S'APPREND, ELLE NE SE DEDUIT PAS.

    C'est le defaut le plus audible des clones faits a la va-vite : toutes les
    questions tombent a plat, parce que le corpus n'en contenait presque pas.
    """
    questions = [p for p in CORPUS if p.rstrip().endswith("?")]

    assert len(questions) >= 15, f"seulement {len(questions)} questions"


def test_les_chiffres_sont_ecrits_en_toutes_lettres():
    """Le corpus doit s'ecrire COMME IL SE PRONONCE.

    « 20 h » se lit « vingt heures », mais l'entraineur reçoit la chaine telle
    quelle et alignerait « 2 », « 0 », « h » sur des sons qui n'existent pas.
    Le format LJSpeech attend deja du texte normalise ; l'ecrire ainsi des le
    depart evite une passe de normalisation, donc une occasion de se tromper.
    """
    with_chiffres = [p for p in CORPUS if any(c.isdigit() for c in p)]

    assert not with_chiffres, f"chiffres non ecrits en lettres : {with_chiffres[:3]}"


def test_les_longueurs_sont_variees():
    """Des phrases toutes courtes donnent un debit hache, toutes longues un
    modele qui ne sait pas s'arreter. Il faut les deux."""
    longueurs = [len(p.split()) for p in CORPUS]

    assert min(longueurs) <= 6, "aucune phrase vraiment courte"
    assert max(longueurs) >= 25, "aucune phrase vraiment longue"


def test_le_taux_est_celui_de_piper_et_pas_celui_de_whisper():
    """⚠️ 16 kHz DONNERAIT UN MODELE SOURD, SANS RIEN CASSER.

    Le banc de transcription enregistre en 16 kHz — l'entree de Whisper. Piper
    « medium » travaille en 22 050. Enregistrer plus bas puis reechantillonner
    vers le haut ne rend pas les aigus : ils n'ont jamais ete captes. Tous les
    fichiers resteraient parfaitement valides.
    """
    assert enregistrer_clone.TAUX == 22050
