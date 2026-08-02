"""Correction des homophones que la transcription confond.

LE PROBLEME

En francais, « sais », « c'est », « ces », « ses » et « s'est » se prononcent
tous /sɛ/. Whisper choisit d'apres le contexte, et se trompe. Releve en
conditions reelles :

    « que sais-tu de moi ? »  ->  « que c'est-tu de moi ? »

Aucun reglage de Whisper ne corrige ca : le son est reellement identique.

LA REGLE QU'ON S'IMPOSE

On ne corrige QUE des formes agrammaticales — des suites de mots qui
n'existent pas en francais correct. « c'est-tu » n'est pas du francais ;
« c'est tout » l'est. La premiere peut etre corrigee sans risque, la seconde
ne doit jamais etre touchee.

C'est ce qui separe une correction d'un pari. Un correcteur qui remplace tout
ce qui sonne pareil casse plus de phrases justes qu'il n'en repare, et le fait
en silence.

CE QU'ON NE FAIT PAS

« il s'est tu » (verbe se taire) est parfaitement correct. La forme non
tiretee de « s'est » est donc exclue, alors que « s'est-tu » — impossible —
est corrigee. Un caractere de difference, deux traitements opposes.
"""

from __future__ import annotations

import re

# Chaque entree : (motif, remplacement, pourquoi cette forme est impossible).
# Le « pourquoi » n'est pas decoratif : il est la condition d'admission dans
# cette table. Si on ne sait pas dire pourquoi la forme est fausse, la regle
# n'y entre pas.
REGLES: tuple[tuple[str, str, str], ...] = (
    (
        r"\b(?:c'est|ces|ses|sait|s'est)-tu\b",
        "sais-tu",
        "inversion interrogative : seul « sais-tu » existe a la deuxieme personne",
    ),
    (
        # Sans trait d'union, mais « s'est tu » est exclu : c'est le passe
        # compose de « se taire », parfaitement correct.
        #
        # Le `\b` final suffit a proteger « ces tulipes » et « ses tuiles » :
        # dans ces mots, « tu » n'est pas suivi d'une frontiere. Une garde
        # supplementaire avait ete ajoutee par prudence et bloquait le cas
        # reel — « que c'est tu de moi » — sans rien proteger de plus.
        r"\b(?:c'est|ces|ses)\s+tu\b",
        "sais-tu",
        "« c'est tu », « ces tu », « ses tu » n'existent pas",
    ),
    (
        r"\b(je|tu)\s+(?:c'est|ces|ses|s'est)\b",
        r"\1 sais",
        "apres « je » ou « tu », le verbe savoir s'ecrit « sais »",
    ),
    (
        r"\bqu'est-ce que tu (?:c'est|ces|ses)\b",
        "qu'est-ce que tu sais",
        "meme cas, dans la tournure interrogative complete",
    ),
)

_COMPILEES = tuple((re.compile(motif, re.IGNORECASE), remplacement) for motif, remplacement, _ in REGLES)


def corriger(texte: str) -> tuple[str, list[str]]:
    """Applique les corrections. Retourne le texte et la liste de ce qui a change.

    Retourner les changements plutot que de corriger en silence : une
    correction invisible qui se trompe est indebogable.
    """
    if not texte:
        return texte, []

    changements: list[str] = []
    corrige = texte
    for motif, remplacement in _COMPILEES:
        nouveau = motif.sub(remplacement, corrige)
        if nouveau != corrige:
            for trouve in motif.findall(corrige):
                fragment = trouve if isinstance(trouve, str) else " ".join(trouve)
                changements.append(fragment)
            corrige = nouveau
    return corrige, changements
