"""Le raisonnement qui mangeait la reponse.

⚠️ CE FICHIER GARDE LA PANNE LA PLUS COUTEUSE A DIAGNOSTIQUER DE TOUTES.

Releve sur la machine reelle, au premier essai du modele `nova` :

    Modele nova : aucun mot produit en 39.0 s.
    Aucune reponse.

Trente-neuf secondes de travail parfaitement reel, et rien. Pas d'erreur, pas
d'avertissement, pas une ligne de journal pour dire ou c'etait parti.

CE QUI SE PASSAIT

La base Qwen 3.5 du modele raisonne avant de repondre, et `/no_think` — un
interrupteur de Qwen 3 — est purement ignore par elle. Mais le piege n'est pas
la : il est dans l'endroit ou Ollama RANGE ce raisonnement.

    "delta":{"content":"","reasoning":"The"}
    "delta":{"content":"","reasoning":" user"}

Un champ `reasoning` separe. `ThinkFilter` cherche des balises `<think>` dans
`content` — il ne pouvait donc RIEN voir : il n'y avait rien a filtrer, juste
un `content` vide de bout en bout. Les 500 jetons du plafond partaient
integralement dans un champ que personne ne lisait.

Toutes les couches se comportaient correctement, chacune de son cote. C'est le
pire mode de panne qui soit : celui ou tout le monde a l'air d'avoir bien fait
son travail, et ou il ne reste aucune prise.

DEUX CHOSES A GARDER, ET LA SECONDE COMPTE AUTANT

  1. l'interrupteur qui marche vraiment (`reasoning_effort`, verifie contre le
     vrai Ollama — `think: false` etait ignore sur ce point d'entree) ;
  2. le fait qu'un silence complet se DENONCE. Meme repare, ce chemin doit
     rester bruyant : le jour ou un autre modele trouve une autre facon de ne
     rien produire, personne ne devrait avoir a relire le flux brut pour
     l'apprendre.
"""

from __future__ import annotations

import json

import httpx
import pytest

from nova.llm.client import LLMClient, LLMError


def _flux(fragments: list[dict]) -> httpx.MockTransport:
    """Un faux Ollama qui rend les `delta` demandes, en SSE."""

    def repondre(requete: httpx.Request) -> httpx.Response:
        lignes = [f"data: {json.dumps({'choices': [{'delta': d}]})}" for d in fragments]
        lignes.append("data: [DONE]")
        return httpx.Response(200, text="\n\n".join(lignes) + "\n\n")

    return httpx.MockTransport(repondre)


def _client(monkeypatch, fragments: list[dict]) -> LLMClient:
    transport = _flux(fragments)
    origine = httpx.Client.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = transport
        origine(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    return LLMClient(base_url="http://faux/v1", model="nova")


def test_le_raisonnement_seul_ne_passe_plus_en_silence(monkeypatch):
    """Le cas reel : que du `reasoning`, jamais de `content`."""
    client = _client(monkeypatch, [
        {"role": "assistant", "content": "", "reasoning": "The"},
        {"content": "", "reasoning": " user"},
        {"content": "", "reasoning": " asks about black holes"},
    ])

    with pytest.raises(LLMError) as erreur:
        list(client.stream([{"role": "user", "content": "les trous noirs"}]))

    message = str(erreur.value)
    # On exige la CAUSE et le REMEDE, pas seulement le constat : c'est
    # precisement ce qui manquait le jour ou la panne est arrivee.
    assert "RAISONNEMENT" in message
    assert "aucune reponse" in message
    assert "NOVA_THINKING" in message


def test_une_vraie_reponse_traverse_intacte(monkeypatch):
    """Le garde-fou ne doit pas se declencher quand tout va bien."""
    client = _client(monkeypatch, [
        {"content": "Un trou noir", "reasoning": "hmm"},
        {"content": " est une region."},
    ])

    morceaux = list(client.stream([{"role": "user", "content": "?"}]))
    assert "".join(morceaux) == "Un trou noir est une region."


def test_reasoning_effort_est_envoye_quand_on_ne_veut_pas_raisonner(monkeypatch):
    """L'interrupteur qui marche — le seul des trois essayes sur /v1."""
    vu: dict = {}

    def repondre(requete: httpx.Request) -> httpx.Response:
        vu.update(json.loads(requete.content))
        corps = 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=corps)

    transport = httpx.MockTransport(repondre)
    origine = httpx.Client.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = transport
        origine(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    client = LLMClient(base_url="http://faux/v1", model="nova")
    list(client.stream([{"role": "user", "content": "?"}]))

    assert vu.get("reasoning_effort") == "none"
