"""Detection du mot de reveil.

Le mot de reveil de l'application de bureau reposait sur la reconnaissance
vocale de Chromium, qui ne fonctionne pas dans Electron : il n'a donc jamais
pu marcher. On le reconstruit ici, en local.

PRINCIPE

Plutot qu'un moteur specialise (openWakeWord et consorts, qui demandent une
chaine audio complete et des modeles supplementaires), on reutilise Whisper
qui est deja la. Deux precautions rendent ca viable :

  1. Un modele minuscule (`tiny`, ~75 Mo). Reconnaitre UN mot ne demande
     aucune finesse, et il repond en ~150 ms.
  2. Cote application, on ne transcrit QUE quand le micro depasse un seuil
     sonore. Dans une piece silencieuse, il ne se passe strictement rien —
     c'est ce qui rend l'ecoute permanente supportable sur une petite machine.

TOLERANCE AUX ERREURS DE TRANSCRIPTION

« Nova » est un mot court, souvent mal transcrit a l'oral : « nova », « no va »,
« nowa », « novak ». On accepte donc plusieurs formes. Le cout d'un faux
positif est faible (Nova repond « dites-moi » pour rien) ; celui d'un faux
negatif est eleve (elle ne repond pas et on la croit cassee).
"""

from __future__ import annotations

import re
import unicodedata

# Formes acceptees. Volontairement genereuses : mieux vaut se reveiller de
# temps en temps pour rien que de rater un appel.
VARIANTES = ("nova", "no va", "nowa", "novak", "nauva", "novas")
# Variantes tenant en UN mot — utilisees pour decouper la phrase.
VARIANTES_MOT = tuple(v for v in VARIANTES if " " not in v)


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation reduite a des espaces."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]+", " ", sans_accents.lower())


def contient_reveil(texte: str) -> bool:
    """Le mot de reveil est-il present dans cette transcription ?"""
    if not texte:
        return False
    normalise = " " + " ".join(normaliser(texte).split()) + " "
    return any(f" {v} " in normalise for v in VARIANTES)


def commande_apres_reveil(texte: str) -> str:
    """Ce qui suit le mot de reveil, s'il y a quelque chose.

    Permet de dire « Nova, quelle heure est-il ? » d'un seul trait, sans
    attendre la relance. Si l'utilisateur n'a dit que « Nova », on renvoie une
    chaine vide et l'application demande la suite.
    """
    # On decoupe le texte ORIGINAL et on ne normalise que pour comparer :
    # la commande doit parvenir au modele telle qu'elle a ete dite. Normaliser
    # la sortie transformerait « qu'est-ce que » en « qu est ce que ».
    mots = texte.split()
    for i, mot in enumerate(mots):
        if normaliser(mot).strip() in VARIANTES_MOT:
            return " ".join(mots[i + 1 :]).strip(" ,.!?;:")
    return ""
