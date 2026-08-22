"""Retrouver une image par ce qu'elle MONTRE, pas par sa date.

CE QUE CE FICHIER REND POSSIBLE

    « Nova, sur mon PC j'ai une image ou il y a une casquette tenue dans une
      main. Est-ce que tu peux me la retrouver ? »

Jusqu'ici Nova savait regarder « la derniere image ». Une seule, celle du
dessus de la pile. Demander CELLE QUI MONTRE quelque chose supposait de les
avoir toutes regardees — et de s'en souvenir.

⚠️ REGARDER A LA DEMANDE ETAIT IMPOSSIBLE, ET LE CHIFFRE LE DIT.

Mesure sur la machine : 2,8 s de calcul par image, modele deja charge.
Quarante images sur un Bureau, c'est deux minutes d'attente pour une
question. Personne n'attend deux minutes.

D'ou un CATALOGUE : chaque image est regardee UNE FOIS, en tache de fond, et
sa description est gardee. La recherche ne coute alors plus rien — c'est une
comparaison de texte, sans modele.

⚠️ LA TRADUCTION EST FAITE A L'INDEXATION, PAS A LA RECHERCHE.

moondream decrit en anglais : « a hand holding a white cap ». Chercher
« casquette » la-dedans ne donne rien. Traduire la QUESTION a chaque
recherche couterait un appel au modele par question ; traduire la
DESCRIPTION une fois par image le paie une fois pour toutes.

Les deux textes sont gardes. L'anglais d'origine sert quand le modele de
langue est indisponible au moment d'indexer — mieux vaut une entree
cherchable a moitie qu'une image absente du catalogue.

⚠️ CE MODULE NE PARLE A AUCUN MODELE.

`indexer` recoit `decrire` et `traduire` en parametres. Il se teste donc sans
Ollama, sans reseau et sans machine — la meme regle que le planificateur.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Au-dela, on n'indexe plus.
#:
#: ⚠️ UNE BORNE, PARCE QUE LE COUT EST LINEAIRE ET PAYE EN SECONDES.
#:
#: Un dossier Telechargements de dix ans contient des milliers d'images. A
#: 2,8 s chacune, l'indexation complete durerait des heures et tiendrait le
#: modele de vision resident tout ce temps — donc le modele de langue dehors.
#: Les 300 plus recentes couvrent « ce que j'ai sur mon PC » au sens ou on
#: l'entend en parlant.
CATALOGUE_MAX = 300

#: Nombre d'images regardees par passage en tache de fond.
#:
#: Chaque passage charge le modele de vision, donc decharge celui de la
#: langue. Un lot groupe ce cout : dix images pour un chargement, au lieu de
#: dix chargements. Plus grand immobiliserait la machine trop longtemps
#: d'affilee.
LOT = 10

#: Mots trop courants pour designer quoi que ce soit. Les garder ferait
#: ressembler toutes les descriptions a toutes les questions.
VIDES: frozenset[str] = frozenset(
    """
    le la les un une des du de d a au aux et ou ce cet cette ces mon ma mes
    ton ta tes son sa ses il elle on nous vous ils elles est sont etre avoir
    dans sur sous avec sans pour par en y qui que quoi dont ou quel quelle
    je tu me te se lui leur y n ne pas plus tres bien tout tous toute toutes
    image images photo photos capture captures fichier fichiers
    the a an of in on at with and or is are this that it its there

    retrouve retrouver retrouves cherche chercher cherches trouve trouver
    ouvre ouvrir ouvres montre montrer montres peux peut pouvez pourrais
    pourrait aimerais voudrais veux veut faire acces stp merci

    nova plait plais svp bonjour salut coucou dis dit moi toi soi

    derniere dernier dernieres derniers recente recent nouvelle nouveau
    transferee transfere transferees transferes envoyee envoye recue recu
    telechargee telecharge mise mis ajoutee ajoute
    """.split()
)
#: ⚠️ LES MOTS DE PROVENANCE NE DECRIVENT PAS UN CONTENU.
#:
#: « la derniere image que j'ai transferee sur mon PC » dit QUAND et COMMENT
#: le fichier est arrive, jamais ce qu'on y voit. Les garder faisait deux
#: degats a la fois : ils polluaient le score d'une vraie recherche, et — pire
#: — ils faisaient passer « ouvre la derniere image » pour une recherche par
#: contenu, qui ne trouvait rien et refusait d'ouvrir quoi que ce soit.
#:
#: Aucun modele de vision n'ecrira jamais « transferee » dans une description.
#: ⚠️ « NOVA » ET « S'IL TE PLAIT » COMPTAIENT COMME DES MOTS CHERCHES.
#:
#: Le score est une PROPORTION. Releve sur la machine, transcription reelle :
#:
#:     « ou je train casquette sur mon PC, s'il te plait »
#:     mots cherches : train, casquette, plait  →  1/3 = 0,33
#:
#: Seuil a 0,34. La bonne image echouait a un centieme, a cause d'une formule
#: de politesse. Et le mot de reveil « Nova » reste souvent dans la
#: transcription : il apparaissait donc dans presque toutes les recherches,
#: en faisant baisser toutes.
#:
#: Sans « plait », la meme phrase donne 1/2 = 0,50. Un mot parasite venu
#: d'une mauvaise transcription — « train » — reste, et c'est normal : on ne
#: peut pas le deviner. La politesse, si.


@dataclass(frozen=True)
class Entree:
    """Ce que Nova sait d'une image, sans avoir a la regarder de nouveau."""

    chemin: str
    nom: str
    #: Date de modification au moment de l'indexation. Sert a detecter qu'un
    #: fichier a change et doit etre regarde de nouveau.
    mtime: float
    taille: int
    #: La description en francais. C'est elle qu'on cherche.
    description: str
    #: Ce que le modele de vision a reellement dit, avant traduction.
    #: Garde parce qu'une traduction est une interpretation : le jour ou une
    #: recherche donne un resultat surprenant, c'est ici qu'on regarde.
    origine: str = ""
    indexee_le: float = 0.0


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents, sans ponctuation. Comme partout ailleurs."""
    plat = "".join(
        c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]+", " ", plat.lower())


def mots(texte: str) -> list[str]:
    """Les mots porteurs de sens d'un texte."""
    return [m for m in _normaliser(texte).split() if len(m) > 2 and m not in VIDES]


class Catalogue:
    """Les descriptions deja obtenues, sur le disque.

    ⚠️ UN FICHIER JSON, PAS UNE TABLE.

    La base sert aux documents et a la memoire, et elle peut etre eteinte —
    c'est arrive plusieurs fois pendant ce projet, avec trente secondes
    d'attente a la clef. Une capacite facultative ne doit pas dependre d'une
    autre capacite facultative. Trois cents descriptions tiennent dans
    quelques dizaines de kilo-octets ; le jour ou il en faudra cent mille,
    cette classe changera d'implementation sans que personne d'autre bouge.
    """

    def __init__(self, fichier: Path) -> None:
        self.fichier = Path(fichier)
        self._entrees: dict[str, Entree] = {}
        self.charger()

    # -- persistance -------------------------------------------------------
    def charger(self) -> None:
        """Relit le catalogue. Un fichier illisible est ignore, pas fatal."""
        try:
            brut = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._entrees = {}
            return
        self._entrees = {
            e["chemin"]: Entree(**e) for e in brut.get("images", []) if "chemin" in e
        }
        log.info("Catalogue d'images : %d description(s) connue(s).", len(self._entrees))

    def enregistrer(self) -> None:
        """Ecrit le catalogue. Ne leve jamais : perdre l'index n'est pas grave.

        Il se reconstruit tout seul au passage suivant. Faire tomber une
        indexation de fond parce qu'un disque est plein serait disproportionne.
        """
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            # Ecriture atomique : une coupure au milieu laisserait un JSON
            # tronque, que `charger` jetterait entierement — on perdrait tout
            # le travail d'indexation, pas seulement la derniere entree.
            temporaire = self.fichier.with_suffix(".tmp")
            temporaire.write_text(
                json.dumps(
                    {"images": [asdict(e) for e in self._entrees.values()]},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
            temporaire.replace(self.fichier)
        except OSError as erreur:
            log.warning("Catalogue d'images non enregistre : %s", erreur)

    # -- contenu -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._entrees)

    def entrees(self) -> tuple[Entree, ...]:
        return tuple(self._entrees.values())

    def ajouter(self, entree: Entree) -> None:
        self._entrees[entree.chemin] = entree

    def a_jour(self, chemin: Path) -> bool:
        """Cette image est-elle deja decrite, dans sa version actuelle ?"""
        connue = self._entrees.get(str(chemin))
        if connue is None:
            return False
        try:
            etat = chemin.stat()
        except OSError:
            return True  # illisible : ne pas la reindexer en boucle
        return connue.mtime == etat.st_mtime and connue.taille == etat.st_size

    def oublier_les_disparues(self) -> int:
        """Retire les entrees dont le fichier n'existe plus.

        Sans ca, Nova proposerait d'ouvrir une image supprimee il y a six
        mois — et l'echec viendrait de `open`, sans rapport apparent avec la
        recherche qui l'a designee.
        """
        disparues = [c for c in self._entrees if not Path(c).is_file()]
        for chemin in disparues:
            del self._entrees[chemin]
        return len(disparues)

    # -- la recherche ------------------------------------------------------
    def chercher(self, requete: str, limite: int = 3) -> list[tuple[Entree, float]]:
        """Les images qui correspondent le mieux, de la meilleure a la moins bonne.

        ⚠️ LE SCORE EST UNE PROPORTION, PAS UN COMPTE.

        Compter les mots trouves ferait gagner les descriptions LONGUES : plus
        un modele est bavard, plus il attrape de mots au hasard. On mesure
        donc la part des mots de la QUESTION qui sont presents — « casquette
        tenue dans une main » donne 3 mots utiles, et une description qui en
        contient 2 vaut 0,67, qu'elle fasse dix mots ou cent.

        Le nom du fichier compte aussi : « IMG_7826 » ne dit rien, mais
        « facture-edf.png » dit tout, et aucun modele de vision ne le devinera.
        """
        cherches = mots(requete)
        if not cherches:
            return []

        resultats: list[tuple[Entree, float]] = []
        for entree in self._entrees.values():
            connus = set(mots(f"{entree.description} {entree.origine} {entree.nom}"))
            trouves = sum(1 for mot in cherches if mot in connus)
            if trouves:
                resultats.append((entree, trouves / len(cherches)))

        resultats.sort(key=lambda r: (-r[1], -r[0].mtime))
        return resultats[:limite]


#: En dessous, la correspondance n'en est pas une.
#:
#: ⚠️ CE SEUIL DECIDE ENTRE « LA VOICI » ET « JE N'AI PAS TROUVE ».
#:
#: Un seul mot commun sur cinq (0,20) arrive par hasard des que le catalogue
#: grandit : toute photo d'exterieur contient « ciel » ou « arbre ». Ouvrir
#: la mauvaise image sur un score de hasard est pire que ne rien ouvrir —
#: l'utilisateur ne saurait meme pas que la recherche a echoue.
SEUIL_PERTINENCE = 0.34


def indexer(
    images: Iterable[Path],
    catalogue: Catalogue,
    *,
    decrire: Callable[[Path], str],
    traduire: Callable[[list[str]], list[str]] | None = None,
    lot: int = LOT,
) -> int:
    """Decrit les images pas encore connues. Rend le nombre d'ajouts.

    ⚠️ NE LEVE JAMAIS SUR UNE IMAGE.

    Un HEIC illisible, un fichier corrompu, un disque debranche : chacun doit
    coûter cette image-la et pas l'indexation entiere. Une tache de fond qui
    s'arrete a la premiere anomalie ne finit jamais son travail — et personne
    ne le voit, puisqu'elle est de fond.

    `traduire` recoit TOUTES les descriptions du lot d'un coup. C'est ce qui
    permet de ne changer de modele que deux fois par lot au lieu de deux fois
    par image — sur cette machine, chaque bascule coute plusieurs secondes.
    """
    a_faire = [c for c in images if not catalogue.a_jour(c)][:lot]
    if not a_faire:
        return 0

    obtenues: list[tuple[Path, str]] = []
    for chemin in a_faire:
        try:
            description = (decrire(chemin) or "").strip()
        except Exception as erreur:  # noqa: BLE001
            log.warning("Image « %s » non decrite : %s", chemin.name, erreur)
            continue
        if description:
            obtenues.append((chemin, description))

    if not obtenues:
        return 0

    francais = [d for _, d in obtenues]
    if traduire is not None:
        try:
            propose = traduire(francais)
            # Une traduction qui ne rend pas le bon nombre de lignes est
            # inexploitable : on garde l'original plutot que de risquer
            # d'attribuer la description d'une image a une autre.
            if len(propose) == len(obtenues):
                francais = [p.strip() or d for p, d in zip(propose, francais, strict=True)]
            else:
                log.warning(
                    "Traduction ignoree : %d ligne(s) pour %d image(s).",
                    len(propose), len(obtenues),
                )
        except Exception as erreur:  # noqa: BLE001
            log.warning("Descriptions non traduites (%s) — gardees telles quelles.", erreur)

    ajoutees = 0
    for (chemin, origine), description in zip(obtenues, francais, strict=True):
        try:
            etat = chemin.stat()
        except OSError:
            continue
        catalogue.ajouter(
            Entree(
                chemin=str(chemin),
                nom=chemin.name,
                mtime=etat.st_mtime,
                taille=etat.st_size,
                description=description,
                origine=origine if origine != description else "",
                indexee_le=time.time(),
            )
        )
        ajoutees += 1

    if ajoutees:
        catalogue.enregistrer()
        log.info("Catalogue d'images : %d ajoutee(s), %d au total.", ajoutees, len(catalogue))
    return ajoutees


def fichier_par_defaut() -> Path:
    """Ou vit le catalogue. Dans `data/`, avec le reste de ce que Nova garde."""
    from nova.settings import get_settings

    return get_settings().root / "data" / "vision-catalogue.json"


def a_indexer(limite: int = CATALOGUE_MAX) -> list[Path]:
    """Les images des dossiers surveilles, les plus recentes d'abord."""
    from nova.vision.images import _parcourir, dossiers_surveilles

    trouvees: list[Path] = []
    for dossier in dossiers_surveilles():
        if dossier.is_dir():
            trouvees.extend(_parcourir(dossier))

    def date(chemin: Path) -> float:
        try:
            return chemin.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(trouvees, key=date, reverse=True)[:limite]
