"""L'agent de vision : trouver l'image, la regarder, dire ce qu'on a vu.

CE QU'UN AGENT AJOUTE A L'OUTIL, ICI PRECISEMENT

L'outil `decrire_image` demande un `chemin`. « decris cette image » n'en
donne aucun — et `core.arguments` refuse de deviner un chemin de fichier,
volontairement : se tromper de fichier ne se rattrape pas comme se tromper de
recherche.

C'est exactement le jugement qui definit un agent. Il cherche l'image dans
trois sources, dans cet ordre :

    1. un CHEMIN ecrit dans la demande      « decris data/piece.jpg »
    2. l'etape qui le porte                  « Observer piece.jpg »
    3. la plus RECENTE du dossier de travail « decris cette image »

⚠️ LE TROISIEME EST UNE DEVINETTE, ET ELLE EST DECLAREE

« cette image » est presque toujours celle qu'on vient de deposer. Refuser de
le comprendre obligerait a demander « laquelle ? » a quelqu'un qui vient de
repondre a cette question en glissant un fichier.

Mais une devinette silencieuse produit la description du mauvais fichier sans
que personne comprenne pourquoi. L'agent NOMME donc toujours l'image
retenue — et dit quand il l'a choisie lui-meme. C'est la difference entre une
heuristique corrigeable et un defaut a chercher.

⚠️ CET AGENT NE PRETEND JAMAIS AVOIR VU.

Vision desactivee, modele absent, image illisible : chacun de ces cas rend un
message qui nomme la cause et le remede. Aucun ne rend une description vide,
ni « je ne distingue pas bien » — une phrase qui a l'air d'une observation
alors que rien n'a ete regarde est le pire resultat possible ici.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nova.core import contrats
from nova.core.contrats import Demande, Etape
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Un chemin de fichier image ecrit dans une phrase.
#:
#: Volontairement etroit : il faut une EXTENSION d'image pour declencher. Un
#: motif plus large attraperait « analyse ma piece » et fabriquerait un chemin
#: a partir d'un mot ordinaire.
CHEMIN = re.compile(
    r"(?<![\w/.-])((?:~|\.{1,2})?[\w./\\-]*\.(?:jpe?g|png|webp|gif|bmp|heic|heif|tiff?))",
    re.IGNORECASE,
)


def chemin_cite(texte: str) -> str | None:
    """Le premier chemin d'image ecrit dans un texte, s'il y en a un."""
    trouve = CHEMIN.search(texte or "")
    return trouve.group(1) if trouve else None


class Vision:
    """Regarde une image et rend ce qu'elle montre.

    Le moteur est INJECTE comme partout ailleurs dans le projet : cet agent
    se teste sans Ollama, sans reseau et sans modele multimodal. C'est ce qui
    permet de verifier le choix de l'image — la seule partie ou il decide
    quelque chose — sans avoir 3 Go a charger.
    """

    nom = "vision"
    description = "Regarde une image et decrit ce qu'elle montre"
    capacites = frozenset({"vision"})
    #: LECTURE : il regarde un fichier, il n'en modifie aucun.
    niveau = contrats.LECTURE

    def __init__(self, racine: Path, *, moteur: Any = None) -> None:
        self.racine = Path(racine)
        self._moteur = moteur

    def peut_traiter(self, etape: Etape) -> bool:
        return etape.capacite in self.capacites

    # -- le jugement : quelle image ---------------------------------------
    def trouver(self, etape: Etape, demande: Demande) -> tuple[Path, bool]:
        """L'image a regarder, et si l'agent a du la deviner.

        Rend un COUPLE plutot qu'un chemin : l'appelant doit pouvoir dire
        « j'ai regarde piece.jpg, que j'ai choisie parce que c'est la plus
        recente ». Sans ce second element, l'agent aurait exactement la meme
        assurance sur un chemin donne et sur un chemin devine.
        """
        from nova.vision.images import la_plus_recente, resoudre

        for texte in (demande.texte, etape.intitule):
            if cite := chemin_cite(texte):
                return resoudre(cite, self.racine), False
        return la_plus_recente(self.racine), True

    # -- l'execution -------------------------------------------------------
    def moteur(self) -> Any:
        if self._moteur is None:
            from nova.vision.moteur import moteur

            self._moteur = moteur(self.racine)
        return self._moteur

    def executer(self, etape: Etape, demande: Demande) -> Any:
        from nova.vision.images import ImageIllisible, ImageIntrouvable
        from nova.vision.moteur import VisionIndisponible

        try:
            cible, devinee = self.trouver(etape, demande)
        except (ImageIntrouvable, ImageIllisible) as absence:
            # ⚠️ ON RELAIE LA CAUSE, ON NE LA RESUME PAS.
            #
            # « je n'ai pas pu voir l'image » se cherche. « Aucune image dans
            # le dossier de travail (…). Depose-la la, ou donne son chemin »
            # se corrige, et le message est deja ecrit a l'endroit qui sait.
            raise VisionIndisponible(str(absence)) from absence

        observation = self.moteur().decrire(cible)
        log.info(
            "Image regardee : %s%s", cible.name, " (choisie : la plus recente)" if devinee else ""
        )
        return {
            "image": cible.name,
            "chemin": str(cible),
            # ⚠️ CE CHAMP EST LA RAISON D'ETRE DU COUPLE RENDU PAR `trouver`.
            #
            # Sans lui, une description du mauvais fichier est indiscernable
            # d'une description du bon.
            "image_devinee": devinee,
            "description": observation.description,
            **observation.brut,
        }
