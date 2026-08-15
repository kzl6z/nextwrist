"""Un seul endroit pour repondre a « pourquoi c'est lent ? ».

POURQUOI CE SCRIPT EXISTE

Chaque fois que la machine ralentissait, la reponse demandait de coller trois
ou quatre commandes shell inventees sur le moment. La derniere — un
classement des processus par RSS — totalisait 1,4 Go sur une machine de 8 Go
qui paginait : elle ne montrait pas ce qu'il fallait, et elle a coute un
aller-retour.

Un diagnostic qu'on doit reinventer a chaque fois n'est pas un diagnostic.

CE QU'IL REGARDE, ET DANS QUEL ORDRE

L'ordre n'est pas cosmetique : il va du plus decisif au plus anecdotique.

  1. la PAGINATION   si elle est la, rien d'autre ne compte
  2. ce que NOVA tient    la seule part qu'on change en une ligne
  3. les VOISINS          ce qui occupe la machine a cote
  4. les SERVICES         Ollama tourne-t-il, Docker tourne-t-il

Il ne juge pas et ne repare rien : il montre. C'est deliberé — sur une
machine de 8 Go, le compromis entre memoire et intelligence appartient a son
proprietaire.

    uv run python scripts/diagnostic.py        (ou : make diagnostic)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nova.core import plateforme  # noqa: E402
from nova.settings import get_settings  # noqa: E402


def titre(texte: str) -> None:
    print(f"\n\033[1m── {texte} ".ljust(72, "─") + "\033[0m")


def _sortie(commande: list[str]) -> str:
    try:
        return subprocess.run(
            commande, capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def nom_court(chemin: str) -> str:
    """Le nom sous lequel on reconnait un processus.

    ⚠️ LE PIEGE QUI M'A EU DANS LA PREMIERE VERSION.

    Couper au premier point rangeait « com.apple.WebKit.WebContent » sous
    « com » — c'est-a-dire que les onglets de Safari, souvent le premier
    poste de memoire d'une machine, disparaissaient sous un nom qui ne veut
    rien dire. Les identifiants en notation inversee se lisent par la FIN.
    """
    nom = chemin.split("/")[-1]
    if nom.count(".") >= 2 and nom.split(".")[0] in {"com", "org", "net", "io"}:
        return nom.split(".")[-1]
    return nom.removesuffix(".app")


def voisins(combien: int = 12) -> list[tuple[float, str]]:
    """Les processus les plus gourmands, regroupes par nom, en Go.

    `ps -o rss` sous-estime sur macOS — la memoire compressee et le partage
    entre processus n'y figurent pas — mais il donne le CLASSEMENT, qui est
    ce qu'on cherche.

    Le REGROUPEMENT est le point important : un navigateur eclate en vingt
    processus enfants n'apparait sinon nulle part, alors qu'il est souvent le
    premier poste. C'est exactement ce qui rendait ma premiere mesure
    inutilisable — elle totalisait 1,4 Go sur une machine qui paginait.
    """
    total: dict[str, float] = {}
    for ligne in _sortie(["ps", "-A", "-o", "rss=,comm="]).splitlines():
        morceaux = ligne.split(None, 1)
        if len(morceaux) != 2 or not morceaux[0].isdigit():
            continue
        nom = nom_court(morceaux[1])
        total[nom] = total.get(nom, 0.0) + int(morceaux[0]) / 2**20
    return sorted(((go, nom) for nom, go in total.items()), reverse=True)[:combien]


def ollama_resident() -> list[str] | None:
    """Ce qu'Ollama tient EN CE MOMENT, lu chez lui. `None` s'il est absent.

    ⚠️ POURQUOI CETTE MESURE VAUT MIEUX QUE MA TABLE DE POIDS.

    `POIDS_CONNUS` donne le poids du FICHIER — 2,00 Go pour llama3.2:3b.
    `ollama ps` donne ce qui est reellement resident, contexte compris, et
    l'ecart n'est pas un detail : il approche souvent le double.

    Autrement dit, tout ce que j'ai annonce a l'utilisateur sur l'empreinte
    de Nova etait une sous-estimation, et une sous-estimation systematique du
    poste le plus lourd. Une table de constantes ne remplace pas une lecture.

    La colonne PROCESSOR compte tout autant sur Apple Silicon : « 100% GPU »
    et « 100% CPU » ne se corrigent pas de la meme facon.
    """
    if not shutil.which("ollama"):
        return None
    lignes = [ligne for ligne in _sortie(["ollama", "ps"]).splitlines() if ligne.strip()]
    if len(lignes) <= 1:      # l'entete seule = rien de charge
        return []
    return lignes


def tourne(motif: str) -> bool:
    return bool(_sortie(["pgrep", "-f", motif]).strip())


def main() -> None:
    reglages = get_settings()
    machine = plateforme.detecter()

    titre("La machine")
    print(f"  {plateforme.resume()}")

    titre("Pagination — si elle est la, rien d'autre ne compte")
    pression = plateforme.pression_memoire()
    if not pression.disponible:
        print("  Mesure indisponible sur cette plateforme.")
    elif pression.pagine:
        print(f"  \033[31mLA MACHINE PAGINE\033[0m — {pression}")
        print("  Chaque page qui revient est une lecture disque. Tout ralentit :")
        print("  Nova, mais aussi tout ce que tu fais pendant qu'elle repond.")
    else:
        print(f"  \033[32mPas de pagination\033[0m — {pression}")

    titre("Ce que Nova tient")
    print(
        plateforme.empreinte_nova(
            reglages.chat_model, [reglages.whisper_model, reglages.whisper_wake_model]
        )
    )

    titre("Ce qu'Ollama tient VRAIMENT")
    charges = ollama_resident()
    if charges is None:
        print("  Commande `ollama` introuvable — impossible de verifier.")
    elif not charges:
        print("  Aucun modele charge en ce moment.")
        print("  (le premier mot d'une reponse paiera donc la lecture du disque)")
    else:
        for ligne in charges:
            print(f"  {ligne}")
        print("  ⚠️ Cette taille INCLUT le contexte, et depasse le poids du fichier.")
        print("  C'est elle qui compte pour la memoire, pas celle annoncee plus haut.")

    titre("Les voisins — ce qui occupe la machine a cote")
    liste = voisins()
    for go, nom in liste:
        barre = "█" * max(1, round(go * 12))
        print(f"  {go:5.2f} Go  {nom[:26]:<26} {barre}")
    if liste:
        print(f"  {sum(go for go, _ in liste):5.2f} Go  \033[1mtotal des ci-dessus\033[0m")
    print("  (ps sous-estime sur macOS ; c'est le CLASSEMENT qui compte, pas le total)")

    titre("Services")
    for nom, motif in (("Ollama", "ollama"), ("Docker Desktop", "Docker Desktop"),
                       ("Nova Core", "nova.api.app")):
        etat = "\033[32mtourne\033[0m" if tourne(motif) else "arrete"
        print(f"  {nom:<16} {etat}")

    titre("Ce que ca veut dire")
    if pression.pagine and machine.profil == "etroit":
        print("  Sur cette machine, la memoire est la contrainte, pas le processeur.")
        print("  Deux leviers, et le premier ne coute rien a l'intelligence de Nova :")
        print("    1. fermer ce qui ne sert pas pendant que Nova travaille")
        print("       (regarde le classement ci-dessus, pas tes impressions)")
        print("    2. un modele plus leger — voir « Ce que Nova tient »")
    elif pression.pagine:
        print("  La machine pagine alors qu'elle a de la memoire : quelque chose")
        print("  d'inhabituel la retient. Le classement ci-dessus dit quoi.")
    else:
        print("  Rien d'anormal de ce cote. Si Nova reste lente, le probleme est")
        print("  ailleurs : regarde le bloc [PERFORMANCE] dans la console de")
        print("  l'application, qui chronometre chaque etape.")
    print()


if __name__ == "__main__":
    os.environ.setdefault("NOVA_LOG_LEVEL", "WARNING")
    main()
