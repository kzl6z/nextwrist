"""Cette phrase m'est-elle adressee, ou est-ce que tu reflechis tout haut ?

LE DEFAUT

Pendant une conversation ouverte, « Nova » devient facultatif : tout ce qui
depasse le seuil sonore part comme une demande. C'est ce qui rend la
conversation naturelle — et c'est aussi ce qui fait que Nova repond quand on
pense a voix haute.

    « bon… il faudrait que je revoie le refroidissement »
    Nova : « Le refroidissement d'un moteur electrique repose sur… »

Personne n'avait rien demande. L'assistant qui coupe la parole pendant qu'on
reflechit est pire que celui qui se tait : on finit par ne plus penser a
voix haute devant lui, et la fenetre d'ecoute ne sert plus a rien.

⚠️ CE MODULE NE DEVINE PAS CE QUE TU VEUX. IL LIT UNE PROPRIETE DE GRAMMAIRE.

C'est la seule chose qui le separe d'une liste de commandes deguisee. Le
francais MARQUE le destinataire : un imperatif, un « tu », une interrogative
s'adressent a quelqu'un ; « il faudrait que je… » decrit une action dont le
sujet est celui qui parle. On ne decide pas de ce que la phrase veut dire —
on lit qui elle designe comme agent.

⚠️ ET ON SE TROMPE DANS UN SEUL SENS.

Ne pas repondre a un ordre est une regression : ca casse ce qui marchait, et
c'est la faute la plus chere ici. Repondre a une pensee est le defaut qu'on
corrige, mais il reste rattrapable — on se tait, on recommence.

Le defaut est donc « c'est pour moi ». Le silence demande un signal POSITIF
de deliberation ET l'absence de tout signe d'adresse. Les constructions
retenues sont celles qui ne peuvent pas etre une demande — pas celles qui
sont souvent des pensees.

⚠️ CE QU'IL NE SAIT PAS FAIRE, ET QU'IL NE FAUT PAS LUI PRETER.

Il ne distingue pas une phrase adressee a quelqu'un d'autre dans la piece
d'une phrase adressee a Nova : « tu peux me passer le sel » porte toutes les
marques de l'adresse. Le micro ouvert reste le micro ouvert, et c'est la
fenetre courte qui borne ce risque, pas ce module.
"""

from __future__ import annotations

import re
import unicodedata


def _plat(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", sans_accents.lower())).strip()


# ══════════════════════════════════════════════════════════════════════════
#  CE QUI DESIGNE NOVA — et qui gagne toujours
# ══════════════════════════════════════════════════════════════════════════

#: Le nom, la deuxieme personne, ou une interrogative en tete.
#:
#: ⚠️ CES SIGNES L'EMPORTENT SUR TOUT LE RESTE, SANS EXCEPTION.
#:
#: « Nova, il faudrait que je revoie le refroidissement » porte le marqueur
#: de deliberation ET le nom. Se taire la-dessus serait ignorer quelqu'un qui
#: vient de vous appeler par votre nom.
#:
#: De meme « qu'est-ce que je devrais faire ? » : la question est posee a
#: quelqu'un, meme si son sujet grammatical est « je ».
_ADRESSE = re.compile(
    r"\bnova\b"
    r"|\b(?:tu|te|toi|ton|ta|tes|vous|votre)\b"
    r"|\bt'(?:as|es|a|e)\b"
    r"|^(?:qu'est ce que|qu est ce que|est ce que|comment|pourquoi|combien|"
    r"quand|quel|quelle|quels|quelles|qui|ou)\b"
)


# ══════════════════════════════════════════════════════════════════════════
#  CE QUI DESIGNE CELUI QUI PARLE
# ══════════════════════════════════════════════════════════════════════════

#: Deliberer sur sa PROPRE action a venir.
#:
#: ⚠️ LISTE COURTE, ET C'EST LE CŒUR DE LA CONCEPTION.
#:
#: J'y avais mis « j'ai besoin de » et « je me demande ». Les deux sont des
#: demandes parfaitement ordinaires :
#:
#:     « j'ai besoin de mes impots de 2024 »   → une recherche de fichier
#:     « je me demande quelle heure il est »   → une question
#:
#: Les faire taire aurait casse ce qui marchait, pour corriger un defaut qui
#: n'aurait meme pas ete celui-la. Ne restent que les tournures ou le sujet
#: de l'action est « je » ET ou l'action reste a faire : aucune d'elles ne
#: peut demander quoi que ce soit a quelqu'un d'autre.
_DELIBERE = re.compile(
    r"\b(?:il )?faudrait que j(?:e\b|')"
    r"|\bfaut que j(?:e\b|')"
    r"|\bva falloir que j(?:e\b|')"
    r"|\bje (?:devrais|dois|vais|pourrais|ferais mieux de)\b"
    r"|\bje me disais\b|\bje disais\b"
    r"|\bnote a moi meme\b"
)


# ══════════════════════════════════════════════════════════════════════════
#  LA PHRASE QUI NE DIT RIEN
# ══════════════════════════════════════════════════════════════════════════

#: Les mots qui ne peuvent etre ni une demande, ni un ordre, ni une reponse.
#:
#: C'est la meme famille que le silence transcrit en « … » : une phrase sans
#: contenu propositionnel ne peut pas etre exaucee, et le modele en fera
#: quand meme quelque chose.
_REMPLISSAGE: frozenset[str] = frozenset(
    "hmm hum mmh euh heu ben bah beh mouais bon voyons enfin bref".split()
)

#: Ce qui peut ACCOMPAGNER un remplissage sans jamais suffire a lui seul.
#:
#: ⚠️ « ok », « ouais », « vas y », « voila » N'ONT RIEN A FAIRE ICI.
#:
#: Ce sont les mots de `session._ACCORD` : quand Nova vient de proposer
#: « je te l'ouvre ? », ils valent OUI. Les traiter comme du remplissage
#: rendrait la proposition inacceptable — un « ok » repondrait au vide.
#: « c'est bon » est un conge, « attends » une interruption : ni l'un ni
#: l'autre ne se rangent ici non plus.
_LIANTS: frozenset[str] = frozenset("alors donc puis et mais du coup en fait".split())


def hesitation_seule(texte: str) -> bool:
    """La phrase n'est faite que d'hesitation : rien a exaucer.

    Il faut AU MOINS UN vrai mot de remplissage. « alors » seul n'en est pas
    un — apres une reponse de Nova, il veut souvent dire « et ensuite ? ».
    """
    mots = _plat(texte).split()
    if not mots:
        return False
    if not all(mot in _REMPLISSAGE or mot in _LIANTS for mot in mots):
        return False
    return any(mot in _REMPLISSAGE for mot in mots)


def pense_tout_haut(texte: str) -> bool:
    """Cette phrase se parle a elle-meme plutot qu'a Nova.

    ⚠️ LE DEFAUT EST « NON ». LE SILENCE SE MERITE.

    Il faut un signal de deliberation — ou une phrase vide de contenu — ET
    aucune marque d'adresse. Sans les deux, Nova repond, comme avant.
    """
    plat = _plat(texte)
    if not plat:
        return False
    if _ADRESSE.search(plat):
        return False
    return bool(_DELIBERE.search(plat)) or hesitation_seule(plat)


def raison(texte: str) -> str:
    """Pourquoi Nova s'est tue, ou non. Pour le journal.

    Un silence sans explication est indistinguable d'une panne : on
    chercherait pourquoi Nova « ne repond plus » alors qu'elle se retient.
    Celle-ci se lit dans la console.
    """
    plat = _plat(texte)
    if not plat:
        return "phrase vide"
    if _ADRESSE.search(plat):
        return "s'adresse a Nova"
    if _DELIBERE.search(plat):
        return "delibere sur sa propre action"
    if hesitation_seule(plat):
        return "hesitation sans contenu"
    return "demande ordinaire"
