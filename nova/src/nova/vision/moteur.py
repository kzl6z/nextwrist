"""Le moteur de vision : un modele multimodal, appele par le meme chemin que le reste.

CE QUI CHANGE PAR RAPPORT AU CONTRAT VIDE

`vision/__init__.py` decrivait depuis longtemps ce que la vision RENDRAIT —
`Observation`, `Region` — et levait `PasEncoreImplemente` partout. Ce fichier
en implemente la partie qui tient sur cette machine : DECRIRE. Le reste
continue de lever, avec ce qui manque exactement.

⚠️ LA VISION COUTE DE LA MEMOIRE, ET CETTE MEMOIRE EST DEJA PRISE

C'est le point qui decide de toute l'architecture de ce fichier, et il a ete
mesure sur la machine reelle plus tot dans le projet :

    nova-leger (le modele de langue)   1,9 Go resident
    un multimodal utilisable            1,7 a 3 Go

Sur 8 Go partages avec macOS, l'interface et un navigateur, les deux ne
tiennent pas ensemble. Ollama en decharge donc un pour charger l'autre — et
le rechargement depuis le disque coute un forfait MESURE de 21 secondes,
identique quel que soit le prompt. Cette lenteur frappe la reponse SUIVANTE,
pas l'appel de vision : elle ressemble donc a un ralentissement sans cause.

Trois consequences, toutes assumees dans le code :

  1. LA VISION EST DESACTIVEE PAR DEFAUT (`NOVA_VISION_ACTIVE=false`). Elle
     s'active quand on la veut, en sachant ce qu'elle coute.
  2. `disponible()` DIT LA VERITE, sans appeler le moteur : l'interface peut
     griser un bouton plutot que l'offrir puis echouer.
  3. LE COUT EST MESURE, pas estime. Chaque appel passe par `chrono`, et
     `make vision` compare le modele de langue avant et apres.

⚠️ CE QUI N'EST PAS FAIT, ET POURQUOI JE NE LE PRETENDS PAS

Localiser un objet dans l'image (`detecter`) demande un modele qui rende des
coordonnees. Un multimodal generaliste en INVENTE de plausibles — des boites
bien formees, aux mauvais endroits. Rendre `Region(x=0.3, y=0.2, …)` a partir
de ca serait la pire forme de mensonge disponible ici : structuree, precise,
et fausse. La methode continue donc de lever.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from nova.core import chrono
from nova.logging_setup import get_logger
from nova.settings import get_settings
from nova.vision import Observation, PasEncoreImplemente, Region
from nova.vision.images import ImagePrete, preparer, racines, resoudre

log = get_logger(__name__)


class VisionIndisponible(RuntimeError):
    """La vision est demandee mais pas utilisable. Le message dit quoi faire."""


#: Ce qu'on demande au modele. Court, et en francais.
#:
#: ⚠️ « SOIS CONCIS » N'EST PAS UNE COQUETTERIE.
#:
#: Un multimodal laisse libre ecrit quinze lignes sur la lumiere et l'ambiance
#: de la photo. A 20 jetons par seconde sur cette machine, c'est une minute
#: d'attente pour une information qu'on n'a pas demandee — et Nova la LIT a
#: voix haute.
CONSIGNE_DECRIRE = (
    "Decris cette image en francais, en trois phrases au plus. "
    "Dis ce qu'on voit, pas ce que ca evoque. "
    "Si du texte est lisible, cite-le."
)

CONSIGNE_COMPOSANTS = (
    "Enumere en francais les objets et pieces visibles sur cette image, "
    "un par ligne, sans phrase ni commentaire. "
    "N'ecris que ce que tu vois reellement."
)


def _messages(consigne: str, image: ImagePrete) -> list[dict[str, Any]]:
    """Un message multimodal au format compatible OpenAI.

    ⚠️ ON PASSE PAR `/v1`, COMME TOUT LE RESTE DU PROJET.

    L'API native d'Ollama a son propre champ `images`, et elle marcherait. La
    prendre ici ferait de `vision/` le deuxieme endroit du projet qui sait
    qu'Ollama existe — et rendrait le moteur non remplacable pour un gain
    nul. `image_url` avec une URI `data:` est la forme standard ; Ollama,
    llama.cpp et les moteurs distants la comprennent tous.
    """
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": consigne},
                {"type": "image_url", "image_url": {"url": image.uri}},
            ],
        }
    ]


class MoteurOllama:
    """La vision, par un modele multimodal servi localement.

    `client` est INJECTE plutot qu'importe, pour la meme raison que partout
    ailleurs : ce moteur se teste sans Ollama, sans reseau et sans machine.
    """

    nom = "vision"
    description = "Analyse d'images par un modele multimodal local"
    capacites = frozenset({"vision", "extraction"})

    def __init__(
        self,
        racine: Path | Iterable[Path],
        *,
        client: Any = None,
        modele: str | None = None,
        cote_max: int | None = None,
    ) -> None:
        reglages = get_settings()
        # ⚠️ UNE RACINE OU PLUSIEURS — ET LE TYPE NE DOIT PAS DECIDER SEUL.
        #
        # `Path(racine)` sur un tuple leve « argument should be a str or an
        # os.PathLike object […] not 'tuple' ». Releve en conditions reelles :
        # la vision echouait a CHAQUE demande vocale, et l'utilisateur voyait
        # une reponse inventee — parce que le message d'erreur partait dans le
        # prompt et que le modele preferait broder plutot que le relayer.
        #
        # Un defaut de plomberie de trois caracteres, transforme en
        # hallucination par la couche du dessus.
        self.racines = racines(racine)
        self.modele = modele or reglages.vision_modele
        # Surchargeable pour que le banc puisse balayer plusieurs tailles dans
        # une seule session, sans editer `.env` entre chaque essai — donc sans
        # risquer de conclure sur un reglage qu'on croit avoir change.
        self.cote_max = cote_max or reglages.vision_cote_max
        self._client = client

    # -- plomberie ---------------------------------------------------------
    def client(self) -> Any:
        """Le client du modele. Construit tard : importer `llm` coute a l'import."""
        if self._client is None:
            from nova.llm.client import LLMClient

            self._client = LLMClient(model=self.modele)
        return self._client

    def _regarder(self, consigne: str, image: ImagePrete) -> str:
        with chrono.mesurer("vision — modele"):
            reponse = self.client().chat(_messages(consigne, image), temperature=0.1)
        return (reponse or "").strip()

    def _preparer(self, image: Path | str) -> ImagePrete:
        # ⚠️ UN `Path` NE CONTOURNE PAS LA VERIFICATION.
        #
        # Il aurait ete tentant de considerer qu'un `Path` vient du code et
        # une `str` de l'utilisateur, donc que seul le second merite d'etre
        # borne. C'est faux : `Path(reponse_du_modele)` est un `Path`. Une
        # borne qui admet une exception n'est pas une borne, et le type d'une
        # variable ne dit rien de la confiance qu'on lui doit.
        cible = resoudre(str(image), self.racines)
        with chrono.mesurer("vision — preparation"):
            return preparer(cible, cote_max=self.cote_max)

    # -- ce qui marche -----------------------------------------------------
    def decrire(self, image: Path | str) -> Observation:
        """Ce qu'il y a sur l'image, en trois phrases."""
        prete = self._preparer(image)
        description = self._regarder(CONSIGNE_DECRIRE, prete)
        if not description:
            raise VisionIndisponible(
                f"Le modele « {self.modele} » n'a rien repondu sur « {prete.source.name} ». "
                "Est-il bien multimodal ?  ollama list"
            )
        return Observation(
            source=prete.source,
            description=description,
            brut={
                "modele": self.modele,
                "octets_envoyes": prete.octets,
                "reduite": prete.reduite,
            },
        )

    def identifier_composants(self, image: Path | str) -> tuple[str, ...]:
        """Les objets visibles, un par ligne.

        Meme appel que `decrire`, autre consigne. Les separer sert a l'etape
        « Identifier l'objet et ses composants » du plan de diagnostic, qui a
        besoin d'une LISTE et pas d'un paragraphe.
        """
        prete = self._preparer(image)
        brut = self._regarder(CONSIGNE_COMPOSANTS, prete)
        lignes = (
            ligne.strip(" -•*\t").strip()
            for ligne in brut.splitlines()
        )
        return tuple(ligne for ligne in lignes if ligne)

    # -- ce qui ne marche pas, et le dit -----------------------------------
    def detecter(self, image: Path) -> tuple[Region, ...]:
        raise PasEncoreImplemente(
            "Localiser un objet demande un modele qui rende des coordonnees. Un "
            "multimodal generaliste en invente de plausibles : des boites bien "
            "formees, aux mauvais endroits. Rendre des Region a partir de ca "
            "serait structure, precis, et faux."
        )

    def analyser_video(
        self, video: Path, images_par_seconde: float = 1.0
    ) -> tuple[Observation, ...]:
        raise PasEncoreImplemente(
            "L'analyse video demande un decoupage en images-cles (ffmpeg), puis "
            "une description par image. Le cout est celui de `decrire`, "
            "multiplie par le nombre d'images — soit des minutes sur cette "
            "machine. A faire quand la description d'une image sera rapide."
        )

    def documenter(self, composant: str) -> dict[str, Any]:
        raise PasEncoreImplemente(
            "La recherche de documentation demande un acces reseau et une "
            "politique de sortie de donnees : c'est une decision, pas un detail."
        )

    def preparer_reconstruction(self, vues: tuple[Path, ...]) -> dict[str, Any]:
        raise PasEncoreImplemente(
            "La reconstruction 3D par photogrammetrie est un projet a part "
            "entiere, pas une fonction."
        )


def disponible() -> tuple[bool, str]:
    """La vision est-elle utilisable ? Et sinon, qu'est-ce qui manque ?

    ⚠️ UN BOOLEEN SEUL AURAIT ETE INUTILISABLE.

    « Non » ne se corrige pas. « Le modele n'est pas active » et « le modele
    n'est pas telecharge » demandent deux gestes differents, et l'interface
    doit pouvoir les dire. C'est la meme raison qui a fait de `Resultat` une
    structure a quatre etats plutot qu'un booleen.

    Cette fonction NE CHARGE RIEN et n'interroge pas le moteur : elle doit
    pouvoir etre appelee a chaque affichage sans rien couter.
    """
    reglages = get_settings()
    if not reglages.vision_active:
        return False, (
            "La vision est desactivee. Elle charge un modele de 2 a 3 Go qui "
            "decharge le modele de langue sur cette machine.\n"
            "Pour l'activer :  NOVA_VISION_ACTIVE=true dans .env"
        )
    if not reglages.vision_modele:
        return False, "Aucun modele de vision configure (NOVA_VISION_MODELE)."
    return True, ""


def moteur(racine: Path) -> MoteurOllama:
    """Le moteur de vision, ou une exception qui dit ce qui manque."""
    utilisable, raison = disponible()
    if not utilisable:
        raise VisionIndisponible(raison)
    return MoteurOllama(racine)
