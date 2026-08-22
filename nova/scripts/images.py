"""Ce que Nova a deja regarde, et ce qu'il lui reste a voir.

POURQUOI CE SCRIPT EXISTE

L'indexation tourne en tache de fond, quand la machine se tait. C'est ce
qu'on veut — et c'est aussi une boite noire : on ne sait ni ou elle en est,
ni pourquoi une recherche ne trouve rien.

    make images                     ou en est le catalogue
    make images CHERCHE="casquette" ce que Nova trouverait
    make images FORCER=1            indexer maintenant, sans attendre

⚠️ `FORCER=1` CHARGE LE MODELE DE VISION TOUT DE SUITE.

Donc decharge celui de la langue. C'est acceptable ici parce que c'est
demande explicitement, en connaissance de cause — le fil de fond, lui,
attend deux minutes de silence.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime


def _age(horodatage: float) -> str:
    if not horodatage:
        return "—"
    return datetime.fromtimestamp(horodatage).strftime("%d/%m %H:%M")


def main(argv: list[str]) -> int:
    from nova.vision import catalogue as cat
    from nova.vision.images import dossiers_surveilles
    from nova.vision.moteur import disponible

    catalogue = cat.Catalogue(cat.fichier_par_defaut())
    dossiers = dossiers_surveilles()
    toutes = cat.a_indexer()
    restantes = [c for c in toutes if not catalogue.a_jour(c)]

    utilisable, raison = disponible()

    print("═" * 74)
    print("  DOSSIERS SURVEILLES")
    for dossier in dossiers:
        etat = "" if dossier.is_dir() else "   (n'existe pas)"
        print(f"    {dossier}{etat}")
    print()
    print(f"  images trouvees   {len(toutes)}")
    print(f"  deja regardees    {len(catalogue)}")
    print(f"  restantes         {len(restantes)}")
    print(f"  vision            {'active' if utilisable else raison.splitlines()[0]}")
    print("═" * 74)

    if requete := os.environ.get("CHERCHE", "").strip():
        print(f"\n  RECHERCHE « {requete} »\n")
        trouvees = catalogue.chercher(requete, limite=5)
        if not trouvees:
            print("    aucune correspondance.")
        for entree, score in trouvees:
            retenu = "✅" if score >= cat.SEUIL_PERTINENCE else "  "
            print(f"    {retenu} {int(score * 100):3d} %  {entree.nom}")
            print(f"           {entree.description[:100]}")
        print(
            f"\n    (seuil de pertinence : {int(cat.SEUIL_PERTINENCE * 100)} % — "
            "en dessous, Nova prefere ne rien proposer)"
        )
        return 0

    if os.environ.get("FORCER"):
        if not utilisable:
            print(f"\n⚠️  {raison}")
            return 1
        print(f"\n  Indexation d'un lot de {cat.LOT}… (charge le modele de vision)\n")
        from nova.vision.indexation import _un_passage

        ajoutees = _un_passage()  # noqa: SLF001 — c'est le sujet du script
        print(f"  {ajoutees} image(s) ajoutee(s).")
        if restantes:
            print(f"  Il en reste {max(len(restantes) - ajoutees, 0)}. Relance pour continuer.")
        return 0

    if catalogue.entrees():
        print("\n  LES DERNIERES REGARDEES\n")
        recentes = sorted(catalogue.entrees(), key=lambda e: -e.indexee_le)[:10]
        for entree in recentes:
            print(f"    {_age(entree.indexee_le)}  {entree.nom}")
            print(f"              {entree.description[:96]}")

    if restantes and utilisable:
        print(
            f"\n  {len(restantes)} image(s) pas encore regardee(s). Le fil de fond "
            f"s'en charge\n  quand la machine se tait, par lots de {cat.LOT}.\n"
            "  Pour ne pas attendre :  make images FORCER=1"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
