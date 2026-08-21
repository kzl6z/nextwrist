"""Trouver une image, la borner, la reduire, l'encoder.

CE FICHIER EST LA MOITIE DU TRAVAIL DE LA VISION, ET C'EST LA MOINS VISIBLE

Decrire une image, c'est un appel. Savoir DE QUELLE image on parle, verifier
qu'on a le droit de la lire, et la mettre dans un etat ou le modele peut la
recevoir — c'est tout le reste, et c'est la que ca casse.

⚠️ TROIS PIEGES, DONT UN DE SECURITE

1. LE CHEMIN. « decris cette image » ne dit pas laquelle. Un modele qui
   devine un chemin peut devenir le chemin vers `~/.ssh/id_rsa` : la meme
   verification que `LireFichier` s'applique, pour la meme raison, et elle
   n'est pas negociable. On resout reellement (`resolve`, qui suit les liens
   symboliques et remonte les `..`) et on verifie qu'on reste sous la racine.
   Comparer des chaines ne suffirait pas : `data/../../.ssh` commence bien
   par `data/`.

2. LA TAILLE. Une photo d'iPhone fait 12 megapixels. Encodee en base64 dans
   un prompt, elle pese une quinzaine de megaoctets — que le moteur va
   avaler, puis reduire lui-meme a 1024 pixels avant de regarder quoi que ce
   soit. On aura donc paye l'envoi, l'attente et le depassement de delai pour
   arriver a l'image qu'on aurait pu envoyer directement.

3. LE FORMAT. Un HEIC d'iPhone n'est pas un JPEG. Sans Pillow, on ne sait ni
   le lire ni le convertir — et il faut le DIRE, pas rendre une image vide.

CE MODULE NE PARLE A AUCUN MODELE

Il rend des octets et un chemin. C'est ce qui le rend testable sans Ollama,
sans reseau et sans machine — la meme regle que le planificateur.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from nova.logging_setup import get_logger

log = get_logger(__name__)


class ImageIntrouvable(FileNotFoundError):
    """Aucune image a analyser, et on prefere le dire que d'en inventer une."""


class ImageIllisible(ValueError):
    """L'image existe mais on ne sait pas la preparer. Le message dit pourquoi."""


#: Extensions qu'on accepte de regarder.
#:
#: `.heic` y figure alors qu'on ne sait pas toujours le lire : c'est le format
#: par defaut d'un iPhone, donc celui que l'utilisateur aura sous la main. Le
#: refuser comme « pas une image » serait faux et incomprehensible ; mieux
#: vaut l'accepter puis expliquer ce qui manque pour le convertir.
EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif", ".tif", ".tiff"}
)

#: Formats qu'un moteur multimodal recoit sans conversion. Les autres passent
#: obligatoirement par Pillow.
DIRECTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"})

#: Au-dela, on refuse d'envoyer sans avoir reduit.
#:
#: ⚠️ CE PLAFOND N'EST PAS UNE PRUDENCE, C'EST UN DIAGNOSTIC.
#:
#: Sans lui, une photo de 8 Mo part telle quelle, le moteur met deux minutes,
#: le delai de lecture expire, et Nova rend « le moteur n'a pas repondu a
#: temps (modele trop lourd pour la machine ?) » — un message qui accuse le
#: modele alors que c'est l'image qui etait trop grosse. On prefere echouer
#: tout de suite en nommant la vraie cause et le remede.
OCTETS_MAX_SANS_REDUCTION = 2_000_000


@dataclass(frozen=True)
class ImagePrete:
    """Une image bornee, reduite si possible, et encodee pour un moteur."""

    source: Path
    #: Le contenu encode en base64, sans prefixe.
    donnees: str
    #: Le type MIME de `donnees`, apres conversion eventuelle.
    mime: str
    #: Taille reellement envoyee, en octets. Pour le journal et la mesure.
    octets: int
    #: Vrai si Pillow a redimensionne. Faux si l'image est partie telle quelle.
    reduite: bool

    @property
    def uri(self) -> str:
        """La forme attendue par un point d'entree compatible OpenAI."""
        return f"data:{self.mime};base64,{self.donnees}"


def est_une_image(chemin: Path) -> bool:
    return chemin.suffix.lower() in EXTENSIONS


def resoudre(chemin: str, racine: Path) -> Path:
    """Le chemin reel d'une image, DANS le dossier de travail et nulle part ailleurs.

    ⚠️ LA SEULE LIGNE QUI COMPTE VRAIMENT ICI EST LA VERIFICATION.

    Ce chemin peut venir d'un modele, ou d'un document que Nova vient de lire.
    Un chemin non borne permet a n'importe quelle demande d'atteindre
    n'importe quel fichier de la machine — et la vision est un excellent
    moyen d'exfiltrer un fichier, puisqu'elle en RACONTE le contenu.
    """
    racine = Path(racine).resolve()
    demande = Path(chemin).expanduser()
    cible = (demande if demande.is_absolute() else racine / demande).resolve()

    if not cible.is_relative_to(racine):
        raise ImageIllisible(
            f"« {chemin} » sort du dossier de travail ({racine}). "
            "Nova ne regarde que ce que tu lui as confie."
        )
    if not cible.is_file():
        raise ImageIntrouvable(f"« {chemin} » n'existe pas dans le dossier de travail.")
    if not est_une_image(cible):
        raise ImageIllisible(
            f"« {chemin} » n'est pas une image "
            f"({', '.join(sorted(EXTENSIONS))} attendus)."
        )
    return cible


def la_plus_recente(racine: Path) -> Path:
    """L'image la plus recemment modifiee du dossier de travail.

    ⚠️ UNE HEURISTIQUE ASSUMEE, ET BORNEE.

    « decris cette image » ne nomme rien. Dans la vie reelle, « cette image »
    est celle qu'on vient de deposer — c'est la lecture la plus naturelle, et
    la seule qui evite de demander « laquelle ? » a quelqu'un qui vient de
    repondre a cette question en glissant un fichier.

    Elle reste bornee au dossier de travail, et l'agent NOMME toujours
    l'image retenue dans sa reponse. Une heuristique qui se declare est
    corrigeable ; une heuristique silencieuse produit une description du
    mauvais fichier sans que personne comprenne pourquoi.
    """
    racine = Path(racine).resolve()
    if not racine.is_dir():
        raise ImageIntrouvable(f"Le dossier de travail ({racine}) n'existe pas.")

    images = [c for c in racine.rglob("*") if c.is_file() and est_une_image(c)]
    if not images:
        raise ImageIntrouvable(
            f"Aucune image dans le dossier de travail ({racine}). "
            "Depose-la la, ou donne son chemin."
        )
    return max(images, key=lambda c: c.stat().st_mtime)


def _reduire(cible: Path, cote_max: int) -> tuple[bytes, str] | None:
    """Reduit avec Pillow, ou rend `None` si Pillow n'est pas installe."""
    try:
        from PIL import Image
    except ImportError:
        return None

    import io

    with Image.open(cible) as image:
        # `RGB` avant tout : un PNG a canal alpha ou un HEIC en YCbCr ne
        # s'enregistre pas en JPEG tel quel, et l'erreur qui en sort parle de
        # modes de couleur — pas du fichier qu'on essayait de lire.
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if max(image.size) > cote_max:
            image.thumbnail((cote_max, cote_max), Image.LANCZOS)
        tampon = io.BytesIO()
        image.save(tampon, format="JPEG", quality=85, optimize=True)
    return tampon.getvalue(), "image/jpeg"


def preparer(cible: Path, *, cote_max: int = 1024) -> ImagePrete:
    """Met une image dans l'etat ou un moteur multimodal peut la recevoir.

    Avec Pillow : reduite au cote demande et convertie en JPEG. Sans Pillow :
    envoyee telle quelle si le format est direct et le poids raisonnable, et
    REFUSEE sinon, avec le remede.
    """
    reduit = _reduire(cible, cote_max)
    if reduit is not None:
        octets, mime = reduit
        log.info(
            "Image « %s » reduite : %d ko -> %d ko",
            cible.name, cible.stat().st_size // 1000, len(octets) // 1000,
        )
        return ImagePrete(
            source=cible,
            donnees=base64.b64encode(octets).decode("ascii"),
            mime=mime,
            octets=len(octets),
            reduite=True,
        )

    # ── Sans Pillow ────────────────────────────────────────────────────────
    extension = cible.suffix.lower()
    if extension not in DIRECTS:
        raise ImageIllisible(
            f"« {cible.name} » est au format {extension} : sa conversion demande Pillow.\n"
            'Installe-le :  uv pip install -e ".[vision]"'
        )
    poids = cible.stat().st_size
    if poids > OCTETS_MAX_SANS_REDUCTION:
        raise ImageIllisible(
            f"« {cible.name} » pese {poids // 1_000_000} Mo. Sans Pillow, Nova ne "
            "sait pas la reduire, et l'envoyer telle quelle ferait expirer le "
            "delai du moteur.\n"
            'Installe Pillow :  uv pip install -e ".[vision]"'
        )
    octets = cible.read_bytes()
    mime = "image/jpeg" if extension in (".jpg", ".jpeg") else f"image/{extension[1:]}"
    log.info(
        "Image « %s » envoyee telle quelle (%d ko) : Pillow absent.",
        cible.name, poids // 1000,
    )
    return ImagePrete(
        source=cible,
        donnees=base64.b64encode(octets).decode("ascii"),
        mime=mime,
        octets=len(octets),
        reduite=False,
    )
