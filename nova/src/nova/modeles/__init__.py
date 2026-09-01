"""Les fournisseurs de modeles : une seule facon de parler a n'importe quel cerveau.

CE QUI EXISTAIT DEJA, ET QU'IL NE FALLAIT PAS REFAIRE

    core/routeur.py   CHOISIT un modele pour un usage — capacite, vitesse,
                      local exige, monologue. Il est mesure, teste, et il
                      etait deja juste.
    llm/client.py     PARLE a Ollama — flux, filtre de raisonnement, coupure
                      du JSON, mise en chauffe, delais separes. Tout ce qui a
                      coute cher a regler est la-dedans.

⚠️ ET POURTANT LE CHOIX DU ROUTEUR N'ARRIVAIT NULLE PART.

C'est le defaut que cette couche corrige, et il vaut d'etre nomme : le
routeur choisissait un modele, personne ne lisait sa reponse, et
`LLMClient()` relisait `settings.chat_model` directement. Le seul appelant de
`routeur()` etait `/v1/capacites`, pour AFFICHER la liste.

Un module qui existe, qui est teste, et dont le resultat est jete est plus
trompeur qu'un module absent — c'est la lecon deja ecrite dans
`core/gestionnaire.py`, a propos des agents que rien n'inscrivait. Elle vaut
une seconde fois.

CE QUE CETTE COUCHE AJOUTE, ET RIEN DE PLUS

    un CONTRAT commun          `Fournisseur`
    une mise en oeuvre         Ollama, en local
    un RECOURS                 si le premier echoue, le suivant essaie
    le CABLAGE                 le choix du routeur atteint enfin un moteur

⚠️ UN SEUL FOURNISSEUR AUJOURD'HUI, ET C'EST UN CHOIX EXPLICITE.

Claude a existe ici, par l'API Anthropic. Il a ete retire sur demande — « je
ne veux pas de Claude ». Le contrat, lui, reste : c'est ce qui permettra
d'ajouter un second modele Ollama, un modele specialise ou le modele Nova
sans toucher a un seul appelant.

Le garder « au cas ou » aurait ete pire que le retirer. Du code mort qu'on
conserve finit par etre execute par accident — la lecon de `_TOUT_OUVRIR`.

`llm/client.py` n'est pas remplace : le fournisseur local l'appelle. Rien de
ce qui a ete regle a l'usage n'est reecrit.

⚠️ LE RECOURS S'ARRETE AU PREMIER JETON SORTI, ET C'EST NON NEGOCIABLE.

Une fois qu'un fragment est parti vers l'interface — donc vers la synthese
vocale — changer de modele ne repare rien : cela colle la fin d'une reponse a
la moitie d'une autre. L'utilisateur entendrait une phrase qu'aucun modele
n'a ecrite.

« Ne jamais pretendre qu'un modele a repondu si la requete n'a pas ete
executee » vaut aussi dans l'autre sens : ne jamais assembler deux moities.
Le recours n'a donc lieu que TANT QUE RIEN N'EST SORTI.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol, runtime_checkable

from nova.core.contrats import Modele

Message = dict[str, str]


class FournisseurIndisponible(RuntimeError):
    """Ce fournisseur ne peut pas servir — et le message dit pourquoi.

    Distincte de `LLMError` a dessein : celle-ci signifie « n'essaie meme
    pas », l'autre « j'ai essaye et ca a rate ». Le routage les traite
    pareil — il passe au suivant — mais le journal ne dit pas la meme chose,
    et c'est le journal qu'on lit a trois heures du matin.
    """


@runtime_checkable
class Fournisseur(Protocol):
    """Ce que tout fournisseur de modeles sait faire.

    ⚠️ LE RESTE DE NOVA NE DOIT JAMAIS SAVOIR QUI REPOND.

    C'est la premiere des frontieres stables du projet, deja tenue par
    `llm/client.py` pour Ollama seul. On l'elargit sans la deplacer : un
    appelant demande une CAPACITE, il recoit du texte. Qu'il vienne d'un
    modele local, d'une API, ou un jour du modele Nova, ne change pas une
    ligne chez lui.
    """

    #: Identifiant stable, technique. Sert aux journaux et aux reglages.
    id: str
    #: Nom lisible, pour l'interface.
    nom: str

    def modeles(self) -> tuple[Modele, ...]:
        """Ce que ce fournisseur met a disposition, et ce que ca sait faire.

        Rend une description, pas une connexion : cet appel ne doit RIEN
        couter. Il est fait a chaque routage.
        """
        ...

    def disponible(self) -> bool:
        """Peut-on l'utiliser MAINTENANT, sans rien lui demander ?

        ⚠️ SANS APPEL RESEAU. C'est la difference avec `sante()`.

        Cette question est posee dans le chemin de la reponse : une clef
        absente ou un mode local-seul se constatent en memoire. Verifier par
        le reseau ajouterait un aller-retour a chaque question, ce qui est
        exactement ce que le routage promet de ne pas faire.
        """
        ...

    def flux(
        self,
        modele: Modele,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        """La reponse, morceau par morceau.

        Le flux n'est pas cosmetique : sur un modele local, la premiere phrase
        arrive en une seconde alors que la reponse complete peut en prendre
        trente. C'est la difference entre « ca repond » et « c'est fige ».
        """
        ...

    def generer(
        self,
        modele: Modele,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
    ) -> str:
        """La reponse complete, en un bloc. Pour la CLI et les traitements de fond."""
        ...

    def sante(self) -> bool:
        """Le service repond-il ? PEUT couter un aller-retour reseau.

        Reserve a `/health` et au diagnostic. Jamais dans le chemin d'une
        reponse.
        """
        ...


__all__ = [
    "Fournisseur",
    "FournisseurIndisponible",
    "Message",
    "Modele",
]
