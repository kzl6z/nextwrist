"""Acces a PostgreSQL.

Choix assume : pas d'ORM. On ecrit du SQL.
  - la requete EST le sujet (recherche vectorielle, fusion de classements) ;
  - un ORM la cacherait ;
  - SQL est une competence qui se transfere et qui dure.

Regle de securite absolue : jamais de requete construite par concatenation.
Toujours des parametres `%s` — c'est la protection contre l'injection SQL.
"""

from __future__ import annotations

import atexit
from collections.abc import Iterator
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)
_pool: ConnectionPool | None = None


def _configure(conn: Connection) -> None:
    """Appele a l'ouverture de chaque connexion du pool.

    `register_vector` apprend a psycopg a convertir les listes Python en type
    `vector` de Postgres, et inversement. Sans lui, aucune requete vectorielle
    ne fonctionne.
    """
    register_vector(conn)
    conn.row_factory = dict_row  # les resultats arrivent en dictionnaires


def get_pool() -> ConnectionPool:
    """Pool de connexions, cree paresseusement.

    Un pool evite de rouvrir une connexion a chaque requete (couteux) tout en
    limitant le nombre de connexions simultanees vers Postgres.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=8,
            configure=_configure,
            open=True,
        )
    return _pool


def _close_pool() -> None:
    """Ferme le pool proprement AVANT la finalisation de l'interpreteur.

    Sans ceci, sur Python 3.13+, chaque commande se termine par :
        PythonFinalizationError: cannot join thread at interpreter shutdown

    Explication : le pool possede des threads de fond. Quand Python s'arrete,
    il appelle le ramasse-miettes sur le pool, qui essaie de joindre ses
    threads — mais Python interdit desormais de joindre un thread pendant la
    finalisation. `atexit` s'execute AVANT cette phase : on ferme donc a temps.

    L'erreur etait bruyante mais inoffensive. On la supprime quand meme : des
    traces d'erreur sans consequence apprennent a ignorer les traces d'erreur.
    """
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:  # noqa: BLE001
            pass
        _pool = None


atexit.register(_close_pool)


@contextmanager
def connection() -> Iterator[Connection]:
    """Connexion empruntee au pool, rendue automatiquement.

    Usage :
        with connection() as conn:
            rows = conn.execute("SELECT ...", (param,)).fetchall()

    La transaction est validee a la sortie du bloc, annulee si une exception
    remonte. C'est psycopg qui s'en charge.
    """
    with get_pool().connection() as conn:
        yield conn


def run_migrations() -> list[str]:
    """Applique les migrations SQL non encore appliquees, dans l'ordre.

    Principe volontairement rudimentaire — et c'est le bon choix : un outil de
    migration complet (Alembic) apporterait 90 % de fonctionnalites inutiles ici.
    Une table de suivi + des fichiers numerotes suffisent.

    REGLE : un fichier deja applique ne doit JAMAIS etre modifie. On en ajoute
    un nouveau. Sinon les environnements divergent silencieusement.
    """
    settings = get_settings()
    files = sorted(settings.migrations_dir.glob("*.sql"))
    applied: list[str] = []

    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}

        for path in files:
            if path.name in done:
                continue
            log.info("Migration %s", path.name)
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            applied.append(path.name)

    return applied
