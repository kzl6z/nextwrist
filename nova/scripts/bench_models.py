"""Mesure la latence reelle de plusieurs modeles, sur TA machine.

Pourquoi cet outil existe : j'ai recommande qwen3:4b sur des caracteristiques
generales, et il s'est revele inutilisable ici — non pas par manque de puissance,
mais parce qu'il produit une longue phase de raisonnement avant chaque reponse.
Aucune fiche technique ne dit ca. Seule la mesure le dit.

    uv run python scripts/bench_models.py
    uv run python scripts/bench_models.py qwen3:1.7b gemma3:4b

Ce qui est mesure :
  - premier mot : le temps AVANT que quoi que ce soit s'affiche. C'est ce que
    l'utilisateur percoit comme "ca rame", bien plus que la vitesse d'ecriture.
  - total : jusqu'au dernier mot.
  - raisonnement : le modele monologue-t-il avant de repondre ?

Les modeles absents en local sont ignores (installe-les avec `ollama pull`).
"""

from __future__ import annotations

import json
import sys
import time

import httpx
from rich.console import Console
from rich.table import Table

from nova.settings import get_settings

console = Console()

# Question courte et factuelle : on mesure la latence, pas la difficulte.
PROMPT = "Dis bonjour en une phrase."

CANDIDATS = [
    "qwen3:4b",
    "qwen3:1.7b",
    "gemma3:4b",
    "llama3.2:3b",
]


def modeles_locaux(base_url: str) -> set[str]:
    try:
        data = httpx.get(f"{base_url}/models", timeout=10).json()["data"]
        return {m["id"] for m in data}
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Moteur injoignable : {exc}[/]")
        raise SystemExit(1) from exc


def mesurer(base_url: str, modele: str) -> dict:
    payload = {
        "model": modele,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 200,
        "stream": True,
    }
    debut = time.monotonic()
    premier: float | None = None
    morceaux: list[str] = []

    with httpx.Client(timeout=300) as client:
        with client.stream("POST", f"{base_url}/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                if line[6:].strip() == "[DONE]":
                    break
                try:
                    delta = json.loads(line[6:])["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if content := delta.get("content"):
                    if premier is None:
                        premier = time.monotonic() - debut
                    morceaux.append(content)

    texte = "".join(morceaux)
    return {
        "modele": modele,
        "premier": premier or 0.0,
        "total": time.monotonic() - debut,
        "raisonne": "<think>" in texte or len(texte) > 400,
        "reponse": texte.strip().replace("\n", " ")[-60:],
    }


def main() -> None:
    base_url = get_settings().ollama_url.rstrip("/")
    demandes = sys.argv[1:] or CANDIDATS
    disponibles = modeles_locaux(base_url)

    table = Table(title=f"Latence sur cette machine — « {PROMPT} »")
    for colonne in ("Modele", "Premier mot", "Total", "Raisonne ?", "Fin de reponse"):
        table.add_column(colonne)

    for modele in demandes:
        if modele not in disponibles:
            table.add_row(modele, "[dim]absent[/]", "", "", "[dim]ollama pull " + modele + "[/]")
            continue
        console.print(f"[dim]mesure de {modele}…[/]")
        r = mesurer(base_url, modele)
        # Seuil de confort : au-dela de 5 s avant le premier mot, l'attente
        # devient penible et on cesse d'utiliser l'outil au quotidien.
        couleur = "green" if r["premier"] < 5 else "yellow" if r["premier"] < 15 else "red"
        table.add_row(
            r["modele"],
            f"[{couleur}]{r['premier']:.1f}s[/]",
            f"{r['total']:.1f}s",
            "[red]oui[/]" if r["raisonne"] else "[green]non[/]",
            r["reponse"],
        )

    console.print(table)
    console.print(
        "\n[dim]Choisis le premier modele en vert qui ne raisonne pas, "
        "puis mets-le dans .env (NOVA_CHAT_MODEL).[/]"
    )


if __name__ == "__main__":
    main()
