"""Executer une intention : POST /v1/action.

LE CONTRAT, EN DEUX TEMPS

L'application envoie ce que Nova a compris. Nova Core repond l'une de quatre
choses :

    executee     c'est fait, voici le message a prononcer
    a_confirmer  voici la QUESTION a poser ; rappelle-moi avec confirme=true
    ignoree      reconnu, mais pas assez sur — ou pas encore implemente
    echouee      tente, et raté ; voici pourquoi

⚠️ `confirme` VIENT DE L'UTILISATEUR, JAMAIS DU MODELE.

C'est toute la difference entre un garde-fou et un decor. Si un modele
pouvait remplir ce champ, il reviendrait a demander au renard s'il a le droit
d'entrer dans le poulailler — et un modele local de trois milliards de
parametres repondrait oui.

L'application doit donc avoir REELLEMENT pose la question et REELLEMENT
entendu la reponse avant de rappeler avec `confirme=true`.

POURQUOI DEUX APPELS PLUTOT QU'UN

Un seul appel devrait porter la reponse a une question pas encore posee. En
deux temps, l'etat vit la ou il doit vivre — chez celui qui parle a
l'utilisateur — et Nova Core reste sans memoire d'un appel a l'autre.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from nova import orchestrator
from nova.logging_setup import get_logger
from nova.voice import comprehension as voice_comprehension
from nova.voice import intentions as voice_intentions

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["actions"])


class DemandeAction(BaseModel):
    """Ce que l'application a compris, et ce qu'elle demande d'en faire."""

    texte: str = Field(description="La phrase, apres comprehension")
    #: Confiance de la PAROLE (0 a 1). L'application la recoit de
    #: /v1/audio/wake ou /v1/audio/transcriptions et la retransmet telle
    #: quelle. Par defaut 1.0 : une demande TAPEE n'a pas de doute
    #: acoustique.
    confiance: float = 1.0
    #: L'utilisateur a-t-il repondu oui a une question deja posee ?
    confirme: bool = False


class ReponseAction(BaseModel):
    etat: str
    message: str
    outil: str | None = None
    niveau: int | None = None
    intention: str | None = None
    cible: str | None = None


@router.post("/action", response_model=ReponseAction)
def executer(demande: DemandeAction) -> ReponseAction:
    """Reconnait l'intention de la phrase et l'execute, si tout concorde."""
    # ⚠️ UN « OUI » NU REPOND A LA PROPOSITION, PAS AU MODELE.
    #
    # Nova vient de dire « je te l'ouvre ? ». La reponse tient en un mot, et
    # ce mot ne porte aucune intention reconnaissable : envoye au modele, il
    # produirait une phrase polie et rien d'autre.
    #
    # Il ne vaut que parce qu'une proposition attend. Hors de ce cas, « oui »
    # repart vers le modele comme n'importe quelle phrase — c'est ce qui rend
    # cette liste de mots aussi courte sans danger.
    from nova.voice import session

    if (acceptee := session.accord(demande.texte)) is not None:
        outil, arguments = acceptee
        fait = orchestrator.executer_outil_propose(outil, arguments)
        log.info("Proposition acceptee « %s » → %s", demande.texte, fait.etat)
        return ReponseAction(
            etat=fait.etat, message=fait.message, outil=fait.outil,
            niveau=fait.niveau, intention="proposition_acceptee", cible=None,
        )

    intention = voice_intentions.reconnaitre(demande.texte)

    # On reconstruit une `Comprehension` minimale : ce point d'entree accepte
    # du TEXTE, pas de l'audio. La confiance acoustique vient de l'appelant,
    # qui l'a obtenue au moment de la transcription — la recalculer ici
    # n'aurait aucun sens, on n'a plus le son.
    comprise = voice_comprehension.Comprehension(
        texte=demande.texte,
        origine=demande.texte,
        confiance=max(0.0, min(1.0, demande.confiance)),
        intention=intention,
    )

    resultat = orchestrator.executer_intention(comprise, confirme=demande.confirme)

    log.info(
        "Action demandee « %s » → %s%s",
        demande.texte, resultat.etat,
        " (confirmee par l'utilisateur)" if demande.confirme else "",
    )
    return ReponseAction(
        etat=resultat.etat,
        message=resultat.message,
        outil=resultat.outil,
        niveau=resultat.niveau,
        intention=intention.nom if intention.reconnue else None,
        cible=intention.cible or None,
    )


@router.get("/actions")
def catalogue() -> dict:
    """Ce que Nova sait faire, et ce qu'il en coute.

    Destine autant a l'humain qui debogue qu'a l'interface, qui peut ainsi
    afficher la liste sans la coder en dur.
    """
    from nova.core import actions, contrats
    from nova.outils import applications, registre_outils

    connues = []
    for nom_intention, action in actions.ACTIONS.items():
        outil = registre_outils.get(action.outil)
        niveau = getattr(outil, "niveau", None) if outil else None
        connues.append(
            {
                "intention": nom_intention,
                "outil": action.outil,
                "disponible": outil is not None,
                "niveau": niveau,
                "niveau_nom": contrats.nom_du_niveau(niveau) if niveau is not None else None,
                "confirmation": contrats.exige_confirmation(niveau) if niveau is not None else True,
                "catalogue": action.catalogue,
            }
        )
    # Le nombre d'applications connues est la premiere chose a regarder quand
    # « ouvre X » repond « je ne trouve pas » : zero veut dire que le
    # catalogue n'a pas ete lu, pas que l'application manque.
    installees = applications.installees()
    return {
        "actions": connues,
        "seuil_intention": actions.SEUIL_INTENTION,
        "intentions_reconnues": list(voice_intentions.intentions_connues()),
        "applications": len(installees),
    }
