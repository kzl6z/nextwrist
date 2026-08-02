"""Encodage phonetique du francais : comparer des mots par leur SON.

POURQUOI CE MODULE EST LA PIECE PORTEUSE

Whisper se trompe sur ce qui est rare. Ses erreurs ne sont pas aleatoires :
elles sonnent JUSTE. Releve en conditions reelles :

    « pinata »   ->  « pierre pienita »
    « Ollama »   ->  « aux lamas »
    « Aznavour » ->  « as-tu na vous »

Comparer les lettres ne sert a rien — « ollama » et « aux lamas » n'ont
presque aucune lettre commune a la meme place. Comparer les SONS, si : les
deux donnent /olama/.

C'est la seule facon de rattraper un nom propre massacre sans risquer de
toucher a une phrase correcte.

CE QUE FAIT CE FICHIER, ET CE QU'IL NE FAIT PAS

Il transforme un mot francais en une suite de sons approximative. Ce n'est
pas de l'API : c'est un code de comparaison, volontairement grossier.

    « Ollama »    -> OLAMA
    « aux lamas » -> OLAMA      identiques : candidat a la correction
    « bonjour »   -> BOZUR
    « bonsoir »   -> BOSWAR     differents : aucun risque de confusion

Il ne sait pas lire un mot etranger selon sa langue d'origine, ni gerer les
liaisons entre mots. Ces deux limites sont assumees : la premiere se traite
par le lexique personnel, la seconde ne se pose pas puisqu'on encode des
groupes de mots entiers.

POURQUOI PAS SOUNDEX OU METAPHONE

Ils sont concus pour l'anglais. « eau » y devient E-A-U ; en francais c'est
un seul son, /o/. Sur des noms propres francais, ils rapprochent des mots qui
ne se ressemblent pas et separent des mots identiques a l'oreille.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Les digrammes et trigrammes du francais, dans l'ordre ou il faut les
# traiter : du plus long au plus court, sinon « eau » serait vu comme « e »
# puis « au ». C'est la seule subtilite de tout le fichier.
_GROUPES: tuple[tuple[str, str], ...] = (
    # Nasales — a traiter tot, avant que les voyelles soient reduites.
    ("aient", "E"), ("eaient", "E"),
    ("ain", "1"), ("aim", "1"), ("ein", "1"), ("eim", "1"),
    ("oin", "W1"),
    ("ien", "J1"),
    ("an", "A"), ("am", "A"), ("en", "A"), ("em", "A"),
    ("in", "1"), ("im", "1"), ("yn", "1"), ("ym", "1"),
    ("on", "O"), ("om", "O"),
    ("un", "1"), ("um", "1"),
    # Voyelles composees.
    ("eau", "O"), ("au", "O"),
    ("eu", "2"), ("oeu", "2"), ("œu", "2"), ("œ", "2"),
    ("ou", "U"), ("où", "U"), ("oû", "U"),
    ("oi", "WA"), ("oy", "WAJ"),
    ("ai", "E"), ("ei", "E"), ("ay", "EJ"),
    # Consonnes composees.
    ("sch", "S"), ("ch", "S"), ("ph", "F"), ("th", "T"),
    ("gn", "N"),
    ("qu", "K"), ("q", "K"),
    ("ll", "L"),
    ("cc", "K"), ("ss", "S"), ("tt", "T"), ("nn", "N"), ("mm", "M"),
    ("pp", "P"), ("rr", "R"), ("ff", "F"), ("dd", "D"), ("bb", "B"),
    ("gg", "G"),
)

# Consonnes muettes en fin de mot. « bonjour » et « bonjours » doivent donner
# le meme code : c'est exactement le genre de difference que Whisper produit.
_FINALES_MUETTES = ("s", "t", "d", "x", "z", "p", "g")

_VOYELLES = set("aeiouy")


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


@lru_cache(maxsize=4096)
def coder_mot(mot: str) -> str:
    """Le code phonetique d'UN mot. Chaine vide si le mot est vide.

    Mis en cache : le meme mot revient sans arret d'une phrase a l'autre, et
    l'encodage est purement fonctionnel.
    """
    m = _sans_accents(mot).lower()
    m = re.sub(r"[^a-z]", "", m)
    if not m:
        return ""

    # « h » est toujours muet en francais. On le retire tot pour que « th »
    # et « ch » — deja traites — ne soient pas reconstitues par erreur.
    m = m.replace("h", "") if not m.startswith("h") else m[1:].replace("h", "")

    # Finale muette : uniquement apres une consonne ou une voyelle, jamais
    # sur un mot d'une seule lettre.
    if len(m) > 2 and m[-1] in _FINALES_MUETTES:
        # « e » final precedent une muette : « ils portent » -> /pOrt/
        m = m[:-1]
    if len(m) > 2 and m.endswith("e"):
        m = m[:-1]

    for groupe, son in _GROUPES:
        m = m.replace(groupe, son)

    sortie: list[str] = []
    for i, lettre in enumerate(m):
        if lettre.isupper():          # deja code par un groupe
            sortie.append(lettre)
            continue
        suivante = m[i + 1] if i + 1 < len(m) else ""
        if lettre == "c":
            sortie.append("S" if suivante in "eiy" else "K")
        elif lettre == "g":
            sortie.append("Z" if suivante in "eiy" else "G")
        elif lettre == "j":
            sortie.append("Z")
        elif lettre == "s":
            # « s » entre deux voyelles se prononce /z/ : « rose », « base ».
            precedente = m[i - 1] if i else ""
            sortie.append("Z" if precedente in _VOYELLES and suivante in _VOYELLES else "S")
        elif lettre == "x":
            sortie.append("KS")
        elif lettre in "aeiouy":
            # Toutes les voyelles simples sont ramenees a trois timbres. Plus
            # de finesse rendrait le code plus juste et la comparaison moins
            # utile : on cherche les mots PROCHES, pas les mots identiques.
            sortie.append({"a": "A", "e": "E", "i": "I", "o": "O", "u": "U", "y": "I"}[lettre])
        elif lettre == "w":
            sortie.append("V")
        else:
            sortie.append(lettre.upper())

    # Repetitions consecutives : « ss » deja traite, mais un groupe peut en
    # recreer. « AA » et « A » sont le meme son tenu.
    code = re.sub(r"(.)\1+", r"\1", "".join(sortie))
    return code


def coder(texte: str) -> str:
    """Le code phonetique d'une suite de mots, sans separateur.

    Sans separateur a dessein : c'est ce qui rend « aux lamas » et « Ollama »
    comparables. Whisper coupe les mots ou il veut, et cette liberte est
    justement la source de la moitie de ses erreurs.
    """
    return "".join(coder_mot(mot) for mot in texte.split())


def distance(a: str, b: str) -> int:
    """Distance d'edition entre deux chaines. Classique, et volontairement ici.

    Ecrite plutot qu'importee : c'est vingt lignes, sans dependance, et la
    dependance evitee est une de moins a suivre pendant dix ans.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courante = [i]
        for j, cb in enumerate(b, 1):
            courante.append(
                min(
                    precedente[j] + 1,          # suppression
                    courante[j - 1] + 1,        # insertion
                    precedente[j - 1] + (ca != cb),  # substitution
                )
            )
        precedente = courante
    return precedente[-1]


def ressemblance(a: str, b: str) -> float:
    """Proximite phonetique de deux textes, de 0 (rien) a 1 (identique).

    C'est cette valeur qui sert de score de confiance a une correction. Elle
    est normalisee par la longueur : trois erreurs sur un mot de quatre
    lettres et trois erreurs sur une phrase de quarante ne pesent pas pareil.
    """
    ca, cb = coder(a), coder(b)
    if not ca and not cb:
        return 1.0
    if not ca or not cb:
        return 0.0
    return 1.0 - distance(ca, cb) / max(len(ca), len(cb))
