"""Journal des echanges.

Question legitime : l'interface garde deja l'historique, pourquoi le dupliquer ?

Parce que l'interface est jetable et que la memoire ne l'est pas. Toute
l'architecture repose sur ce principe : ce qui a de la valeur vit dans Nova
Core. Le jour ou tu changes d'interface, tu ne dois rien perdre.

C'est aussi cette table que lira la consolidation nocturne en V0.3 pour produire
les resumes et extraire les faits nouveaux.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from nova.db import connection


def get_or_create(external_id: str | None, title: str | None = None) -> int:
    """Retourne l'identifiant interne de la conversation, en la creant au besoin.

    `external_id` est fourni par l'interface. S'il est absent (appel CLI, script),
    on cree une conversation anonyme.
    """
    with connection() as conn:
        if external_id:
            row = conn.execute(
                "SELECT id FROM conversations WHERE external_id = %s", (external_id,)
            ).fetchone()
            if row:
                return row["id"]
        row = conn.execute(
            "INSERT INTO conversations (external_id, title) VALUES (%s, %s) RETURNING id",
            (external_id, title),
        ).fetchone()
        return row["id"]


def log_message(
    conversation_id: int,
    role: str,
    content: str,
    *,
    model: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Enregistre un message et rafraichit la date d'activite de la conversation.

    `meta` transporte ce qui n'est pas du texte : sources citees, duree, mode
    utilise. En JSONB, donc extensible sans migration — c'est exactement le cas
    ou le schema souple est le bon choix.
    """
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, model, meta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, role, content, model, Jsonb(meta or {})),
        )
        conn.execute(
            "UPDATE conversations SET last_message_at = now() WHERE id = %s",
            (conversation_id,),
        )


def derniers_echanges(
    conversation_id: int,
    *,
    budget_caracteres: int,
    tours_max: int = 8,
    apres: int | None = None,
) -> list[dict[str, str]]:
    """Les derniers messages de la conversation, prets a etre envoyes au modele.

    POURQUOI CETTE FONCTION N'EXISTAIT PAS, ET CE QUE CA COUTAIT

    Ce module savait ECRIRE et pas RELIRE. Chaque echange partait en base et
    n'en revenait jamais. Nova avait donc une memoire parfaite de ce qui
    s'etait dit, et aucun moyen de s'en servir :

        — « Parle-moi de Mars. »        Nova repond.
        — « Et on pourrait y vivre ? »  « y » ne renvoie a rien.

    Ce n'etait pas un manque d'intelligence du modele : on ne lui avait
    simplement pas donne la phrase precedente.

    LE BUDGET EST EN CARACTERES, PAS EN NOMBRE DE MESSAGES

    C'est le risque R13 du projet — « Nova ralentit a mesure qu'elle
    apprend ». Borner le NOMBRE de tours ne borne pas leur TAILLE : huit
    reponses longues pesent plus qu'un document entier, et chaque caractere
    du prompt se paie sur CHAQUE question suivante.

    On remonte donc du plus recent vers le plus ancien, et on s'arrete des
    que le budget est atteint. Le present est toujours servi avant le passe.

    `tours_max` est un second garde-fou, contre une conversation faite de
    milliers de messages minuscules que le budget seul laisserait passer.

    `apres` BORNE LE PASSE PAR LE BAS, ET C'EST CE QUE LE RESUME UTILISE

    Quand un resume couvre deja les messages jusqu'a l'identifiant N, les
    relire bruts les ferait figurer DEUX FOIS dans le prompt : une fois
    resumes, une fois mot pour mot. Un modele qui lit deux versions du meme
    passe n'a aucun moyen de savoir qu'il s'agit du meme.
    """
    borne = "AND id > %s" if apres is not None else ""
    parametres: tuple = (
        (conversation_id, apres, tours_max * 2)
        if apres is not None
        else (conversation_id, tours_max * 2)
    )
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT role, content
            FROM messages
            WHERE conversation_id = %s AND role IN ('user', 'assistant')
              {borne}
            ORDER BY id DESC
            LIMIT %s
            """,  # noqa: S608 — `borne` est une constante du module, jamais une entree
            parametres,
        ).fetchall()

    retenus: list[dict[str, str]] = []
    total = 0
    for row in rows:                     # du plus recent au plus ancien
        contenu = (row["content"] or "").strip()
        if not contenu:
            continue
        if total + len(contenu) > budget_caracteres and retenus:
            break
        retenus.append({"role": row["role"], "content": contenu})
        total += len(contenu)

    retenus.reverse()                    # le modele lit dans l'ordre du temps
    return retenus
