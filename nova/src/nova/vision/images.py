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
from collections.abc import Iterable, Iterator
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


#: Profondeur de descente dans les dossiers surveilles.
#:
#: ⚠️ BORNEE, ET PAS PAR PRUDENCE ABSTRAITE.
#:
#: `rglob("*")` sur un Bureau ou un dossier Telechargements bien rempli peut
#: parcourir des dizaines de milliers d'entrees — et ce parcours arrive dans
#: la question de l'utilisateur, pas dans un fil de fond. Deux niveaux
#: couvrent « Bureau/photos/piece.jpg » et s'arretent avant une sauvegarde
#: complete oubliee la.
PROFONDEUR_MAX = 2


def est_une_image(chemin: Path) -> bool:
    return chemin.suffix.lower() in EXTENSIONS


def racines(ou: Path | Iterable[Path]) -> tuple[Path, ...]:
    """Normalise « une racine ou plusieurs » en un tuple resolu.

    Publique parce que `moteur.py` en a besoin : un nom prive utilise depuis
    un autre module est une contradiction, et la premiere chose qu'on casse
    en refactorant.
    """
    if isinstance(ou, (str, Path)):
        ou = [Path(ou)]
    resolues: list[Path] = []
    for racine in ou:
        chemin = Path(racine).expanduser()
        try:
            resolues.append(chemin.resolve())
        except OSError:  # un chemin configure qui n'existe pas ne doit rien casser
            continue
    return tuple(resolues)


def dossiers_surveilles() -> tuple[Path, ...]:
    """Les dossiers ou Nova a le droit de chercher une image.

    Lus dans les reglages plutot que codes ici : elargir ce que Nova peut
    lire doit etre une DECISION visible dans `.env`, pas une constante enfouie
    dans un module.
    """
    from nova.settings import get_settings

    reglages = get_settings()
    declares = [d.strip() for d in reglages.vision_dossiers.split(",") if d.strip()]
    racine_projet = reglages.root
    return racines(
        [d if Path(d).expanduser().is_absolute() else racine_projet / d for d in declares]
    )


def _parcourir(racine: Path, profondeur: int = PROFONDEUR_MAX) -> Iterator[Path]:
    """Les images d'un dossier, sans descendre indefiniment ni suivre le cache.

    Les dossiers caches sont sautes : `~/Library`, `.git`, `node_modules` et
    les caches d'applications contiennent des milliers d'images qui ne sont
    jamais « la derniere image que j'ai apportee ».
    """
    if profondeur < 0 or not racine.is_dir():
        return
    try:
        entrees = list(racine.iterdir())
    except OSError:
        return
    for entree in entrees:
        if entree.name.startswith("."):
            continue
        try:
            if entree.is_file():
                if est_une_image(entree):
                    yield entree
            elif entree.is_dir():
                yield from _parcourir(entree, profondeur - 1)
        except OSError:
            continue


def resoudre(chemin: str, racine: Path | Iterable[Path]) -> Path:
    """Le chemin reel d'une image, DANS le dossier de travail et nulle part ailleurs.

    ⚠️ LA SEULE LIGNE QUI COMPTE VRAIMENT ICI EST LA VERIFICATION.

    Ce chemin peut venir d'un modele, ou d'un document que Nova vient de lire.
    Un chemin non borne permet a n'importe quelle demande d'atteindre
    n'importe quel fichier de la machine — et la vision est un excellent
    moyen d'exfiltrer un fichier, puisqu'elle en RACONTE le contenu.
    """
    permis = racines(racine)
    if not permis:
        raise ImageIllisible("Aucun dossier de travail configure pour la vision.")

    demande = Path(chemin).expanduser()
    # ⚠️ UN CHEMIN RELATIF EST ESSAYE DANS CHAQUE RACINE, PAS SEULEMENT LA
    #    PREMIERE — mais chaque essai reste borne a SA racine.
    #
    # Elargir la recherche n'elargit pas le droit de lire : un candidat qui
    # sortirait de la racine ou on l'essaie est ecarte comme avant.
    candidats = (
        [demande] if demande.is_absolute() else [racine / demande for racine in permis]
    )

    dedans: list[Path] = []
    for candidat in candidats:
        try:
            resolu = candidat.resolve()
        except OSError:
            continue
        if any(resolu.is_relative_to(racine) for racine in permis):
            dedans.append(resolu)

    if not dedans:
        ou = ", ".join(str(r) for r in permis)
        raise ImageIllisible(
            f"« {chemin} » sort des dossiers que Nova peut lire ({ou}). "
            "Nova ne regarde que ce que tu lui as confie."
        )

    cible = next((c for c in dedans if c.is_file()), dedans[0])
    if not cible.is_file():
        raise ImageIntrouvable(f"« {chemin} » n'existe pas dans le dossier de travail.")
    if not est_une_image(cible):
        raise ImageIllisible(
            f"« {chemin} » n'est pas une image "
            f"({', '.join(sorted(EXTENSIONS))} attendus)."
        )
    return cible


def la_plus_recente(racine: Path | Iterable[Path]) -> Path:
    """L'image la plus recemment deposee, parmi les dossiers surveilles.

    ⚠️ UNE HEURISTIQUE ASSUMEE, ET BORNEE.

    « analyse l'image » ne nomme rien. Dans la vie reelle, « l'image » est
    celle qu'on vient de recevoir du telephone, d'un mail ou de Chrome —
    c'est la lecture la plus naturelle, et la seule qui evite de demander
    « laquelle ? » a quelqu'un qui vient de repondre a cette question en
    deposant un fichier.

    Elle reste bornee aux dossiers declares, et l'appelant NOMME toujours
    l'image retenue. Une heuristique qui se declare est corrigeable ; une
    heuristique silencieuse produit une description du mauvais fichier sans
    que personne comprenne pourquoi.

    ⚠️ `st_mtime` ET NON `st_ctime`.

    Un fichier telecharge, recu par AirDrop ou copie depuis le telephone
    garde souvent la date de MODIFICATION de l'original — parfois vieille de
    plusieurs mois. `st_ctime` (date d'arrivee sur ce disque) serait le bon
    critere pour « ce que je viens d'apporter »... mais il change aussi a
    chaque renommage, et sur macOS il recule apres une restauration.
    On garde `st_mtime`, on ANNONCE l'age, et l'utilisateur corrige d'un mot.
    """
    permis = racines(racine)
    existants = [r for r in permis if r.is_dir()]
    if not existants:
        ou = ", ".join(str(r) for r in permis) or "aucun"
        raise ImageIntrouvable(f"Aucun dossier surveille n'existe ({ou}).")

    images: list[Path] = []
    for dossier in existants:
        images.extend(_parcourir(dossier))
    if not images:
        ou = ", ".join(str(r) for r in existants)
        raise ImageIntrouvable(
            f"Aucune image dans les dossiers surveilles ({ou}). "
            "Depose-la dans l'un d'eux, ou donne son chemin."
        )

    def date(chemin: Path) -> float:
        try:
            return chemin.stat().st_mtime
        except OSError:
            return 0.0

    return max(images, key=date)


def age_en_heures(chemin: Path) -> float:
    """Depuis combien de temps ce fichier n'a pas bouge. `-1` si illisible."""
    import time

    try:
        return max((time.time() - chemin.stat().st_mtime) / 3600, 0.0)
    except OSError:
        return -1.0


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
