"""Mesurer ce que la vision coute — sur TA machine, pas sur la mienne.

POURQUOI CE SCRIPT EXISTE

    « Ne prétends jamais qu'une optimisation améliore les performances
      sans la mesurer. »

La regle vaut aussi dans l'autre sens : je ne peux pas affirmer ce que la
vision RALENTIT sans l'avoir mesure. Je n'ai ni ton Mac, ni Ollama, ni modele
multimodal ici — aucun chiffre de ce projet ne doit sortir d'une estimation.

CE QU'IL MESURE, ET DANS CET ORDRE PRECIS

    1. le modele de langue AVANT     (reference)
    2. la vision                      (preparation de l'image + regard)
    3. le modele de langue APRES      ← LE CHIFFRE QUI COMPTE

⚠️ C'EST LA TROISIEME MESURE QUI DECIDE DE TOUT.

Sur 8 Go, charger un multimodal decharge le modele de langue. Le cout ne
frappe donc PAS l'appel de vision — il frappe la question suivante, celle
qu'on pose apres, et qui n'a rien a voir. Mesuree isolement, la vision peut
paraitre acceptable ; c'est la reponse d'apres qui paie le rechargement, et
le symptome ressemble a « Nova est redevenue lente sans raison ».

    uv run python scripts/bench_vision.py chemin/vers/photo.jpg
"""

from __future__ import annotations

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

    print("═" * 70)
    print(f"  modele de langue : {reglages.chat_model}")
    print(f"  modele de vision : {reglages.vision_modele}")
    print(f"  image            : {image.name} ({image.stat().st_size // 1000} ko)")
    print("═" * 70)

    # 1. La reference. Deux appels : le premier peut payer un chargement, le
    #    second mesure le regime etabli. Prendre le premier ferait passer un
    #    chargement pour la vitesse normale du modele.
    _langue()
    avant, _ = _langue()
    print(f"\n1. langue AVANT           {avant:8.0f} ms   (modele deja chaud)")

    # 2. La vision.
    from nova.core import chrono
    from nova.vision.moteur import MoteurOllama

    chrono.vider()
    duree, sortie = _chrono(lambda: MoteurOllama(image.parent).decrire(image.name).description)
    print(f"2. vision                 {duree:8.0f} ms")
    for nom, stat in sorted(chrono.releve().items()):
        print(f"     {nom:<26} {stat['median']:8.0f} ms")
    print(f"\n   « {sortie[:200]} »")

    # 3. Le chiffre qui compte.
    apres, _ = _langue()
    print(f"\n3. langue APRES           {apres:8.0f} ms")

    surcout = apres - avant
    print("\n" + "═" * 70)
    if surcout > 3000:
        print(f"  ⚠️  LA REPONSE SUIVANTE COUTE {surcout / 1000:.1f} s DE PLUS.")
        print("      Le modele de langue a ete decharge pour faire place au")
        print("      multimodal, et rechargé depuis le disque. Ce cout frappe la")
        print("      question d'apres, pas la vision : il ressemble donc a un")
        print("      ralentissement sans cause.")
        print("\n      Remedes, du moins couteux au plus :")
        print("        - un multimodal plus petit  (moondream, ~1,7 Go)")
        print("        - fermer les navigateurs    (mesure : 3,6 Go recuperes)")
        print("        - garder la vision eteinte hors des moments ou tu t'en sers")
    else:
        print(f"  Surcout sur la reponse suivante : {surcout:+.0f} ms — les deux")
        print("  modeles tiennent ensemble en memoire.")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
