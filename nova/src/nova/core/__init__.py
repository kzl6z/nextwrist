"""Le noyau de Nova : les contrats, le registre, le routeur, le planificateur.

Ces quatre modules ne connaissent ni la base de donnees, ni le moteur
d'inference, ni l'interface. Ils ne manipulent que des descriptions et des
decisions — ce qui les rend testables sans machine, et encore vrais quand
tout le reste aura change.

    api  ->  orchestrator  ->  core  ->  contrats
                           ->  memory / documents / llm / voice  ->  db
"""

from nova.core.contrats import (
    CAPACITES_CONNUES,
    Agent,
    Demande,
    EspaceDeTravail,
    Etape,
    Modele,
    Outil,
    Plan,
)
from nova.core.planificateur import planifier, planifier_deterministe
from nova.core.registre import ErreurRegistre, Registre
from nova.core.routeur import USAGES, AucunModele, Exigence, Routeur

__all__ = [
    "CAPACITES_CONNUES",
    "Agent",
    "AucunModele",
    "Demande",
    "ErreurRegistre",
    "EspaceDeTravail",
    "Etape",
    "Exigence",
    "Modele",
    "Outil",
    "Plan",
    "Registre",
    "Routeur",
    "USAGES",
    "planifier",
    "planifier_deterministe",
]
