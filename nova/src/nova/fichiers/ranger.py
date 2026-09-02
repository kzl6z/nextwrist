"""Ranger dans le dossier du projet ce que Nova vient d'annoncer.

    « retrouve-moi les photos ou je tiens une casquette blanche »
    « J'ai trouve 3 photos. Laquelle veux-tu ? »
    « mets-les dans le dossier du projet »
    « Je deplace les 3 photos dans le dossier centrale nucleaire ? »
    « oui »

⚠️ ON NE DEPLACE QUE CE QUE NOVA VIENT D'ANNONCER.

C'est la borne la plus importante de ce module, et elle ne coute rien : la
liste retenue par `focus` est deja celle qui donne un sens a « ouvre la
deuxieme » et a « ouvre-les toutes ». Un outil qui accepterait un chemin
libre pourrait ranger n'importe quoi ; celui-ci ne peut toucher que des
fichiers dont Nova vient de dire le nombre a voix haute.

⚠️ ET ON RETIENT D'OU CHAQUE FICHIER VENAIT.

Sur le papier, deplacer n'est ni supprimer ni ecraser : le fichier existe
toujours, entier, ailleurs. En pratique on ne retrouve pas ce qu'on ne sait
pas nommer — trois photos rangees au mauvais endroit sont perdues, et la
difference avec « detruites » n'interesse que les informaticiens.

L'origine enregistree rend « remets-les ou ils etaient » possible. C'est ce
qui fait passer l'action de « ne se defait pas » a « se defait mal », donc de
IRREVERSIBLE a CONSEQUENT — le niveau ou une confirmation suffit.

⚠️ « DANS UN DOSSIER » ET « DANS LE DOSSIER » NE DEMANDENT PAS LA MEME CHOSE.

    « range tout dans un dossier Photos »   → CREER un dossier
    « range-les dans le dossier »           → RANGER dans celui du projet

L'article indefini annonce quelque chose qui n'existe pas encore, le defini
renvoie a ce dont on parle. C'est une propriete de la phrase, lisible sans
modele, et c'est ce qui separe ce module de `fichiers/creer.py`.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nova.logging_setup import get_logger

log = get_logger(__name__)


def _plat(texte: str) -> str:
    sans = "".join(
        c for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", sans.lower())).strip()


# ══════════════════════════════════════════════════════════════════════════
#  RECONNAITRE
# ══════════════════════════════════════════════════════════════════════════

_VERBE = re.compile(
    r"\b(?:mets?|met|mettre|range|ranger|deplace|deplacer|classe|classer|"
    r"ajoute|ajouter|glisse|glisser|copie)\b"
)

#: ⚠️ L'ARTICLE DEFINI EST LE SIGNAL, ET IL EST OBLIGATOIRE.
#:
#: « dans UN dossier Photos » cree ; « dans LE dossier » range. Accepter
#: l'indefini ici volerait sa phrase a `fichiers/creer.py`, et Nova
#: repondrait qu'elle ne sait pas ou ranger alors qu'on lui demandait de
#: creer.
_DEDANS = re.compile(
    r"\b(?:dans (?:le |ce |mon |notre |son )(?:dossier|projet|repertoire)"
    r"|dans le dossier du projet|dans le projet"
    r"|dedans|la dedans|avec le reste)\b"
)

#: « remets-les ou ils etaient », « annule le deplacement ».
_ANNULER = re.compile(
    r"\b(?:remets? (?:les |le |la |ca |tout )?(?:ou ils etaient|ou elles etaient|"
    r"a (?:leur|sa) place|comme avant)"
    r"|annule (?:le |ce )?(?:deplacement|rangement)"
    r"|remets? tout comme avant"
    r"|c etait une erreur)\b"
)


def demande_de_ranger(texte: str) -> bool:
    """Cette phrase demande-t-elle de ranger dans le dossier du projet ?

    Deux signaux : un verbe de rangement et une destination DEFINIE. Le verbe
    seul attrape « mets-moi de la musique » ; la destination seule attrape
    « qu'est-ce qu'il y a dans le dossier ».
    """
    plat = _plat(texte)
    if not plat:
        return False
    return bool(_VERBE.search(plat) and _DEDANS.search(plat))


def demande_d_annuler(texte: str) -> bool:
    """Cette phrase demande-t-elle de remettre les fichiers ou ils etaient ?"""
    plat = _plat(texte)
    return bool(plat and _ANNULER.search(plat))


# ══════════════════════════════════════════════════════════════════════════
#  LA TRACE
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Deplacement:
    """Un fichier, d'ou il venait et ou il est alle."""

    id: int
    venait_de: Path
    est_alle_a: Path
    projet_id: int | None = None
    fait_le: datetime | None = None


def nouvelle_salve() -> str:
    """L'identifiant d'un rangement. Un par geste, pas un par fichier.

    ⚠️ J'AI D'ABORD GROUPE PAR L'HEURE. C'ETAIT FAUX.

    `now()` rend l'heure de la TRANSACTION, et chaque fichier etait
    enregistre dans la sienne : trois photos rangees d'un coup portaient
    trois instants differents, et « remets-les ou ils etaient » n'en ramenait
    qu'une. Deux fichiers restaient dans le dossier, sans que rien ne le dise.
    """
    return str(uuid.uuid4())


def noter(projet_id: int | None, salve: str, venait_de: Path, est_alle_a: Path) -> None:
    """Enregistre un deplacement, pour pouvoir le defaire.

    Ecrit APRES chaque fichier plutot qu'une fois a la fin : si le processus
    s'arrete au milieu, ce qui a deja bouge reste retrouvable.
    """
    from nova.db import connection

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO deplacements (projet_id, salve, venait_de, est_alle_a)
            VALUES (%s, %s, %s, %s)
            """,
            (projet_id, salve, str(venait_de), str(est_alle_a)),
        )


def a_defaire(projet_id: int | None, limite: int = 50) -> list[Deplacement]:
    """Les deplacements du dernier rangement, du plus recent au plus ancien.

    ⚠️ LE DERNIER RANGEMENT, PAS TOUS LES DEPLACEMENTS DU PROJET.

    « remets-les ou ils etaient » defait le geste qu'on vient de faire. Tout
    ramener depuis le debut du projet deferait aussi les rangements d'hier,
    que personne ne demandait de defaire — et Nova aurait l'air d'avoir tout
    casse en obeissant.

    On prend donc ceux d'une meme SALVE — un identifiant tire une fois par
    geste, et porte par chacune de ses lignes.
    """
    from nova.db import connection

    with connection() as conn:
        lignes = conn.execute(
            """
            SELECT id, projet_id, venait_de, est_alle_a, fait_le
            FROM deplacements
            WHERE NOT annule
              AND (%s::BIGINT IS NULL OR projet_id = %s)
              AND salve = (
                  SELECT salve FROM deplacements
                  WHERE NOT annule AND (%s::BIGINT IS NULL OR projet_id = %s)
                  ORDER BY id DESC LIMIT 1
              )
            ORDER BY id DESC
            LIMIT %s
            """,
            (projet_id, projet_id, projet_id, projet_id, limite),
        ).fetchall()

    return [
        Deplacement(
            id=ligne["id"],
            venait_de=Path(ligne["venait_de"]),
            est_alle_a=Path(ligne["est_alle_a"]),
            projet_id=ligne["projet_id"],
            fait_le=ligne["fait_le"],
        )
        for ligne in lignes
    ]


def marquer_annules(identifiants) -> None:
    """Marque ces deplacements comme defaits. On ne supprime pas la ligne.

    Effacer la trace d'un retour en arriere empecherait de comprendre, trois
    jours plus tard, pourquoi un fichier a bouge deux fois.
    """
    ids = [int(i) for i in identifiants]
    if not ids:
        return
    from nova.db import connection

    with connection() as conn:
        conn.execute("UPDATE deplacements SET annule = true WHERE id = ANY(%s)", (ids,))
