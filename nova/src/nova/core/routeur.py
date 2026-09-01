"""Le routeur de modeles : quel modele pour quelle tache.

L'UTILISATEUR NE CHOISIT PAS L'IA. NOVA CHOISIT.

C'est une exigence explicite du projet, et c'est aussi la seule facon de
tenir dix ans : le jour ou un meilleur modele sort, il entre dans la table et
tout le systeme en profite. Aucun appelant ne nomme jamais un modele.

SUR QUOI SE FONDE LE CHOIX

Sur des MESURES, jamais sur des reputations. Chaque modele est decrit par ce
que `scripts/bench_models.py` a constate sur la machine reelle : sa vitesse
d'ecriture, son poids, et s'il monologue avant de repondre.

C'est la lecon la plus chere du projet. `qwen3:4b` avait ete recommande sur
ses caracteristiques generales — excellent francais, excellent appel
d'outils — et s'est revele inutilisable ici : mille jetons de raisonnement
invisible avant le premier mot. Aucune fiche technique ne le mentionne.

LA REGLE DE SELECTION, ET POURQUOI ELLE EST DANS CET ORDRE

    1. Ecarter ceux qui n'ont pas la capacite demandee.
    2. Ecarter ceux qui monologuent, si la reponse doit etre prononcee.
    3. Ecarter ceux qui n'atteignent pas la vitesse minimale de l'usage.
    4. Parmi les restants : le PLUS CAPABLE, pas le plus rapide.

Le point 4 merite d'etre defendu. Un modele deux fois plus rapide qu'un autre
alors que les deux sont deja sous le seuil de confort n'apporte rien : la
difference ne s'entend pas, d'autant que la parole en flux commence des la
premiere phrase. Le milliard de parametres en moins, lui, s'entend a chaque
reponse. On ne troque de la capacite contre de la vitesse que SOUS le seuil.

C'est la regle du projet, ecrite le premier jour : « une IA extraordinairement
intelligente avec une interface simple bat une interface spectaculaire avec
une IA mediocre ».
"""

from __future__ import annotations

from dataclasses import dataclass

from nova.core.contrats import Modele
from nova.logging_setup import get_logger

log = get_logger(__name__)


class AucunModele(RuntimeError):
    """Aucun modele ne convient, avec l'explication de ce qui a ete ecarte."""


@dataclass(frozen=True)
class Exigence:
    """Ce qu'un usage attend d'un modele.

    Nommer les usages plutot que les modeles est ce qui rend le systeme
    durable : `USAGES["vocal"]` reste vrai en 2035, `"llama3.2:3b"` non.
    """

    capacite: str
    #: Jetons par seconde en dessous desquels l'usage devient penible.
    vitesse_min: float = 0.0
    #: La reponse sera-t-elle prononcee ? Si oui, un modele qui monologue est
    #: disqualifie, quelles que soient ses autres qualites.
    parlee: bool = False
    #: Interdit-on la sortie des donnees de la machine ?
    local_exige: bool = False
    #: Le modele local suffit-il a cet usage ?
    #:
    #: ⚠️ SANS CE CHAMP, UN MODELE DISTANT DECLARE GAGNE TOUT.
    #:
    #: La regle du routeur est « le plus capable, pas le plus rapide », et le
    #: poids en est l'approximation. Un modele distant pese cent : des qu'il
    #: est configure, il rafle la conversation courante — « quelle heure
    #: est-il » partirait sur Internet, avec sa latence, son cout et la
    #: sortie de donnees qui va avec.
    #:
    #: C'est exactement ce que le mode local d'abord existe pour empecher :
    #: privilegier le local QUAND IL SUFFIT. Il ne suffit pas pour tout — le
    #: raisonnement lourd et le grand contexte laissent la capacite decider,
    #: et c'est pour cela que ce champ est par usage et non global.
    local_suffit: bool = True


USAGES: dict[str, Exigence] = {
    # Le quotidien : on parle a Nova, elle repond a voix haute.
    "vocal": Exigence("conversation", vitesse_min=12.0, parlee=True, local_exige=True),
    # Ecrit : on peut attendre un peu plus pour une meilleure reponse. Le
    # local suffit — « quelle heure est-il » n'a rien a faire sur Internet.
    "conversation": Exigence("conversation", vitesse_min=6.0),
    # Analyse lourde : la qualite prime, le temps est secondaire. C'est le
    # seul usage courant ou l'on accepte de sortir de la machine.
    "raisonnement": Exigence("raisonnement", vitesse_min=0.0, local_suffit=False),
    # Sortie structuree : ni vitesse ni finesse, mais de la rigueur.
    "extraction": Exigence("extraction", vitesse_min=6.0, local_exige=True),
    # Le local ne declare pas « code » : en pratique, seul un distant repond.
    "code": Exigence("code", vitesse_min=6.0, local_suffit=False),
    "vision": Exigence("vision", vitesse_min=0.0),
    # Cent mille jetons de contexte : aucun modele de 3 Go n'y arrive.
    "long_contexte": Exigence("long_contexte", vitesse_min=0.0, local_suffit=False),
}


class Routeur:
    """Choisit un modele pour un usage. Ne parle a aucun moteur."""

    def __init__(self, modeles: tuple[Modele, ...] = ()) -> None:
        self._modeles = tuple(modeles)

    def declarer(self, modele: Modele) -> None:
        """Ajoute un modele au catalogue, ou remplace celui du meme nom."""
        self._modeles = tuple(m for m in self._modeles if m.nom != modele.nom) + (modele,)

    @property
    def modeles(self) -> tuple[Modele, ...]:
        return self._modeles

    def choisir(self, usage: str) -> Modele:
        """Le meilleur modele pour cet usage.

        Leve `AucunModele` avec le detail de ce qui a ete ecarte, plutot que
        de rendre un modele approximatif. Un mauvais choix silencieux est
        pire qu'un echec : il se manifeste par des reponses mediocres qu'on
        attribue au projet entier.
        """
        return self.classer(usage)[0]

    def classer(self, usage: str) -> tuple[Modele, ...]:
        """TOUS les modeles admissibles, du meilleur au moins bon.

        ⚠️ SANS CETTE LISTE, IL N'Y A PAS DE RECOURS POSSIBLE.

        `choisir` rendait un modele et jetait les autres. Quand ce modele
        echoue — Ollama eteint, plus de reseau, delai depasse — l'appelant
        n'a plus rien : il ne sait meme pas qu'un second candidat existait.
        Le recours n'est pas une politique en plus, c'est cette liste.

        ⚠️ ET LES ECARTES RESTENT ECARTES.

        Un modele sans la capacite demandee, ou qui monologue alors que la
        reponse sera prononcee, ne devient pas acceptable parce que le
        premier est tombe. Ce serait echanger une panne visible contre une
        reponse mediocre inexplicable — et pour le vocal, faire sortir de la
        machine des donnees qu'un usage local interdisait.
        """
        exigence = USAGES.get(usage)
        if exigence is None:
            connus = ", ".join(sorted(USAGES))
            raise AucunModele(f"usage inconnu « {usage} ». Connus : {connus}.")

        rejets: list[str] = []
        candidats: list[Modele] = []

        for modele in self._modeles:
            if exigence.capacite not in modele.capacites:
                rejets.append(f"{modele.nom} : ne sait pas « {exigence.capacite} »")
                continue
            if exigence.parlee and modele.raisonne_a_voix_haute:
                rejets.append(f"{modele.nom} : monologue avant de repondre")
                continue
            if exigence.local_exige and modele.distant:
                rejets.append(f"{modele.nom} : sort de la machine")
                continue
            if modele.vitesse < exigence.vitesse_min:
                rejets.append(
                    f"{modele.nom} : {modele.vitesse:.0f} jetons/s "
                    f"(minimum {exigence.vitesse_min:.0f})"
                )
                continue
            candidats.append(modele)

        if not candidats:
            detail = "\n  ".join(rejets) or "aucun modele declare"
            raise AucunModele(
                f"aucun modele pour l'usage « {usage} ».\n  {detail}\n"
                "Mesure tes modeles :  uv run python scripts/bench_models.py"
            )

        # ⚠️ LE LOCAL D'ABORD QUAND IL SUFFIT — C'EST LE PREMIER CRITERE.
        #
        # Le tri de fond reste « le plus capable, pas le plus rapide » : a
        # poids egal, le plus rapide departage ; a poids et vitesse egaux, le
        # local l'emporte. Mais quand l'usage declare que le local SUFFIT, il
        # passe devant quoi qu'il arrive.
        #
        # Sans cela, un modele distant configure raflait la conversation
        # courante — moins de vie privee, plus de latence, un cout par
        # question, et tout cela pour une reponse que le local donnait deja.
        #
        # Les distants restent dans la liste, derriere : ils servent de
        # recours quand le local tombe.
        local_prefere = exigence.local_suffit
        candidats.sort(
            key=lambda m: (
                local_prefere and not m.distant,
                m.poids,
                m.vitesse,
                not m.distant,
            ),
            reverse=True,
        )
        if len(candidats) > 1:
            log.debug(
                "Usage « %s » : %s retenu parmi %s",
                usage,
                candidats[0].nom,
                ", ".join(c.nom for c in candidats),
            )
        return tuple(candidats)

    def expliquer(self, usage: str) -> str:
        """Pourquoi ce modele — pour le journal et pour l'interface."""
        try:
            modele = self.choisir(usage)
        except AucunModele as exc:
            return str(exc)
        exigence = USAGES[usage]
        return (
            f"{modele.nom} pour « {usage} » : {modele.poids:.1f} Go, "
            f"{modele.vitesse:.0f} jetons/s "
            f"(minimum {exigence.vitesse_min:.0f}), "
            f"{'local' if not modele.distant else 'distant'}"
        )
