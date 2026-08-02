"""Les outils : ce que Nova sait FAIRE, par opposition a ce qu'elle sait dire.

CE QU'EST UN OUTIL

Une fonction nommee, decrite, et retournant une valeur. Un outil ne parle pas
a l'utilisateur, ne decide de rien, et ne connait pas le modele. Il fait une
chose et rend le resultat.

Cette pauvrete est deliberee : c'est elle qui rend un outil testable en trois
lignes, remplacable sans prevenir, et utilisable aussi bien par un agent que
par un appel direct.

AJOUTER UN OUTIL

Aucun fichier existant a modifier — c'est la definition operatoire de
« extensible » :

    from nova.core.registre import registre_outils

    @registre_outils.enregistrer
    class Imprimante:
        nom = "imprimante"
        description = "Envoie un document a l'imprimante par defaut"
        capacite = "action"
        def executer(self, chemin: str) -> str: ...

Le registre valide a l'enregistrement : un outil sans description ou avec une
capacite inconnue fait echouer le demarrage, avec un message qui dit quoi
corriger. Decouvrir six mois plus tard qu'un outil n'a jamais eu de
description est exactement la dette qu'on refuse.

CE QUI N'EST PAS ICI, ET POURQUOI

Terminal, navigateur, impression, camera : ces outils AGISSENT sur la machine
ou sortent de la maison. Ils demandent une politique d'autorisation qui
n'existe pas encore — et livrer un outil « executer une commande shell » sans
cette politique serait irresponsable. Les contrats sont prets ; les outils
viendront avec leur garde-fou, pas avant.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from nova.core.registre import Registre
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Le gestionnaire d'outils. Un `Registre`, pas une classe dediee : outils,
#: agents et espaces ont le meme besoin, et trois gestionnaires auraient
#: diverge en trois endroits.
registre_outils: Registre = Registre("outil")


@registre_outils.enregistrer
class Horloge:
    """L'heure et la date, lues plutot que devinees.

    Un modele de langue n'a aucune notion du temps : sans cet outil il invente
    une heure, avec aplomb. C'est la premiere question que tout le monde pose
    a un assistant vocal, et le premier endroit ou il perd la confiance.
    """

    nom = "horloge"
    description = "Donne la date et l'heure courantes"
    capacite = "recherche"

    JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
    MOIS = (
        "janvier", "fevrier", "mars", "avril", "mai", "juin",
        "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
    )

    def executer(self, maintenant: datetime | None = None) -> dict:
        maintenant = maintenant or datetime.now().astimezone()
        return {
            "heure": maintenant.strftime("%H:%M"),
            "jour": self.JOURS[maintenant.weekday()],
            "date": f"{maintenant.day} {self.MOIS[maintenant.month - 1]} {maintenant.year}",
            "iso": maintenant.isoformat(),
        }


class LireFichier:
    """Lit un fichier texte, DANS le dossier de travail et nulle part ailleurs.

    LA SEULE LIGNE QUI COMPTE VRAIMENT ICI EST LA VERIFICATION DU CHEMIN.

    Un outil de lecture sans borne permet a n'importe quelle demande —
    formulee par l'utilisateur, ou suggeree a Nova par un document qu'elle
    vient de lire — d'atteindre `~/.ssh/id_rsa`. On resout donc le chemin
    reellement (`resolve`, qui suit les liens symboliques et remonte les
    `..`) et on verifie qu'il reste sous la racine.

    Comparer les chaines de caracteres ne suffirait pas : `data/../../.ssh`
    commence bien par `data/`.
    """

    nom = "lire_fichier"
    description = "Lit un fichier texte du dossier de travail"
    capacite = "extraction"

    #: Au-dela, ce n'est plus une lecture, c'est une ingestion — et l'ingestion
    #: a son propre chemin, avec decoupage et indexation.
    TAILLE_MAX = 200_000

    def __init__(self, racine: Path) -> None:
        self.racine = Path(racine).resolve()

    def executer(self, chemin: str) -> str:
        cible = (self.racine / chemin).resolve()
        if not cible.is_relative_to(self.racine):
            raise PermissionError(
                f"« {chemin} » sort du dossier de travail ({self.racine}). "
                "Nova ne lit que ce que tu lui as confie."
            )
        if not cible.is_file():
            raise FileNotFoundError(f"« {chemin} » n'existe pas dans le dossier de travail.")
        if cible.stat().st_size > self.TAILLE_MAX:
            raise ValueError(
                f"« {chemin} » depasse {self.TAILLE_MAX // 1000} Ko. "
                "Passe par l'ingestion :  uv run nova ingest"
            )
        return cible.read_text(encoding="utf-8", errors="replace")


class ChercherDansLesDocuments:
    """Recherche dans les documents ingeres.

    Enveloppe la recherche existante plutot que de la reimplementer : la
    fusion hybride, le classement et le garde-fou du corpus vide sont deja
    ecrits, testes, et n'ont aucune raison de bouger.
    """

    nom = "chercher_documents"
    description = "Cherche un passage dans les documents ingeres"
    capacite = "recherche"

    def executer(self, question: str, limite: int | None = None) -> list[dict]:
        from nova.documents import search  # importe tard : dependance optionnelle

        return [
            {
                "document": hit.document_title,
                "section": hit.heading,
                "extrait": hit.content,
                "chemin": hit.document_path,
            }
            for hit in search.search(question, limit=limite)
        ]


class ChercherDansLaMemoire:
    """Ce que Nova sait de son interlocuteur.

    Distinct de la recherche documentaire, et ca n'est pas un detail : la
    memoire est petite, sure et personnelle ; les documents sont volumineux et
    approximatifs. Les confondre ferait chercher un fait certain par
    similarite — et le fait important est souvent celui qui ne ressemble pas
    a la question.
    """

    nom = "chercher_memoire"
    description = "Consulte les faits que Nova connait sur son interlocuteur"
    capacite = "recherche"

    def executer(self, categorie: str | None = None) -> list[dict]:
        from nova.memory import facts

        return [
            {"categorie": f.category, "fait": f.content, "date": f.created_at.isoformat()}
            for f in facts.list_facts(status="confirmed", category=categorie)
        ]


def enregistrer_outils_standard(racine_travail: Path) -> Registre:
    """Enregistre les outils qui ont besoin d'une configuration.

    Les outils sans etat sont declares par decorateur, a l'import. Ceux qui
    prennent un reglage — ici la racine du dossier de travail — ne peuvent pas
    l'etre : ils sont construits puis enregistres. Le registre accepte les
    deux formes pour cette raison exacte.
    """
    for outil in (LireFichier(racine_travail), ChercherDansLesDocuments(), ChercherDansLaMemoire()):
        if outil.nom not in registre_outils:
            registre_outils.enregistrer(outil)
    return registre_outils
