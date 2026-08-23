"""D'une phrase parlee a une interrogation : les mots, le type, la date.

    « retrouve-moi mon releve de compte de 2024 »
        mots   : releve, compte
        annee  : 2024
        genres : (aucun — tous les types)

    « ma facture EDF en PDF de l'annee derniere »
        mots   : facture, edf
        annee  : 2025 (si nous sommes en 2026)
        genres : pdf

⚠️ TOUT LE TRAVAIL EST ICI, ET C'EST VOULU.

Spotlight sait chercher ; il ne sait pas ce qu'est « un releve de compte ».
Entre la phrase et l'index, il manque trois traductions, et chacune a ete
mise en defaut par une phrase reelle avant d'etre ecrite :

1. LES SYNONYMES. Personne ne nomme ses fichiers comme il en parle. On dit
   « mon releve de compte », le fichier s'appelle « extrait_bancaire.pdf ».
   Chercher le mot prononce ne trouve rien, et l'echec ressemble a une
   absence de fichier alors que c'est une absence de vocabulaire.

2. LA DATE. « de 2024 » est un filtre, pas un mot a chercher — mais il peut
   AUSSI etre dans le nom (« releve-2024-03.pdf »). Les deux, donc : filtre
   souple, et bonus au nom qui le porte.

3. LES MOTS VIDES. « peux-tu me retrouver dans mes fichiers » ne contient
   aucun mot utile. Les garder ferait ressembler la question a tout et a
   rien — la lecon exacte du catalogue d'images, ou une phrase polie
   cherchait moins bien qu'une phrase seche.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from nova.logging_setup import get_logger

log = get_logger(__name__)


def sans_accents(texte: str) -> str:
    """« relevé » → « releve ». La longueur est preservee."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )


def _normaliser(texte: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", sans_accents(texte).lower()).strip()


#: Ce qui ne dit rien sur le fichier cherche.
#:
#: On repart de la liste du catalogue d'images — elle a deja ete corrigee par
#: l'usage (« nova », « stp », « derniere », « transferee ») et la dupliquer
#: garantirait qu'une des deux prenne du retard. On y ajoute ce qui est propre
#: aux fichiers : les mots qui nomment le CONTENANT plutot que le contenu.
_PROPRES: frozenset[str] = frozenset(
    """
    fichier fichiers document documents dossier dossiers papier papiers
    truc trucs chose choses machin ordinateur pc mac disque
    quelque part fond rappelle rappeler souviens souvenir imagine imaginons
    date datant datent remonte annee annees an ans mois semaine semaines
    vers environ autour genre exemple part sais connais
    """.split()
)


def vides() -> frozenset[str]:
    """Les mots a ignorer. Ceux du catalogue, plus ceux des fichiers."""
    from nova.vision.catalogue import VIDES

    return VIDES | _PROPRES


#: Ce qu'on dit, et ce que les fichiers s'appellent vraiment.
#:
#: ⚠️ C'EST LA PIECE QUI FAIT MARCHER LA FONCTIONNALITE, ET ELLE EST BETE.
#:
#: Pas de modele, pas de vecteurs : une table. Un modele de langue saurait
#: elargir « releve de compte » — pour une seconde de calcul a chaque
#: recherche, sur une machine ou cette seconde se voit. Une table repond en
#: zero, se lit, et se corrige quand elle a tort.
#:
#: Chaque ligne est un groupe de mots equivalents : citer n'importe lequel
#: fait chercher tous les autres.
FAMILLES: tuple[tuple[str, ...], ...] = (
    # Banque et argent
    ("releve", "extrait", "bancaire", "banque", "compte", "rib", "iban",
     "solde", "operations"),
    ("revenu", "revenus", "salaire", "paie", "paye", "bulletin", "fiche",
     "remuneration", "traitement"),
    ("impot", "impots", "fiscal", "fiscale", "avis", "imposition", "taxe",
     "declaration"),
    ("facture", "factures", "recu", "ticket", "quittance", "note", "devis"),
    # Papiers
    ("contrat", "contrats", "engagement", "bail", "convention", "avenant"),
    ("attestation", "attestations", "certificat", "justificatif", "preuve"),
    ("assurance", "assurances", "mutuelle", "garantie", "sinistre"),
    ("identite", "passeport", "carte", "permis", "cni"),
    ("cv", "curriculum", "candidature", "lettre", "motivation"),
    ("ordonnance", "medical", "medicale", "sante", "analyse", "resultat"),
    # Etudes et travail
    ("releve_notes", "notes", "bulletin_scolaire", "diplome", "attestation_scolaire"),
    ("rapport", "rapports", "compte_rendu", "memoire", "these", "expose"),
    ("presentation", "diapo", "diapos", "slides", "soutenance"),
)


#: Les types de fichiers qu'on sait nommer a l'oral.
GENRES: dict[str, tuple[str, ...]] = {
    "pdf": (".pdf",),
    "image": (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tiff", ".bmp"),
    "tableur": (".xlsx", ".xls", ".csv", ".numbers", ".ods"),
    "texte": (".doc", ".docx", ".pages", ".txt", ".md", ".rtf", ".odt"),
    "presentation": (".key", ".pptx", ".ppt", ".odp"),
    "video": (".mp4", ".mov", ".avi", ".mkv", ".m4v"),
    "son": (".mp3", ".wav", ".m4a", ".aac", ".flac"),
}

#: Comment on demande chaque type, a l'oral.
#:
#: ⚠️ DES MOTS, PAS DES EXPRESSIONS REGULIERES.
#:
#: Premiere version : une liste de motifs, et `lire` en re-extrayait les mots
#: pour savoir lesquels ne pas chercher. Elle lisait donc `\bpdf\b` et en
#: tirait « bpdf » — le `\b` colle au mot. « pdf » restait dans les mots
#: cherches, et aucun fichier ne s'appelle « pdf ».
#:
#: Un module qui relit sa propre syntaxe pour deviner ce qu'il a voulu dire
#: se trompe toujours. La liste est donc en clair, et le motif s'en deduit.
_DIT_LE_GENRE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pdf", ("pdf",)),
    ("image", ("photo", "photos", "image", "images", "capture", "captures",
               "screenshot", "screenshots", "cliche", "cliches")),
    ("tableur", ("tableur", "excel", "tableau", "numbers", "csv")),
    ("texte", ("word", "texte", "pages", "doc", "docx")),
    ("presentation", ("presentation", "diapo", "diapos", "slide", "slides",
                      "powerpoint", "keynote")),
    ("video", ("video", "videos", "film", "films", "clip", "clips")),
    ("son", ("audio", "son", "sons", "musique", "musiques",
             "enregistrement", "enregistrements")),
)

#: Tous les mots qui nomment un type. Ils filtrent, ils ne se cherchent pas.
_MOTS_DE_GENRE: frozenset[str] = frozenset(
    mot for _, mots_du_genre in _DIT_LE_GENRE for mot in mots_du_genre
)

#: Les nombres qu'on prononce plutot que d'ecrire.
_NOMBRES: dict[str, int] = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "quinze": 15, "vingt": 20,
}

#: « deux mille vingt-quatre » — Whisper ecrit parfois les annees en lettres.
#:
#: ⚠️ RELEVE DANS LA DEMANDE MEME QUI A LANCE CE MODULE.
#:
#: La phrase etait « qui date de deux mille vingt-quatre ». Un motif qui
#: n'attrape que « 2024 » aurait rate l'exemple fondateur — et personne
#: n'aurait su pourquoi, puisque la recherche aurait quand meme rendu des
#: resultats, simplement sans filtre de date.
_ANNEE_EN_LETTRES = re.compile(
    r"\bdeux mille?"
    r"(?:\s+(?P<dizaine>dix|vingt|trente|quarante)"
    r"(?:[\s-]+(?P<unite>et un|un|deux|trois|quatre|cinq|six|sept|huit|neuf))?)?",
)
_DIZAINES: dict[str, int] = {"dix": 10, "vingt": 20, "trente": 30, "quarante": 40}


@dataclass(frozen=True)
class Recherche:
    """Ce qu'on cherche, sous une forme qu'un moteur peut executer."""

    #: Les mots prononces qui portent du sens, deja depouilles.
    mots: tuple[str, ...] = ()
    #: Les mots a chercher REELLEMENT — les precedents, plus leurs synonymes.
    elargis: tuple[str, ...] = ()
    #: L'annee demandee, si elle l'a ete.
    annee: int | None = None
    #: Les types demandes. Vide = tous.
    genres: tuple[str, ...] = ()
    #: La phrase d'origine, pour le journal et les messages.
    phrase: str = ""
    extensions: tuple[str, ...] = field(default=())

    def __bool__(self) -> bool:
        """Une recherche sans mot ni annee ne cherche rien."""
        return bool(self.mots or self.annee)


def _annee(plat: str, aujourdhui: datetime) -> int | None:
    """L'annee visee, ecrite en chiffres, en lettres, ou relative."""
    if ecrite := re.search(r"\b(19\d{2}|20\d{2})\b", plat):
        return int(ecrite.group(1))

    if lettres := _ANNEE_EN_LETTRES.search(plat):
        annee = 2000
        if dizaine := lettres.group("dizaine"):
            annee += _DIZAINES[dizaine]
        if unite := lettres.group("unite"):
            annee += _NOMBRES[unite.replace("et ", "").strip()]
        return annee

    # « il y a deux ans », « il y a 3 ans »
    if recul := re.search(r"\bil y a\s+(\w+)\s+an", plat):
        combien = recul.group(1)
        nombre = _NOMBRES.get(combien) or (int(combien) if combien.isdigit() else None)
        if nombre:
            return aujourdhui.year - nombre

    # ⚠️ `_normaliser` A DEJA REMPLACE L'APOSTROPHE PAR UNE ESPACE.
    #
    # Le motif cherchait « l'annee derniere » sur un texte devenu « l annee
    # derniere ». Il ne pouvait pas correspondre — et l'annee n'etait alors
    # pas filtree du tout, ce qui rendait quand meme des resultats.
    if re.search(r"\b(?:annee derniere|an dernier|annee passee)\b", plat):
        return aujourdhui.year - 1
    if re.search(r"\b(?:cette annee|annee en cours)\b", plat):
        return aujourdhui.year
    return None


def _genres(plat: str) -> tuple[str, ...]:
    presents = set(plat.split())
    # L'ordre de declaration, sans doublon : « une photo ou un pdf » garde les
    # deux, et le classement s'en occupera.
    return tuple(
        genre for genre, mots_du_genre in _DIT_LE_GENRE
        if presents.intersection(mots_du_genre)
    )


def _elargir(mots: tuple[str, ...]) -> tuple[str, ...]:
    """Les mots cherches, plus ceux qui veulent dire la meme chose.

    Un mot qui appartient a une famille amene toute sa famille. Un mot qui
    n'appartient a aucune reste seul — c'est le cas des noms propres
    (« EDF », « Kozlowski »), et ce sont justement les meilleurs mots de
    recherche : on ne les elargit surtout pas.
    """
    elargis: list[str] = list(mots)
    for mot in mots:
        for famille in FAMILLES:
            if mot in famille:
                elargis.extend(f for f in famille if "_" not in f)
    return tuple(dict.fromkeys(elargis))


def lire(texte: str, *, aujourdhui: datetime | None = None) -> Recherche:
    """Traduit une phrase en recherche. Ne leve jamais."""
    aujourdhui = aujourdhui or datetime.now()
    plat = _normaliser(texte)
    if not plat:
        return Recherche(phrase=texte or "")

    annee = _annee(plat, aujourdhui)
    genres = _genres(plat)

    ignores = vides()
    mots = tuple(
        m
        for m in plat.split()
        if len(m) > 2 and m not in ignores and not m.isdigit()
    )
    # Un mot qui ne sert qu'a nommer le TYPE ne sert pas a chercher le nom :
    # « en pdf » filtre l'extension, il ne se cherche pas dans le titre.
    mots = tuple(m for m in mots if m not in _MOTS_DE_GENRE)

    extensions = tuple(
        extension for genre in genres for extension in GENRES.get(genre, ())
    )
    recherche = Recherche(
        mots=mots,
        elargis=_elargir(mots),
        annee=annee,
        genres=genres,
        phrase=texte,
        extensions=extensions,
    )
    log.info(
        "Recherche de fichier : mots=%s annee=%s genres=%s (elargi a %d mots)",
        list(recherche.mots), recherche.annee, list(recherche.genres),
        len(recherche.elargis),
    )
    return recherche
