"""Le fournisseur local : Ollama, par le client qui existe deja.

⚠️ CE MODULE N'IMPLEMENTE RIEN. IL ENVELOPPE.

Tout ce qui a coute cher est dans `llm/client.py` et y reste :

    le filtre `<think>`          qwen3:4b, 2600 caracteres pour dire bonjour
    `reasoning_effort=none`      le seul des trois interrupteurs qui marche
    la coupure du JSON           24 431 ms pour un mot de six caracteres
    les delais separes           connecter n'est pas repondre
    `keep_alive`                 21 secondes de rechargement, a cout fixe
    le compteur de silence       « aucune reponse » apres 39 s de travail reel

Reecrire cela pour « uniformiser les fournisseurs » aurait perdu six
corrections dont chacune a demande une mesure sur la machine. Le fournisseur
local delegue donc, et ne connait qu'une chose de plus qu'avant : quel modele
le routeur a choisi.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from nova.core.contrats import Modele
from nova.logging_setup import get_logger
from nova.modeles import Message

log = get_logger(__name__)


class Ollama:
    """Les modeles qui tournent sur la machine."""

    id = "ollama"
    nom = "Ollama (local)"

    def __init__(self, url: str | None = None) -> None:
        self._url = url

    # ── Ce que le fournisseur propose ────────────────────────────────────
    def modeles(self) -> tuple[Modele, ...]:
        """Le catalogue local, tel que la configuration le decrit.

        ⚠️ LES CAPACITES ET LA VITESSE VIENNENT DE LA MESURE, PAS D'UNE FICHE.

        C'est la lecon la plus chere du projet, deja ecrite dans le routeur :
        `qwen3:4b` etait excellent sur le papier et inutilisable ici — mille
        jetons de monologue avant le premier mot, qu'aucune documentation ne
        mentionne. `scripts/bench_models.py` mesure, `.env` porte le
        resultat.
        """
        from nova.core import plateforme
        from nova.settings import get_settings

        reglages = get_settings()
        machine = plateforme.detecter()
        return (
            Modele(
                nom=reglages.chat_model,
                capacites=frozenset(
                    {"conversation", "raisonnement", "extraction", "redaction"}
                ),
                vitesse=reglages.vitesse_mesuree,
                # Une estimation prudente vaut mieux qu'une valeur absente :
                # elle sert a departager, pas a decider seule.
                poids=min(machine.budget_modele_go, 2.0),
                distant=False,
                fournisseur=self.id,
            ),
        )

    def disponible(self) -> bool:
        """Toujours, du point de vue du routage — et c'est volontaire.

        ⚠️ NE PAS INTERROGER OLLAMA ICI.

        Un `GET /models` coute un aller-retour, et cette question est posee a
        chaque routage. Le service local est le DEFAUT : s'il est eteint,
        l'appel echouera et le recours prendra la main, avec un message qui
        dit quoi faire. Le decouvrir en echouant coute une fois ; le verifier
        d'avance coute a chaque question.
        """
        return True

    # ── Ce que le fournisseur fait ───────────────────────────────────────
    def _client(self, modele: Modele):
        from nova.llm.client import LLMClient

        return LLMClient(base_url=self._url, model=modele.nom)

    def flux(
        self,
        modele: Modele,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        return self._client(modele).stream(
            list(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def generer(
        self,
        modele: Modele,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
    ) -> str:
        return self._client(modele).chat(list(messages), temperature=temperature)

    def sante(self) -> bool:
        from nova.llm.client import LLMClient

        return LLMClient(base_url=self._url).health()
