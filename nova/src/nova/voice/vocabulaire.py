"""Le vocabulaire propre a l'utilisateur, donne d'avance a la transcription.

LE PROBLEME

Whisper transcrit tres bien le francais courant et se trompe sur ce qui est
rare : les noms propres. Releve en conditions reelles :

    « pinata »            ->  « pierre pienita »
    « Charles Aznavour »  ->  « ca qui etait Charles Aznavour »

Aucune augmentation de taille de modele ne resout ca proprement : le mot n'est
pas rare parce que le modele est petit, il est rare dans la langue.

LE LEVIER

Whisper accepte une AMORCE (`initial_prompt`) : un texte qui precede
virtuellement l'audio et oriente fortement son vocabulaire. Un nom propre qui
figure dans l'amorce est reconnu ; le meme nom absent est massacre.

C'est gratuit a l'usage — quelques dizaines de jetons — et c'est le seul
reglage qui agisse specifiquement sur les noms propres.

CE QUE CA A DE PARTICULIER ICI

Nova a deja une memoire : des projets, des personnes, des sujets. Les noms
qu'elle connait sont exactement ceux que l'utilisateur va prononcer. On
construit donc l'amorce A PARTIR DE SA MEMOIRE.

Autrement dit : plus elle te connait, mieux elle t'entend. C'est la seule
boucle du projet ou la memoire ameliore une capacite sensorielle, et elle ne
coute rien.

LIMITE CONNUE

Whisper ne garde que les ~224 derniers jetons de l'amorce. Au-dela, les
premiers termes sont silencieusement ignores. On borne donc explicitement.
"""

from __future__ import annotations

import re
import unicodedata

# ~224 jetons chez Whisper, soit environ 900 caracteres en francais. On reste
# en dessous : depasser ne provoque aucune erreur, seulement une troncature
# silencieuse des premiers termes — le pire des comportements.
BUDGET_AMORCE = 700

# En dessous de trois lettres, ce n'est pas un nom propre mais une initiale ou
# un artefact de decoupage.
LONGUEUR_MIN = 3

# Mots capitalises parce qu'ils commencent une phrase, pas parce qu'ils sont
# des noms propres. Les laisser passer noierait les vrais termes.
_DEBUTS_COURANTS = {
    "Le", "La", "Les", "Un", "Une", "Des", "Ce", "Cette", "Ces", "Il", "Elle",
    "Je", "Tu", "Nous", "Vous", "Ils", "Elles", "On", "Mon", "Ma", "Mes",
    "Son", "Sa", "Ses", "Leur", "Leurs", "Notre", "Votre", "Et", "Ou", "Mais",
    "Donc", "Car", "Si", "Quand", "Pour", "Dans", "Avec", "Sans", "Sur",
    "Depuis", "Apres", "Avant", "Chez", "Par", "Plus", "Tout", "Tous",
}


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def extraire_termes(textes: list[str]) -> list[str]:
    """Retrouve les noms propres dans des phrases libres.

    Heuristique volontairement simple : une majuscule en milieu de phrase, ou
    en debut de phrase si le mot n'est pas un mot-outil courant. Les sigles en
    capitales (RAG, MCP) sont gardes tels quels.

    On garde l'ordre de premiere apparition : les faits arrivent du plus
    recent au plus ancien, et a budget egal un nom recent vaut mieux.
    """
    vus: dict[str, str] = {}
    for texte in textes:
        if not texte:
            continue
        for phrase in re.split(r"[.!?;\n]", texte):
            mots = phrase.split()
            for position, brut in enumerate(mots):
                mot = brut.strip("\"'()[]{}.,:;!?«»…")
                if len(mot) < LONGUEUR_MIN or not mot[0].isupper():
                    continue
                if position == 0 and mot in _DEBUTS_COURANTS:
                    continue
                # Clef sans accents ni casse : « Aznavour » et « aznavour »
                # sont le meme terme, on ne le compte qu'une fois.
                clef = _sans_accents(mot).lower()
                if clef not in vus:
                    vus[clef] = mot
    return list(vus.values())


def construire_amorce(base: str, termes: list[str], budget: int = BUDGET_AMORCE) -> str:
    """Assemble l'amorce finale : les phrases de reference, puis le vocabulaire.

    Le vocabulaire est place EN DERNIER a dessein. Whisper ne conserve que la
    fin de l'amorce ; ce qui compte le plus doit donc s'y trouver.
    """
    base = base.strip()
    if not termes:
        return base

    restant = budget - len(base) - 1
    retenus: list[str] = []
    for terme in termes:
        cout = len(terme) + 2  # le terme, la virgule et l'espace
        if cout > restant:
            continue  # trop long : on passe au suivant plutot que de s'arreter
        retenus.append(terme)
        restant -= cout

    if not retenus:
        return base
    return f"{base} {', '.join(retenus)}."
