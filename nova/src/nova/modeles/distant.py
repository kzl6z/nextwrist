"""Le fournisseur distant : Claude, par l'API Anthropic.

⚠️ TOUT CE QUI PART D'ICI SORT DE LA MACHINE.

C'est la seule chose qui distingue vraiment ce fournisseur du local, et c'est
la raison pour laquelle le routeur porte un champ `local_exige`. Un usage
declare « local » — le vocal, l'extraction — ne verra jamais ce fournisseur,
quelle que soit sa qualite. Le choix n'est pas negociable a l'execution : il
est pris a la selection, ou il se lit.

LA CLEF

Elle vient de la configuration, jamais du code, et elle ne figure dans aucun
journal. Ce projet a deja perdu une clef parce qu'elle etait visible sur une
capture d'ecran : ce module n'ecrit donc ni sa valeur, ni sa longueur, ni ses
premiers caracteres. « presente » ou « absente », rien d'autre.

AUCUNE DEPENDANCE NOUVELLE

`httpx` est deja la, et l'API d'Anthropic est du HTTP avec des evenements
SSE. Ajouter un SDK pour trois appels aurait ajoute une chaine de dependances
a une machine de 8 Go qui doit deja loger un modele local.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence

import httpx

from nova.core.contrats import Modele
from nova.logging_setup import get_logger
from nova.modeles import FournisseurIndisponible, Message

log = get_logger(__name__)

#: Version de l'API, exigee par Anthropic sur chaque appel.
VERSION_API = "2023-06-01"

#: Meme raison que cote Ollama : connecter n'est pas repondre. Un service
#: distant injoignable doit se constater vite, pas au bout d'une minute.
CONNEXION_S = 5.0


class Anthropic:
    """Les modeles Claude, par l'API cloud."""

    id = "anthropic"
    nom = "Claude (Anthropic)"

    def __init__(
        self,
        *,
        cle: str = "",
        url: str = "https://api.anthropic.com/v1",
        modele: str = "",
        capacites: frozenset[str] = frozenset(),
        poids: float = 0.0,
        vitesse: float = 0.0,
        delai: float = 120.0,
    ) -> None:
        self._cle = cle
        self._url = url.rstrip("/")
        self._modele = modele
        self._capacites = capacites
        self._poids = poids
        self._vitesse = vitesse
        self._delai = delai

    # ── Ce que le fournisseur propose ────────────────────────────────────
    def modeles(self) -> tuple[Modele, ...]:
        """Un seul modele, celui que la configuration nomme.

        ⚠️ ON N'INTERROGE PAS LE CATALOGUE D'ANTHROPIC.

        Ce serait un appel reseau a chaque routage, pour une liste qui change
        deux fois par an. Le modele se declare dans `.env`, comme le modele
        local — et pour la meme raison : ce qui depend du compte et de la
        machine n'a rien a faire dans le code.
        """
        if not self._modele:
            return ()
        return (
            Modele(
                nom=self._modele,
                capacites=self._capacites,
                vitesse=self._vitesse,
                poids=self._poids,
                distant=True,
                fournisseur=self.id,
            ),
        )

    def disponible(self) -> bool:
        """Une clef et un modele. Rien de plus, et surtout aucun appel."""
        return bool(self._cle and self._modele)

    # ── Ce que le fournisseur fait ───────────────────────────────────────
    def _entetes(self) -> dict[str, str]:
        return {
            "x-api-key": self._cle,
            "anthropic-version": VERSION_API,
            "content-type": "application/json",
        }

    @staticmethod
    def _decouper(messages: Sequence[Message]) -> tuple[str, list[dict]]:
        """Separe la consigne systeme du dialogue.

        ⚠️ ANTHROPIC NE PREND PAS DE ROLE « system » DANS LA LISTE.

        Il attend un champ `system` a part. Envoyer un message de role
        `system` dans `messages` fait refuser la requete — et Nova construit
        precisement son prompt sous cette forme, depuis le premier jour. La
        conversion appartient donc ici, au seul endroit qui sait qu'Anthropic
        existe.
        """
        consignes = [m["content"] for m in messages if m.get("role") == "system"]
        dialogue = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]
        return "\n\n".join(consignes), dialogue

    def _corps(
        self,
        modele: Modele,
        messages: Sequence[Message],
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict:
        consigne, dialogue = self._decouper(messages)
        corps: dict = {
            "model": modele.nom,
            "messages": dialogue,
            # Obligatoire cote Anthropic, contrairement a OpenAI.
            "max_tokens": max_tokens or 1024,
        }
        if consigne:
            corps["system"] = consigne
        if temperature is not None:
            corps["temperature"] = temperature
        return corps

    def _exiger_la_clef(self) -> None:
        if not self.disponible():
            raise FournisseurIndisponible(
                "Claude n'est pas configure : il faut une clef "
                "(NOVA_ANTHROPIC_API_KEY) et un modele (NOVA_MODELE_CLOUD)."
            )

    def flux(
        self,
        modele: Modele,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        """Le texte, morceau par morceau, depuis les evenements SSE.

        `json_mode` est accepte et ignore : Anthropic n'a pas de decodage
        contraint equivalent. L'ignorer en silence serait un mensonge, on le
        journalise — un appelant qui EXIGE du JSON valide doit rester sur un
        moteur qui le garantit.
        """
        self._exiger_la_clef()
        if json_mode:
            log.info(
                "[Model Router] JSON contraint indisponible chez %s : "
                "la sortie n'est pas garantie valide.",
                self.id,
            )
        corps = self._corps(modele, messages, temperature, max_tokens) | {"stream": True}
        delais = httpx.Timeout(
            connect=CONNEXION_S, read=self._delai, write=30.0, pool=CONNEXION_S
        )
        from nova.llm.client import LLMError

        try:
            with httpx.Client(timeout=delais) as client:
                with client.stream(
                    "POST", f"{self._url}/messages", json=corps, headers=self._entetes()
                ) as reponse:
                    reponse.raise_for_status()
                    for ligne in reponse.iter_lines():
                        if not ligne or not ligne.startswith("data: "):
                            continue
                        try:
                            evenement = json.loads(ligne[6:])
                        except json.JSONDecodeError:
                            continue  # fragment malforme : on ignore, on ne casse pas
                        if evenement.get("type") != "content_block_delta":
                            continue
                        if morceau := evenement.get("delta", {}).get("text"):
                            yield morceau
        except httpx.HTTPError as erreur:
            raise LLMError(self._explique(erreur)) from erreur

    def generer(
        self,
        modele: Modele,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
    ) -> str:
        self._exiger_la_clef()
        from nova.llm.client import LLMError

        corps = self._corps(modele, messages, temperature, None)
        delais = httpx.Timeout(
            connect=CONNEXION_S, read=self._delai, write=30.0, pool=CONNEXION_S
        )
        try:
            with httpx.Client(timeout=delais) as client:
                reponse = client.post(
                    f"{self._url}/messages", json=corps, headers=self._entetes()
                )
                reponse.raise_for_status()
                blocs = reponse.json().get("content", [])
        except httpx.HTTPError as erreur:
            raise LLMError(self._explique(erreur)) from erreur
        return "".join(b.get("text", "") for b in blocs if b.get("type") == "text")

    def sante(self) -> bool:
        """Un appel minimal. Reserve au diagnostic — jamais dans une reponse."""
        if not self.disponible():
            return False
        try:
            with httpx.Client(timeout=httpx.Timeout(CONNEXION_S)) as client:
                reponse = client.get(f"{self._url}/models", headers=self._entetes())
                return reponse.status_code == 200
        except httpx.HTTPError:
            return False

    def _explique(self, erreur: httpx.HTTPError) -> str:
        """Un message qui dit QUOI FAIRE — et qui ne montre jamais la clef.

        Meme regle que `llm/client._explique` : « 401 Unauthorized » est exact
        et inutile. Et le corps d'une reponse d'erreur peut renvoyer ce qu'on
        lui a envoye : on ne le recopie pas.
        """
        if isinstance(erreur, httpx.HTTPStatusError):
            code = erreur.response.status_code
            if code == 401:
                return (
                    "Claude a refuse la clef (401). "
                    "Verifie NOVA_ANTHROPIC_API_KEY dans .env."
                )
            if code == 404:
                return (
                    f"le modele « {self._modele} » n'existe pas chez Anthropic. "
                    "Corrige NOVA_MODELE_CLOUD."
                )
            if code == 429:
                return "Claude a refuse : quota atteint (429)."
            return f"Claude a repondu {code}."
        if isinstance(erreur, httpx.ConnectError):
            return "impossible de joindre Claude — pas d'acces Internet ?"
        if isinstance(erreur, httpx.ReadTimeout):
            return "Claude n'a pas repondu a temps."
        return f"{type(erreur).__name__} en joignant Claude."
