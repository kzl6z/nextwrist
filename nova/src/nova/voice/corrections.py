"""Correction des homophones que la transcription confond.

LE PROBLEME

Le francais est plein de mots qui se prononcent exactement pareil et
s'ecrivent differemment. Whisper entend un son, doit choisir une graphie, et
se trompe. Releve en conditions reelles :

    « que sais-tu de moi ? »  ->  « que c'est-tu de moi ? »

Aucun reglage n'y peut rien : le son est REELLEMENT identique. Un modele plus
gros se trompera moins souvent, jamais jamais. La correction se fait donc
apres coup, sur le texte.

LA REGLE GENERALE, ET POURQUOI ELLE SUFFIT

Enumerer les fautes une par une ne tient pas : il y en a des centaines. Mais
elles obeissent presque toutes a une seule regle de grammaire :

    APRES UN PRONOM SUJET, IL FAUT LA FORME VERBALE DE CE PRONOM.

« je c'est » est faux non pas parce que « c'est » est un mauvais mot, mais
parce qu'apres « je » on attend un verbe conjugue a la premiere personne. La
meme regle corrige « il et », « tu à », « je peu », « il fais », « ils son ».

On organise donc les corrections par SON. Chaque groupe rassemble les graphies
qui se prononcent pareil, et donne la forme attendue pour chaque pronom. Le
reste est mecanique.

LA LIMITE QU'ON S'IMPOSE

On ne corrige QUE des formes agrammaticales — jamais une phrase qui pourrait
etre juste. « il s'est » est correct (« il s'est leve »), « je s'est » ne
l'est pas : les exclusions le disent, pronom par pronom.

C'est ce qui separe une correction d'un pari. Un correcteur qui remplace tout
ce qui sonne pareil casse plus de phrases justes qu'il n'en repare, et le fait
en silence. D'ou le nombre de tests NEGATIFS : ils comptent plus que les
autres.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Pronoms sujets. « qu'il » et « qu'elle » sont couverts sans effort :
# l'apostrophe est une frontiere de mot, donc `\bil\b` y trouve « il ».
PRONOMS = ("je", "tu", "il", "elle", "on", "ils", "elles")


@dataclass(frozen=True)
class Groupe:
    """Un son, les graphies qui le partagent, et la forme juste par pronom."""

    son: str
    #: Graphies entendues a la place du verbe. La forme correcte y figure
    #: aussi : elle sera simplement ignoree pour le pronom dont c'est la forme.
    graphies: tuple[str, ...]
    #: Forme attendue apres chaque pronom. Un pronom absent n'est pas corrige —
    #: soit parce que sa forme ne partage pas ce son (« je suis » n'est pas
    #: homophone de « est »), soit parce que le cas est trop rare pour valoir
    #: le risque.
    formes: dict[str, str]
    #: Couples (pronom, graphie) parfaitement corrects malgre l'apparence.
    exclusions: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    #: Couples (pronom, graphie) a ne corriger QUE si la suite ne correspond
    #: pas au motif donne. Sert aux cas ou la meme suite de mots est tantot
    #: fautive, tantot correcte, et ou seule la suite les separe.
    gardes: dict[tuple[str, str], str] = field(default_factory=dict)


GROUPES: tuple[Groupe, ...] = (
    Groupe(
        son="savoir /sɛ/",
        graphies=("sais", "sait", "c'est", "ces", "ses", "s'est"),
        formes={"je": "sais", "tu": "sais", "il": "sait", "elle": "sait", "on": "sait"},
        # « il s'est leve », « elle s'est tue » : pronominal, parfaitement correct.
        exclusions=frozenset({("il", "s'est"), ("elle", "s'est"), ("on", "s'est")}),
    ),
    Groupe(
        son="etre /ɛ/",
        graphies=("est", "es", "et", "ait", "aie"),
        # « je suis » ne partage pas ce son : la premiere personne est absente.
        formes={"tu": "es", "il": "est", "elle": "est", "on": "est"},
        # ── Le piege du « et » de coordination ──
        #
        # « elle et lui sont partis » est parfaitement correct. « il et parti »
        # ne l'est pas. La difference n'est pas dans la suite mais dans le
        # pronom : en francais, un pronom SUJET ne se coordonne pas. On dit
        # « lui et son frere », jamais « il et son frere ».
        #
        # Or « elle » est a la fois sujet ET forme accentuee. Elle seule peut
        # donc etre coordonnee, et elle seule a besoin d'une garde. « il » et
        # « on » n'en ont pas besoin : apres eux, « et » est toujours une faute.
        gardes={
            ("elle", "et"): r"(?!\s*,)(?!\s+(?:lui|elle|elles|eux|moi|toi|nous|vous|"
                            r"il|ils|je|tu|on|son|sa|ses|leur|leurs|mon|ma|mes|"
                            r"ton|ta|tes|le|la|les|un|une|des|du|de)\b)(?!\s+(?-i:[A-ZÉÈÀÂÎÔÛ]))",
        },
    ),
    Groupe(
        son="avoir /a/",
        graphies=("a", "as", "à"),
        formes={"tu": "as", "il": "a", "elle": "a", "on": "a"},
    ),
    Groupe(
        son="pouvoir /pø/",
        graphies=("peux", "peut", "peu"),
        formes={"je": "peux", "tu": "peux", "il": "peut", "elle": "peut", "on": "peut"},
    ),
    Groupe(
        son="vouloir /vø/",
        graphies=("veux", "veut", "veulent"),
        formes={"je": "veux", "tu": "veux", "il": "veut", "elle": "veut", "on": "veut"},
    ),
    Groupe(
        son="faire /fɛ/",
        graphies=("fais", "fait", "faits", "fai"),
        formes={"je": "fais", "tu": "fais", "il": "fait", "elle": "fait", "on": "fait"},
    ),
    Groupe(
        son="voir /vwa/",
        graphies=("vois", "voit", "voie", "voix"),
        formes={"je": "vois", "tu": "vois", "il": "voit", "elle": "voit", "on": "voit"},
    ),
    Groupe(
        son="mettre /mɛ/",
        graphies=("mets", "met", "mes", "mais", "m'est", "mai"),
        formes={"je": "mets", "tu": "mets", "il": "met", "elle": "met", "on": "met"},
    ),
    Groupe(
        son="prendre /pʁɑ̃/",
        graphies=("prends", "prend", "prent"),
        formes={"je": "prends", "tu": "prends", "il": "prend", "elle": "prend", "on": "prend"},
    ),
    Groupe(
        son="dire /di/",
        graphies=("dis", "dit", "dix"),
        formes={"je": "dis", "tu": "dis", "il": "dit", "elle": "dit", "on": "dit"},
    ),
    Groupe(
        son="aller /va/",
        graphies=("vas", "va"),
        # « je vais » ne partage pas ce son.
        formes={"tu": "vas", "il": "va", "elle": "va", "on": "va"},
    ),
    Groupe(
        son="etre pluriel /sɔ̃/",
        graphies=("sont", "son"),
        formes={"ils": "sont", "elles": "sont"},
    ),
    Groupe(
        son="avoir pluriel /ɔ̃/",
        graphies=("ont", "on"),
        formes={"ils": "ont", "elles": "ont"},
    ),
)


def _regles_apres_pronom() -> list[tuple[re.Pattern[str], str]]:
    """Deroule les groupes en regles concretes.

    C'est ici que la regle de grammaire devient du code : pour chaque pronom
    et chaque graphie qui n'est pas la sienne, une correction. Ecrire ces
    centaines de cas a la main serait intenable et faux quelque part.
    """
    regles = []
    for groupe in GROUPES:
        for pronom, correcte in groupe.formes.items():
            for graphie in groupe.graphies:
                if graphie == correcte or (pronom, graphie) in groupe.exclusions:
                    continue
                # Une regle par graphie, et non une alternative unique : c'est
                # ce qui permet a une garde de ne s'appliquer qu'a la graphie
                # qui en a besoin.
                garde = groupe.gardes.get((pronom, graphie), "")
                motif = re.compile(
                    rf"\b({pronom})(\s+){re.escape(graphie)}\b{garde}",
                    re.IGNORECASE,
                )
                regles.append((motif, rf"\1\2{correcte}"))
    return regles


# ── Inversion interrogative ───────────────────────────────────────────────
# « sais-tu », « es-tu », « as-tu »… Le verbe precede le pronom, la regle
# generale ne s'y applique donc pas. Ces formes sont assez peu nombreuses
# pour etre ecrites, et assez frequentes a l'oral pour compter.
INVERSIONS: tuple[tuple[str, str], ...] = (
    (r"\b(?:c'est|ces|ses|s'est|sait)-(?:tu|t'u)\b", "sais-tu"),
    (r"\b(?:et|ait|aie|es)-tu\b", "es-tu"),
    (r"\b(?:et|ait|aie|es)-(?:il|elle|on)\b", "est-\\g<0>"),  # remplace plus bas
    (r"\b(?:peu|peus)-tu\b", "peux-tu"),
    (r"\b(?:peu|peus)-(?:il|elle|on)\b", "peut-\\g<0>"),
    (r"\bà-t-(?:il|elle|on)\b", "a-t-\\g<0>"),
)

# ── L'ORDRE ADRESSE A NOVA ────────────────────────────────────────────────
#
# ⚠️ CELUI-CI N'EST PAS UNE FAUTE DE CONJUGAISON : C'EST UN DECOUPAGE.
#
# Les regles ci-dessus corrigent une graphie apres un pronom. Ici, Whisper
# entend la bonne suite de sons et la coupe au mauvais endroit :
#
#     dit      « parle-moi de Mars »
#     entendu  « par le mois de mars »
#     dit      « parle-moi des trous noirs »
#     entendu  « par le mois des trous noirs »
#
# /paʁ lə mwa də/ et /paʁl mwa də/ sont le meme son. Aucun modele, quelle que
# soit sa taille, ne peut trancher a l'oreille — seule la grammaire le peut.
#
# Et elle le peut sans ambiguite : « par le mois de X » n'existe pas en
# francais. On dit « au mois de mars », « en mars ». La forme entendue est
# donc TOUJOURS fausse, ce qui est exactement le critere que ce module
# s'impose — on ne corrige que ce qui ne peut pas etre juste.
#
# Le cout de l'erreur est eleve et silencieux : Nova ne repond pas a cote, elle
# repond serieusement a une question inventee. Releve en conditions reelles,
# sur « parle-moi de Mars » :
#
#     « Le mois de mars est une periode de transition pour… »
IMPERATIFS: tuple[tuple[str, str], ...] = (
    # « par le mois de » / « par le moi de » → « parle-moi de »
    #
    # ⚠️ LA BORNE DE MOT N'EST PAS DECORATIVE.
    #
    # Sans elle, le « de » de « dernier » correspond : « par le mois dernier »
    # devenait « parle-moi dernier ». La regle censee reparer un decoupage en
    # inventait un autre — et sur une phrase qui, elle, etait plausible.
    (r"\bpar\s+le\s+mo(?:is|i)\s+(des|du|de)(?![a-z\u00e0-\u00ff])", r"parle-moi \1"),
    (r"\bpar\s+le\s+mo(?:is|i)\s+(d')", r"parle-moi \1"),
    # Sans complement : « par le moi » en fin d'enonce.
    (r"\bpar\s+le\s+mo(?:is|i)\b(?!\s+(?:de|des|du|d'|dernier|prochain))", "parle-moi"),
    # Le trait d'union manquant, purement cosmetique mais gratuit.
    (r"\bparle\s+moi\b", "parle-moi"),
)

# Les deux formes ci-dessus qui referencent le pronom sont trop delicates a
# ecrire en une passe : on les traite separement, pronom par pronom.
_IMPERATIFS = tuple(
    (re.compile(motif, re.IGNORECASE), remplacement) for motif, remplacement in IMPERATIFS
)
_INVERSIONS_SIMPLES = tuple(
    (re.compile(motif, re.IGNORECASE), remplacement)
    for motif, remplacement in INVERSIONS
    if "\\g<0>" not in remplacement
)
_INVERSIONS_PRONOM = tuple(
    (re.compile(rf"\b(?:{alternatives})-({pronoms})\b", re.IGNORECASE), verbe)
    for alternatives, pronoms, verbe in (
        ("et|ait|aie|es", "il|elle|on", "est"),
        ("peu|peus", "il|elle|on", "peut"),
        ("veut|veus", "je", "veux"),
    )
)
_INVERSIONS_T = tuple(
    (re.compile(rf"\b(?:{alternatives})-t-({pronoms})\b", re.IGNORECASE), verbe)
    for alternatives, pronoms, verbe in (
        ("à|ah", "il|elle|on", "a"),
    )
)

_APRES_PRONOM = _regles_apres_pronom()


def corriger(texte: str) -> tuple[str, list[str]]:
    """Applique les corrections. Retourne le texte et ce qui a change.

    Rapporter les changements plutot que de corriger en silence : une
    correction invisible qui se trompe est indebogable.
    """
    if not texte:
        return texte, []

    corrige = texte
    changements: list[str] = []

    def appliquer(motif: re.Pattern[str], remplacement) -> None:
        nonlocal corrige
        avant = corrige
        corrige = motif.sub(remplacement, corrige)
        if corrige != avant:
            for trouve in motif.finditer(avant):
                changements.append(trouve.group(0))

    for motif, remplacement in _INVERSIONS_SIMPLES:
        appliquer(motif, remplacement)
    for motif, verbe in _INVERSIONS_PRONOM:
        appliquer(motif, rf"{verbe}-\1")
    for motif, verbe in _INVERSIONS_T:
        appliquer(motif, rf"{verbe}-t-\1")
    for motif, remplacement in _APRES_PRONOM:
        appliquer(motif, remplacement)
    # En dernier : les ordres adresses a Nova operent sur un decoupage, pas
    # sur une conjugaison, et n'ont donc rien a voir avec ce qui precede.
    for motif, remplacement in _IMPERATIFS:
        appliquer(motif, remplacement)

    return corrige, changements
