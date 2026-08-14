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

    from nova.core import contrats
    from nova.core.registre import registre_outils

    @registre_outils.enregistrer
    class Imprimante:
        nom = "imprimante"
        description = "Envoie un document a l'imprimante par defaut"
        capacite = "action"
        # Du papier sort, mais on peut annuler et jeter la feuille.
        niveau = contrats.REVERSIBLE
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

from nova.core import contrats
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
    niveau = contrats.LECTURE

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
    # Lit uniquement, et dans un bac a sable. Ne modifie rien.
    niveau = contrats.LECTURE

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
    niveau = contrats.LECTURE

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
    niveau = contrats.LECTURE

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


# ══════════════════════════════════════════════════════════════════════════
#  LE PORTILLON — le seul endroit par lequel un outil s'execute
#
#  ⚠️ UN MODELE DE LANGUE PROPOSE. IL N'AUTORISE JAMAIS.
#
#  Un modele local de trois milliards de parametres se trompe : il hallucine
#  un nom de fichier, confond deux applications, prend une transcription
#  bancale pour un ordre. Tant qu'il ne fait que parler, aucune de ces
#  erreurs ne coute rien. Le jour ou il agit, chacune devient un geste reel
#  sur la machine de quelqu'un.
#
#  Ce portillon ne rend pas le modele plus fiable — rien ne le fera. Il rend
#  ses erreurs RATTRAPABLES, ce qui est la seule garantie possible.
#
#  POURQUOI UNE SEULE PORTE
#
#  Un controle duplique a trois endroits finit contourne au quatrieme, et
#  c'est toujours celui qu'on a ajoute en urgence. `executer_outil` est donc
#  le SEUL chemin : appeler `outil.executer()` directement contourne le
#  bareme, et c'est un bug — pas une optimisation.
# ══════════════════════════════════════════════════════════════════════════


class ConfirmationRequise(PermissionError):
    """L'action est legitime mais attend un accord explicite.

    Volontairement une exception et non une valeur de retour : oublier de
    verifier un booleen est facile et silencieux, ignorer une exception
    demande de l'ecrire. La forme la plus sure est celle qui echoue par
    defaut.
    """

    def __init__(self, outil: str, niveau: int, arguments: dict) -> None:
        self.outil = outil
        self.niveau = niveau
        self.arguments = arguments
        super().__init__(
            f"« {outil} » est une action de niveau "
            f"{contrats.nom_du_niveau(niveau)} : elle demande une confirmation."
        )

    def question(self) -> str:
        """Ce que Nova doit demander, en francais, avant d'agir."""
        details = ", ".join(f"{c} = {v}" for c, v in self.arguments.items())
        precision = f" ({details})" if details else ""
        return f"Je m'apprete a {self.outil}{precision}. Je confirme ?"


def executer_outil(nom: str, *, confirme: bool = False, **arguments):
    """Execute un outil, apres avoir verifie ce qu'il en coute.

    `confirme` ne doit JAMAIS venir du modele. Il vient de l'utilisateur, par
    l'interface — sinon le controle se resume a demander au renard s'il a le
    droit d'entrer dans le poulailler.
    """
    outil = registre_outils.exiger(nom)
    niveau = getattr(outil, "niveau", None)

    # Un outil sans niveau ne devrait pas pouvoir etre enregistre. S'il s'en
    # trouve un ici, c'est que quelqu'un a contourne le registre : on refuse
    # plutot que de supposer qu'il est inoffensif.
    if not isinstance(niveau, int) or niveau not in contrats.NIVEAUX:
        raise ConfirmationRequise(nom, -1, arguments)

    if contrats.exige_confirmation(niveau) and not confirme:
        log.info(
            "Action « %s » (%s) suspendue : confirmation attendue.",
            nom, contrats.nom_du_niveau(niveau),
        )
        raise ConfirmationRequise(nom, niveau, arguments)

    log.info("Action « %s » (%s) executee.", nom, contrats.nom_du_niveau(niveau))
    return outil.executer(**arguments)
