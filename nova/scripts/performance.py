"""Le releve de performance de Nova, en un ecran.

    uv run python scripts/performance.py          (ou : make perf)
    uv run python scripts/performance.py --reset  remet les compteurs a zero

POURQUOI CET OUTIL, ALORS QUE LES JOURNAUX DISENT DEJA TOUT

Ils ne disent pas tout : ils disent chaque chose une fois. Retrouver « le
modele a mis combien de temps en general » dans quarante mille lignes de
journal demande de les lire, et personne ne les lit — on lit la derniere
ligne, celle du cas qu'on vient de vivre, qui est justement le moins
representatif.

Le releve montre la DISTRIBUTION. C'est ce qui distingue « Nova est lente »
de « Nova est rapide sauf une fois sur vingt », deux phrases qui n'ont pas le
meme remede.

⚠️ CE QU'IL FAUT AVOIR FAIT AVANT DE LE LANCER

Parler a Nova. Le releve lit ce que le chemin critique a note en passant :
sur une instance qui vient de demarrer, il est vide, et c'est normal. Poser
trois ou quatre questions suffit a le remplir.

COMMENT LIRE LES COLONNES

    mediane   le cas normal — ce que tu ressens la plupart du temps
    p95       le mauvais jour — ce qui te fait dire « c'est lent »
    max       le pire vu

L'ecart entre la mediane et le p95 est le diagnostic le plus utile de tout ce
tableau. Serres, c'est une lenteur structurelle : il faut changer quelque
chose au systeme. Ecartes, c'est une lenteur OCCASIONNELLE — un modele
decharge, un disque occupe, un voisin gourmand — et la reponse n'est pas la
meme du tout.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

#: Le port de `make serve`. Il vit dans le Makefile et non dans les reglages :
#: on le repete ici plutot que de faire croire a `get_settings()` qu'il le
#: connait. `NOVA_PORT` permet de le changer sans toucher au script.
PORT = int(os.environ.get("NOVA_PORT", "8100"))

#: Les etapes du chemin critique, dans l'ordre ou l'utilisateur les vit.
#: Les nommer ici sert a deux choses : les afficher dans le bon ordre, et
#: rendre visible celle qui MANQUE — une etape absente du releve n'a jamais
#: ete parcourue, ce qui est parfois la decouverte la plus interessante.
ORDRE = (
    "whisper — chargement",
    "whisper — decodage",
    "recherche documentaire",
    "rappel de l'historique",
    "construction du prompt",
    "modele — premier jeton",
    "modele — generation",
    "modele — total",
    "synthese — kokoro",
    "synthese — piper",
    "synthese — nettoyage des bords",
)


def _base() -> str:
    return f"http://127.0.0.1:{PORT}"


def _demander(chemin: str, methode: str = "GET") -> dict:
    requete = urllib.request.Request(f"{_base()}{chemin}", method=methode)
    with urllib.request.urlopen(requete, timeout=5) as reponse:
        brut = reponse.read()
    return json.loads(brut) if brut else {}


def _barre(valeur: float, maximum: float, largeur: int = 24) -> str:
    """Une barre proportionnelle. Un tableau de chiffres cache les rapports.

    Trois cents millisecondes a cote de huit mille, en colonnes, se lisent
    comme deux nombres. En barres, on voit tout de suite lequel est le sujet.
    """
    if maximum <= 0:
        return ""
    pleins = max(1, round(valeur / maximum * largeur)) if valeur > 0 else 0
    return "█" * pleins


def main() -> int:
    if "--reset" in sys.argv:
        try:
            _demander("/performance/reset", "POST")
        except urllib.error.HTTPError as exc:
            if exc.code != 204:
                raise
        print("✓ compteurs remis a zero — parle a Nova, puis relance ce script")
        return 0

    try:
        releve = _demander("/performance")
    except (urllib.error.URLError, OSError) as exc:
        print(f"✗ Nova Core injoignable sur {_base()} : {exc}")
        print("  Lance-la d'abord :  make serve")
        return 1

    etapes: dict[str, dict] = releve.get("etapes", {})
    machine = releve.get("machine", {})

    print("\n\033[1m── NOVA — PERFORMANCE ".ljust(80, "─") + "\033[0m")
    print(f"  {machine.get('resume', '?')}")
    print(f"  pagination : {machine.get('pagination', '?')}")
    print(f"  mesures accumulees depuis {releve.get('depuis_secondes', 0):.0f} s")

    if not etapes:
        print("\n  Aucune mesure.")
        print("  Le releve lit ce que les vraies requetes ont note en passant :")
        print("  parle a Nova (trois ou quatre questions), puis relance.")
        return 0

    plafond = max(s["median"] for s in etapes.values())

    print(f"\n  {'etape':<32} {'n':>4} {'mediane':>9} {'p95':>9} {'max':>9}")
    print("  " + "─" * 76)

    connues = [nom for nom in ORDRE if nom in etapes]
    autres = sorted(nom for nom in etapes if nom not in ORDRE)
    for nom in [*connues, *autres]:
        s = etapes[nom]
        print(
            f"  {nom:<32} {s['n']:>4} {s['median']:>8.0f}ms {s['p95']:>8.0f}ms "
            f"{s['max']:>8.0f}ms  {_barre(s['median'], plafond)}"
        )

    manquantes = [nom for nom in ORDRE if nom not in etapes]
    if manquantes:
        print("\n  Jamais parcourues (donc jamais mesurees) :")
        for nom in manquantes:
            print(f"    · {nom}")

    # ── La lecture qui compte ────────────────────────────────────────────
    #
    # On ne se contente pas d'afficher : on pointe les deux cas qui appellent
    # des remedes opposes. Un tableau qu'il faut savoir interpreter n'aide que
    # ceux qui savaient deja.
    print("\n\033[1m── CE QUE CA DIT ".ljust(80, "─") + "\033[0m")
    for nom in [*connues, *autres]:
        s = etapes[nom]
        if s["n"] < 3:
            continue
        if s["median"] > 0 and s["p95"] > s["median"] * 3:
            print(
                f"  ⚠ {nom} : mediane {s['median']:.0f} ms mais p95 "
                f"{s['p95']:.0f} ms — lenteur OCCASIONNELLE."
            )
            print("     Cherche un rechargement ou une concurrence, pas un calcul lent.")
        elif s["median"] > 1000:
            print(
                f"  ⚠ {nom} : {s['median']:.0f} ms de facon CONSTANTE — "
                "lenteur structurelle."
            )
            print("     C'est le systeme qu'il faut changer, pas les circonstances.")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
