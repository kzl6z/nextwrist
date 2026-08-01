"""Mesure la latence reelle de plusieurs modeles, sur TA machine.

Pourquoi cet outil existe : j'ai recommande qwen3:4b sur des caracteristiques
generales, et il s'est revele inutilisable ici — non pas par manque de puissance,
mais parce qu'il produit une longue phase de raisonnement avant chaque reponse.
Aucune fiche technique ne dit ca. Seule la mesure le dit.

    uv run python scripts/bench_models.py
    uv run python scripts/bench_models.py llama3.2:1b qwen2.5:1.5b

CE QUI EST MESURE, ET POURQUOI C'EST SEPARE

Le temps avant une reponse se compose de trois choses sans rapport entre elles,
qui se corrigent de trois facons differentes :

  1. CHARGEMENT — lire le modele depuis le disque. Ne se paie que s'il avait
     ete decharge. Depend de sa taille ET de la memoire libre. Mesure sur
     l'iMac M1 : 21 s pour llama3.2:3b, soit dix fois ce qu'un SSD devrait
     mettre — signe que la machine manquait de memoire, pas que le modele
     etait gros.
  2. LECTURE — comprendre la question et le contexte. Proportionnel a la
     taille du prompt.
  3. ECRITURE — produire la reponse. Proportionnel a sa longueur.

Les confondre fait corriger la mauvaise chose. Cette session en a fait la
demonstration : deux tours passes a raccourcir le prompt alors que le temps
partait dans le chargement.

Pour les separer, on decharge volontairement le modele, on mesure a froid,
puis on remesure a chaud. La difference EST le chargement.

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

# Contexte artificiel, de la taille de celui que Nova envoie reellement (~900
# caracteres), pour que la « lecture » mesuree ici corresponde a l'usage reel.
CONTEXTE = "Tu es l'assistant personnel d'Hugo. Tu es calme et direct. " * 15

CANDIDATS = [
    "llama3.2:3b",
    "llama3.2:1b",
    "qwen2.5:1.5b",
    "gemma3:1b",
    "qwen3:1.7b",
]

# Au-dela, l'attente devient penible et on cesse d'utiliser l'outil au
# quotidien. C'est ce seuil qui decide, pas le classement du modele.
CONFORT_S = 5.0

# En dessous, une reponse de deux phrases (~50 jetons) met plus de 3 secondes
# a s'ecrire. Au-dessus, la vitesse supplementaire ne s'entend plus : elle est
# masquee par la parole en flux, qui commence des la premiere phrase.
VITESSE_MIN = 15.0


def _racine_native(base_url: str) -> str:
    """L'API native d'Ollama, a cote du point d'entree OpenAI-compatible.

    Le dechargement et la taille des modeles n'existent que la : ce sont des
    notions propres a Ollama, absentes du standard OpenAI. Piege deja paye —
    `keep_alive` envoye sur /v1 est ignore en silence.
    """
    return base_url.removesuffix("/v1").rstrip("/")


def modeles_locaux(base_url: str) -> set[str]:
    try:
        data = httpx.get(f"{base_url}/models", timeout=10).json()["data"]
        return {m["id"] for m in data}
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Moteur injoignable : {exc}[/]")
        raise SystemExit(1) from exc


def tailles(base_url: str) -> dict[str, float]:
    """Taille sur disque, en Go. Sert a expliquer un chargement lent."""
    try:
        data = httpx.get(f"{_racine_native(base_url)}/api/tags", timeout=10).json()
        return {m["name"]: m.get("size", 0) / 1e9 for m in data.get("models", [])}
    except Exception:  # noqa: BLE001
        return {}


def decharger(base_url: str, modele: str) -> None:
    """Sort le modele de la memoire, pour pouvoir mesurer son chargement."""
    try:
        httpx.post(
            f"{_racine_native(base_url)}/api/generate",
            json={"model": modele, "keep_alive": 0},
            timeout=60,
        )
        time.sleep(1.0)  # laisse le systeme rendre la memoire
    except httpx.HTTPError as exc:
        console.print(f"[yellow]{modele} : dechargement impossible ({exc})[/]")


def mesurer(base_url: str, modele: str) -> dict:
    """Un aller-retour complet. Retourne les temps et la fin de la reponse."""
    payload = {
        "model": modele,
        "messages": [
            {"role": "system", "content": CONTEXTE},
            {"role": "user", "content": PROMPT},
        ],
        "max_tokens": 200,
        "stream": True,
    }
    debut = time.monotonic()
    premier: float | None = None
    morceaux: list[str] = []

    with httpx.Client(timeout=600) as client:
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
    total = time.monotonic() - debut
    ecriture = max(total - (premier or 0.0), 1e-6)
    return {
        "premier": premier or 0.0,
        # ~4 caracteres par jeton en francais : grossier, mais suffisant pour
        # distinguer 3 jetons/s de 15.
        "jetons_s": len(texte) / 4 / ecriture,
        "raisonne": "<think>" in texte or len(texte) > 400,
        "reponse": texte.strip().replace("\n", " ")[-40:],
    }


def evaluer(base_url: str, modele: str) -> dict:
    """Chargement, lecture et ecriture, separes."""
    decharger(base_url, modele)
    froid = mesurer(base_url, modele)   # chargement + lecture + 1er jeton
    chaud = mesurer(base_url, modele)   # lecture + 1er jeton seulement
    return {
        "modele": modele,
        "chargement": max(froid["premier"] - chaud["premier"], 0.0),
        "lecture": chaud["premier"],
        "jetons_s": chaud["jetons_s"],
        "raisonne": chaud["raisonne"] or froid["raisonne"],
        "reponse": chaud["reponse"],
    }


def main() -> None:
    base_url = get_settings().ollama_url.rstrip("/")
    demandes = sys.argv[1:] or CANDIDATS
    disponibles = modeles_locaux(base_url)
    poids = tailles(base_url)

    console.print(
        "[dim]Chaque modele est decharge puis mesure deux fois : la difference "
        "donne le temps de chargement.\nComptez une a deux minutes par modele.[/]\n"
    )

    table = Table(title="Ou passent les secondes, sur cette machine")
    for colonne in ("Modele", "Taille", "Chargement", "Lecture", "Ecriture", "Raisonne ?", "Reponse"):
        table.add_column(colonne)

    resultats = []
    for modele in demandes:
        if modele not in disponibles:
            table.add_row(modele, "", "[dim]absent[/]", "", "", "", f"[dim]ollama pull {modele}[/]")
            continue
        console.print(f"[dim]mesure de {modele}…[/]")
        r = evaluer(base_url, modele)
        resultats.append(r)
        c_lect = "green" if r["lecture"] < CONFORT_S else "yellow" if r["lecture"] < 15 else "red"
        c_char = "green" if r["chargement"] < 5 else "yellow" if r["chargement"] < 15 else "red"
        table.add_row(
            r["modele"],
            f"{poids.get(modele, 0):.1f} Go" if poids.get(modele) else "—",
            f"[{c_char}]{r['chargement']:.1f}s[/]",
            f"[{c_lect}]{r['lecture']:.1f}s[/]",
            f"{r['jetons_s']:.1f} j/s",
            "[red]oui[/]" if r["raisonne"] else "[green]non[/]",
            r["reponse"],
        )

    console.print(table)
    console.print(
        "\n[bold]Comment lire ce tableau[/]\n"
        "  [bold]Chargement[/] eleve -> le modele est trop gros pour la memoire LIBRE.\n"
        "                     Ferme des applications, ou prends un modele plus petit.\n"
        "  [bold]Lecture[/] elevee   -> prompt trop long, ou modele trop lourd.\n"
        "  [bold]Ecriture[/] faible  -> modele trop gros pour cette machine.\n"
        "  [bold]Raisonne = oui[/]   -> disqualifie pour le vocal, quel que soit le reste.\n"
    )

    # ── Le critere : le PLUS GROS qui soit assez rapide ─────────────────
    #
    # Recommander le plus rapide serait une erreur, et elle a failli etre
    # commise ici : qwen2.5:1.5b ecrit a 55 j/s contre 28,8 pour llama3.2:3b,
    # mais les deux repondent bien en dessous du seuil de confort. A ce
    # moment-la, la vitesse supplementaire ne s'entend plus — alors que le
    # milliard de parametres en moins, lui, s'entend a chaque reponse.
    #
    # « Je prefere une IA extraordinairement intelligente avec une interface
    # simple qu'une interface spectaculaire avec une IA mediocre. » On ne
    # troque donc de la capacite contre de la vitesse que sous le seuil.
    utilisables = [
        r for r in resultats
        if not r["raisonne"] and r["lecture"] < CONFORT_S and r["jetons_s"] >= VITESSE_MIN
    ]
    if utilisables:
        meilleur = max(utilisables, key=lambda r: (poids.get(r["modele"], 0), r["jetons_s"]))
        rapides = sorted(utilisables, key=lambda r: -r["jetons_s"])
        console.print(
            f"[green]Recommande : [bold]{meilleur['modele']}[/bold][/] — le plus CAPABLE "
            f"parmi ceux qui tiennent le rythme.\n"
            f"[dim]NOVA_CHAT_MODEL={meilleur['modele']} dans .env, puis relance make serve.[/]"
        )
        if rapides[0]["modele"] != meilleur["modele"]:
            console.print(
                f"[dim]({rapides[0]['modele']} ecrit plus vite "
                f"({rapides[0]['jetons_s']:.0f} contre {meilleur['jetons_s']:.0f} j/s), mais les "
                f"deux sont deja sous le seuil : la vitesse en plus ne s'entend pas, "
                f"les parametres en moins si.)[/]"
            )
    elif resultats:
        console.print(
            f"[yellow]Aucun modele ne repond sous {CONFORT_S:.0f} s.[/] "
            "Essaie plus petit :\n"
            "[dim]ollama pull llama3.2:1b && ollama pull qwen2.5:1.5b[/]"
        )


if __name__ == "__main__":
    main()
