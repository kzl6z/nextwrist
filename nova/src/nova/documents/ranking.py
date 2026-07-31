"""Fusion de classements (RRF) — module volontairement isole.

Ce fichier n'importe RIEN : ni base, ni reseau, ni configuration.

C'est intentionnel, et la raison merite d'etre retenue : une fonction "pure"
placee dans un module qui importe la base de donnees n'est plus testable sans
base de donnees. La purete d'une fonction se perd au niveau du MODULE, pas de
la fonction. Isoler le calcul le rend testable en quelques millisecondes.

C'est la meme regle que la regle de dependance generale, appliquee en petit.
"""

from __future__ import annotations

from collections.abc import Sequence

# Constante usuelle de la litterature. Elle amortit le poids des tout premiers
# rangs : sans elle, le premier resultat d'un moteur ecraserait tout le reste.
RRF_K = 60


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> dict[int, float]:
    """Fusionne plusieurs classements d'identifiants en un score unique.

        score(element) = somme sur chaque moteur de  1 / (k + rang)

    Propriete recherchee : un element bien classe par PLUSIEURS moteurs passe
    devant un element premier d'un seul. On privilegie le consensus, ce qui est
    exactement ce qu'on veut quand on combine "sens" et "mots exacts".

    Aucun parametre a regler, et regulierement meilleur que des ponderations
    ajustees a la main.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores
