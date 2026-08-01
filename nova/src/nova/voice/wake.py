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

# Confusions observees en conditions reelles : Whisper, ne connaissant pas
# « Nova », le remplace par le mot francais le plus proche. Ces formes sont des
# mots courants — les accepter partout declencherait des reveils intempestifs.
# On ne les accepte donc QU'EN DEBUT de phrase, ou elles ne peuvent guere etre
# autre chose que le mot de reveil mal entendu.
VARIANTES_DEBUT = ("nouveau", "au revoir", "nova s", "no vas")

# ── Le debut du mot est mange par le declenchement ────────────────────────
#
# L'enregistrement demarre quand le micro depasse un seuil sonore : au moment
# ou le seuil est franchi, la premiere consonne est deja prononcee. Whisper ne
# recoit donc pas « nova » mais un fragment. Transcriptions reellement
# observees sur cette machine :
#
#     « Nous va qu'elle a rechelle. »        pour « Nova, quelle heure est-il ? »
#     « C'est au va qu'elle aurait-il ? »    pour la meme phrase
#
# Le point commun est net : la syllabe finale « va » survit toujours, seule
# l'attaque varie. On accepte donc, EN DEBUT D'ENONCE UNIQUEMENT, toute
# attaque plausible suivie de « va ». Ailleurs dans la phrase ce serait bien
# trop large ; en tete, ca ne peut guere etre autre chose.
#
# Faux positif possible : un enonce commencant par « Va… ». Il coute une
# relance inutile — sans commune mesure avec une Nova qui ne repond pas.
_ATTAQUE_ROGNEE = re.compile(
    r"^(?:c est|s est|ce t)?\s*(?:n?[oa]u?[sxz]?)?\s*(?:va|wa)$"
)

# Au-dela de 4 mots, un debut d'enonce n'est plus une attaque rognee.
_MOTS_ATTAQUE_MAX = 4


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation reduite a des espaces."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]+", " ", sans_accents.lower())


def _mots_attaque(texte: str) -> int:
    """Combien de mots ORIGINAUX forment une attaque rognee ? 0 si aucune.

    On teste les prefixes du plus long au plus court et on garde le premier
    qui correspond entierement. Le comptage se fait sur le texte original —
    « c'est » est un mot pour l'utilisateur, deux apres normalisation — pour
    que `commande_apres_reveil` sache exactement quoi retirer.
    """
    mots = texte.split()
    for taille in range(min(_MOTS_ATTAQUE_MAX, len(mots)), 0, -1):
        prefixe = normaliser(" ".join(mots[:taille])).strip()
        if _ATTAQUE_ROGNEE.match(prefixe):
            return taille
    return 0


def reveil_franc(texte: str) -> bool:
    """Le mot de reveil a-t-il ete reconnu SANS tolerance ?

    Sert a decider si on peut faire confiance au RESTE de la phrase. Quand il
    a fallu deviner le mot de reveil, c'est que la transcription est mauvaise :
    la question qui suit l'est tout autant, et il vaut mieux la reenregistrer
    proprement que d'envoyer du charabia au modele.
    """
    if not texte:
        return False
    normalise = " " + " ".join(normaliser(texte).split()) + " "
    return any(f" {v} " in normalise for v in VARIANTES)


def contient_reveil(texte: str) -> bool:
    """Le mot de reveil est-il present dans cette transcription ?"""
    if not texte:
        return False
    mots = normaliser(texte).split()
    if reveil_franc(texte):
        return True
    # Tolerances en debut d'enonce uniquement.
    debut = " ".join(mots[:2])
    if any(debut.startswith(v) for v in VARIANTES_DEBUT):
        return True
    return _mots_attaque(texte) > 0


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

    # Cas des confusions de debut de phrase : la commande est ce qui suit.
    normalises = [normaliser(m).strip() for m in mots]
    for taille in (2, 1):
        if " ".join(normalises[:taille]) in VARIANTES_DEBUT:
            return " ".join(mots[taille:]).strip(" ,.!?;:")

    # Cas de l'attaque rognee : on retire exactement les mots qu'elle occupe.
    taille = _mots_attaque(texte)
    if taille:
        return " ".join(mots[taille:]).strip(" ,.!?;:")
    return ""
