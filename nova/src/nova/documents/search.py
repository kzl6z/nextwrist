"""Recherche dans la base documentaire — hybride.

Pourquoi hybride et pas seulement vectoriel :

  - la recherche VECTORIELLE comprend le sens ("financer" trouve "budget"),
    mais elle echoue sur les termes rares : un nom propre, une reference
    produit, un identifiant. Ces mots-la n'ont pas de voisinage semantique.
  - la recherche PLEIN TEXTE trouve exactement ces termes, mais rate toute
    reformulation.

On lance donc les deux et on fusionne par RRF (Reciprocal Rank Fusion) :

    score(document) = somme sur chaque moteur de  1 / (k + rang)

Simple, sans parametre a regler, et regulierement meilleur que des ponderations
savantes. C'est le genre de decision a prendre MAINTENANT : la rattraper plus
tard imposerait de tout re-vectoriser.
"""

from __future__ import annotations

from nova.db import connection
from nova.documents.ranking import reciprocal_rank_fusion
from nova.llm.embeddings import embed_one
from nova.logging_setup import get_logger
from nova.memory.models import SearchHit
from nova.settings import get_tuning

log = get_logger(__name__)


def _vector_ranking(conn, query: str, limit: int) -> tuple[list[int], dict[int, float]]:
    """Classement par proximite semantique, ET la distance de chacun.

    ⚠️ LA DISTANCE ETAIT CALCULEE PUIS JETEE.

    `<=>` est la distance cosinus de pgvector : 0 = identique, 1 = sans
    rapport. On ne selectionnait que l'`id`, donc on perdait la seule mesure
    ABSOLUE de pertinence du systeme.

    Sans elle, une recherche rend toujours ses plus proches voisins — et
    « le plus proche » ne veut pas dire « proche ». Releve en conditions
    reelles, sur la question « qu'est-ce que la relativite », qui n'a aucun
    rapport avec les documents personnels :

        Prompt systeme : contrat 1337 + memoire 260 + instant 184
                         + documents 1562
        prompt 3376 car. -> premier mot 5,1 s

    46 % du prompt, et environ deux secondes d'attente a chaque question,
    pour des extraits sans rapport. Le score de fusion (RRF) ne pouvait pas
    le detecter : il mesure un RANG. Le premier reste premier, meme quand il
    est le moins mauvais d'un lot sans interet.
    """
    vector = embed_one(query)
    rows = conn.execute(
        """
        SELECT id, embedding <=> %s::vector AS distance
        FROM chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (str(vector), str(vector), limit),
    ).fetchall()
    return [r["id"] for r in rows], {r["id"]: float(r["distance"]) for r in rows}


def _fulltext_ranking(conn, query: str, limit: int) -> list[int]:
    """Classement par correspondance de mots (index GIN, configuration francaise)."""
    rows = conn.execute(
        """
        SELECT id
        FROM chunks
        WHERE tsv @@ plainto_tsquery('french', %s)
        ORDER BY ts_rank(tsv, plainto_tsquery('french', %s)) DESC
        LIMIT %s
        """,
        (query, query, limit),
    ).fetchall()
    return [r["id"] for r in rows]


def search(query: str, limit: int | None = None) -> list[SearchHit]:
    """Retourne les meilleurs extraits pour une question."""
    tuning = get_tuning()
    limit = limit or tuning.extraits_max
    candidates = tuning.candidats_par_moteur

    with connection() as conn:
        # Corpus vide : inutile d'appeler le modele d'embeddings. Sans ce
        # garde-fou, la toute premiere question chargeait bge-m3 (1,2 Go) en
        # memoire pour chercher dans zero document — plusieurs dizaines de
        # secondes d'attente, en concurrence avec le modele de conversation.
        if conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is None:
            return []

        par_vecteur, distances = _vector_ranking(conn, query, candidates)
        par_mots = _fulltext_ranking(conn, query, candidates)
        scores = reciprocal_rank_fusion([par_vecteur, par_mots])
        if not scores:
            return []

        # ── LE PLUS PROCHE N'EST PAS FORCEMENT PROCHE ─────────────────────
        #
        # Une recherche vectorielle rend TOUJOURS ses k plus proches
        # voisins. Sur une question sans rapport avec le corpus, elle rend
        # donc les moins mauvais — avec le meme rang, et le meme score de
        # fusion, que sur une question parfaitement couverte.
        #
        # La distance cosinus, elle, est absolue : on peut lui opposer un
        # seuil. Au-dela, on n'injecte RIEN, et le prompt retrouve un tiers
        # de sa taille sur toutes les questions de culture generale.
        #
        # Un extrait trouve par les MOTS est garde sans condition : si la
        # question contient litteralement les mots du document, la
        # pertinence est etablie par construction, pas estimee.
        mots_exacts = set(par_mots)
        seuil = get_tuning().distance_max
        retenus = [
            cid for cid in scores
            if cid in mots_exacts or distances.get(cid, 2.0) <= seuil
        ]
        if not retenus:
            if distances:
                log.info(
                    "Aucun extrait pertinent (plus proche : distance %.2f > seuil %.2f) — "
                    "prompt allege d'autant.",
                    min(distances.values()), seuil,
                )
            return []

        best = sorted(retenus, key=lambda cid: scores[cid], reverse=True)[:limit]

        # Un seul aller-retour pour recuperer le detail des morceaux retenus.
        rows = conn.execute(
            """
            SELECT c.id, c.heading, c.content, d.title, d.source_path
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ANY(%s)
            """,
            (best,),
        ).fetchall()

    by_id = {r["id"]: r for r in rows}
    return [
        SearchHit(
            chunk_id=cid,
            document_title=by_id[cid]["title"],
            document_path=by_id[cid]["source_path"],
            heading=by_id[cid]["heading"],
            content=by_id[cid]["content"],
            score=scores[cid],
        )
        for cid in best
        if cid in by_id
    ]
