"""Mesurer ce que la vision coute — sur TA machine, pas sur la mienne.

POURQUOI CE SCRIPT EXISTE

    « Ne prétends jamais qu'une optimisation améliore les performances
      sans la mesurer. »

La regle vaut aussi dans l'autre sens : je ne peux pas affirmer ce que la
vision RALENTIT sans l'avoir mesure. Je n'ai ni ton Mac, ni Ollama, ni modele
multimodal ici — aucun chiffre de ce projet ne doit sortir d'une estimation.

CE QU'IL MESURE, ET DANS CET ORDRE PRECIS

    1. le modele de langue AVANT     (reference)
    2. la vision A FROID              (chargement + calcul)
    3. la vision A CHAUD              (calcul seul)
    4. le modele de langue APRES      (ce que la question d'apres paiera)

⚠️ POURQUOI DEUX MESURES DE VISION PLUTOT QU'UNE.

La premiere version n'en faisait qu'une, et rendait « la vision met 45 s » :
un chiffre vrai et INEXPLOITABLE, parce qu'il additionne deux couts qui se
corrigent de facons opposees.

    le CHARGEMENT depuis le disque   ->  prendre un modele plus petit
    le CALCUL sur l'image            ->  envoyer une image plus petite

A chaud, le chargement est deja paye : la difference entre les deux mesures
EST le chargement. Sans cette soustraction, on choisit son remede a pile ou
face — et on peut passer une soiree a reduire des images alors que le temps
partait entierement dans la lecture d'un fichier de 3 Go.

⚠️ ET LA QUATRIEME MESURE RESTE CELLE QU'ON N'ATTEND PAS.

Sur 8 Go, charger un multimodal decharge le modele de langue. Ce cout ne
frappe pas l'appel de vision : il frappe la question SUIVANTE, celle qu'on
pose apres et qui n'a rien a voir. Le symptome ressemble a « Nova est
redevenue lente sans raison ».

DEUX REGLAGES ESSAYABLES SANS TOUCHER AU .env

    make vision IMAGE=photo.jpg
    COTE=672 make vision IMAGE=photo.jpg
    MODELE=moondream make vision IMAGE=photo.jpg
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Une question courte et factuelle : on mesure le CHARGEMENT du modele, pas
# sa capacite a disserter. Plus la reponse est breve, plus le forfait de
# rechargement ressort net dans la mesure.
QUESTION = "En une phrase : quelle est la capitale de la France ?"


def _chrono(faire) -> tuple[float, str]:
    debut = time.perf_counter()
    try:
        resultat = faire()
    except Exception as erreur:  # noqa: BLE001
        return (time.perf_counter() - debut) * 1000, f"ECHEC : {erreur}"
    return (time.perf_counter() - debut) * 1000, str(resultat)


def _langue() -> tuple[float, str]:
    from nova.llm.client import LLMClient

    return _chrono(lambda: LLMClient().chat([{"role": "user", "content": QUESTION}]))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        print("Donne le chemin d'une image :  uv run python scripts/bench_vision.py photo.jpg")
        return 2

    from nova.settings import get_settings
    from nova.vision.moteur import disponible

    reglages = get_settings()
    utilisable, raison = disponible()
    if not utilisable:
        print(f"⚠️  {raison}\n")
        print("Ce banc mesure justement ce que ca coute. Active la vision, puis relance.")
        return 1

    image = Path(argv[1]).expanduser().resolve()
    if not image.is_file():
        print(f"⚠️  « {image} » n'existe pas.")
        return 1

    # ⚠️ DEUX REGLAGES ESSAYABLES SANS TOUCHER AU `.env`.
    #
    # Chercher le bon cote d'image demande trois ou quatre essais. Les faire
    # en editant `.env` a chaque fois, c'est trois occasions d'oublier de
    # remettre la valeur — et de conclure sur une mesure faite avec un
    # reglage qu'on croit avoir change.
    modele = os.environ.get("MODELE") or reglages.vision_modele
    cote = int(os.environ.get("COTE") or reglages.vision_cote_max)

    print("═" * 70)
    print(f"  modele de langue : {reglages.chat_model}")
    print(f"  modele de vision : {modele}")
    print(f"  cote de l'image  : {cote} px")
    print(f"  image            : {image.name} ({image.stat().st_size // 1000} ko)")
    print("═" * 70)

    # 1. La reference. Deux appels : le premier peut payer un chargement, le
    #    second mesure le regime etabli. Prendre le premier ferait passer un
    #    chargement pour la vitesse normale du modele.
    _langue()
    avant, _ = _langue()
    print(f"\n1. langue AVANT           {avant:8.0f} ms   (modele deja chaud)")

    # 2. La vision, A FROID — le modele n'est pas en memoire, `_langue()`
    #    vient de prendre la place.
    from nova.core import chrono
    from nova.vision.moteur import MoteurOllama

    regarder = MoteurOllama(image.parent, modele=modele, cote_max=cote)
    chrono.vider()
    froid, sortie = _chrono(lambda: regarder.decrire(image.name).description)
    print(f"2. vision A FROID         {froid:8.0f} ms")
    for nom, stat in sorted(chrono.releve().items()):
        print(f"     {nom:<26} {stat['median']:8.0f} ms")
    print(f"\n   « {sortie[:200]} »")

    # 3. LA MEME CHOSE, A CHAUD.
    #
    # ⚠️ C'EST CETTE LIGNE QUI DIT QUOI CORRIGER.
    #
    # Sans elle, le releve donne « la vision met 45 s » — un chiffre vrai et
    # inexploitable, parce qu'il additionne deux couts qui se corrigent de
    # facons opposees :
    #
    #     le CHARGEMENT depuis le disque   -> prendre un modele plus petit
    #     le CALCUL sur l'image            -> envoyer une image plus petite
    #
    # A chaud, le chargement est deja paye. La difference entre les deux
    # mesures EST le chargement. Sans cette soustraction, on choisit son
    # remede a pile ou face.
    chrono.vider()
    chaud, _ = _chrono(lambda: regarder.decrire(image.name).description)
    print(f"3. vision A CHAUD         {chaud:8.0f} ms   (modele deja en memoire)")

    # 4. Le cout inflige a la question d'apres.
    apres, _ = _langue()
    print(f"4. langue APRES           {apres:8.0f} ms")

    chargement = max(froid - chaud, 0)
    surcout = apres - avant

    print("\n" + "═" * 70)
    print("  OU PARTENT LES SECONDES")
    print(f"    chargement du multimodal   {chargement / 1000:6.1f} s")
    print(f"    calcul sur l'image         {chaud / 1000:6.1f} s")
    print(f"    rechargement de la langue  {surcout / 1000:6.1f} s   (paye a la question d'apres)")
    print()

    # Le remede depend de QUI domine. On ne conseille que ce que la mesure
    # designe — un conseil donne dans les deux cas n'est pas un conseil.
    if chargement > chaud:
        print("  ⚠️  C'EST LE CHARGEMENT QUI DOMINE.")
        print("      Le modele est trop gros pour rester en memoire a cote de la")
        print("      langue : il est recharge depuis le disque a chaque fois.")
        print("      Reduire l'image n'y changera presque rien.")
        print("\n      A essayer, puis a REMESURER avec ce meme banc :")
        print("        NOVA_VISION_MODELE=moondream        (~1,7 Go au lieu de 3,2)")
        print("        fermer les navigateurs              (mesure : 3,6 Go recuperes)")
    else:
        print("  ⚠️  C'EST LE CALCUL SUR L'IMAGE QUI DOMINE.")
        print("      Le modele est charge, c'est le nombre de pixels qu'il doit")
        print("      regarder qui coute. Ce nombre grandit avec la SURFACE :")
        print("      diviser le cote par deux divise le travail par quatre.")
        print("\n      A essayer, puis a REMESURER avec ce meme banc :")
        print(f"        COTE=672 make vision IMAGE={image}")
        print(f"        COTE=448 make vision IMAGE={image}")
        print("      Puis garde le plus petit cote qui decrit encore correctement :")
        print("        NOVA_VISION_COTE_MAX=672  dans .env")

    if surcout > 3000:
        print()
        print(
            f"  Et quoi qu'il arrive, la question SUIVANTE coute "
            f"{surcout / 1000:.1f} s de plus :"
        )
        print("  la langue a ete dechargee pour faire place au multimodal. Ce cout")
        print("  ne frappe pas la vision, il frappe ce qu'on demande apres — il")
        print("  ressemble donc a un ralentissement sans cause.")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
