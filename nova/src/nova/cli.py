"""Interface en ligne de commande.

Pourquoi une CLI alors qu'il y a une interface web : parce qu'on peut tester
chaque couche isolement, sans lancer Docker ni ouvrir un navigateur. C'est
l'outil de debogage numero un du projet.

`typer` transforme une fonction Python annotee en commande. Zero configuration.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nova import orchestrator
from nova.db import run_migrations
from nova.documents import ingest as ingest_module
from nova.documents import search as search_module
from nova.llm.client import LLMClient
from nova.memory import facts as facts_module

console = Console()
app = typer.Typer(help="Nova — assistant personnel local", no_args_is_help=True)
db_app = typer.Typer(help="Base de donnees")
facts_app = typer.Typer(help="Memoire : les faits te concernant")
app.add_typer(db_app, name="db")
app.add_typer(facts_app, name="facts")


@db_app.command("migrate")
def db_migrate() -> None:
    """Applique les migrations SQL en attente."""
    applied = run_migrations()
    if applied:
        console.print(f"[green]Applique :[/] {', '.join(applied)}")
    else:
        console.print("[dim]Base deja a jour.[/]")


@facts_app.command("add")
def facts_add(
    content: str,
    category: str = typer.Option("profil", help=f"Une de : {', '.join(facts_module.CATEGORIES)}"),
) -> None:
    """Ajoute un fait confirme. Commence par une trentaine de faits sur toi."""
    if category not in facts_module.CATEGORIES:
        raise typer.BadParameter(f"Categorie inconnue. Attendu : {facts_module.CATEGORIES}")
    fact = facts_module.add(content, category=category)
    console.print(f"[green]Fait #{fact.id} enregistre.[/]")


@facts_app.command("list")
def facts_list(status: str = typer.Option(None, help="proposed | confirmed | archived")) -> None:
    """Affiche la memoire semantique."""
    rows = facts_module.list_facts(status=status)
    if not rows:
        console.print("[dim]Aucun fait. Commence par `nova facts add`.[/]")
        return
    table = Table(show_lines=False)
    for column in ("#", "Categorie", "Statut", "Origine", "Contenu"):
        table.add_column(column)
    for fact in rows:
        table.add_row(str(fact.id), fact.category, fact.status, fact.origin, fact.content)
    console.print(table)


@facts_app.command("confirm")
def facts_confirm(fact_id: int) -> None:
    """Valide un fait propose par Nova."""
    facts_module.confirm(fact_id)
    console.print(f"[green]Fait #{fact_id} confirme.[/]")


@app.command()
def ingest(path: Path) -> None:
    """Ingere un fichier ou un dossier (Markdown et texte)."""
    chunks, files = ingest_module.ingest_path(path)
    console.print(f"[green]{files} fichier(s), {chunks} morceau(x) indexe(s).[/]")


@app.command()
def search(query: str, limit: int = 6) -> None:
    """Cherche dans la base documentaire, sans passer par le modele.

    Tres utile pour diagnostiquer : si Nova repond mal, verifie D'ABORD ici que
    la recherche remonte les bons extraits. Cela separe le probleme de recherche
    du probleme de generation.
    """
    hits = search_module.search(query, limit=limit)
    if not hits:
        console.print("[dim]Aucun resultat.[/]")
        return
    for hit in hits:
        # `markup=False` est indispensable : rich interprete les crochets comme
        # des balises et ferait DISPARAITRE la citation `[document, "section"]`.
        # Bug trouve en executant reellement la commande — pas en la relisant.
        console.print()
        console.print(hit.citation(), style="bold", markup=False)
        console.print(f"score {hit.score:.4f}", style="dim")
        console.print(hit.content[:400].strip(), markup=False)


@app.command()
def ask(
    question: str,
    critique: bool = typer.Option(False, "--critique", help="Mode adversarial"),
) -> None:
    """Pose une question a Nova depuis le terminal."""
    console.print()
    for piece in orchestrator.answer_stream(
        [{"role": "user", "content": question}],
        mode="critique" if critique else "normal",
    ):
        # markup=False / highlight=False : Nova cite ses sources entre crochets,
        # et rich les effacerait. Meme piege que dans `search`.
        console.print(piece, end="", markup=False, highlight=False)
    console.print("\n")


@app.command()
def health() -> None:
    """Verifie que la base et le moteur d'inference repondent."""
    from nova.db import connection

    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        console.print("[green]Base de donnees : OK[/]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Base de donnees : {exc}[/]")
    ok = LLMClient().health()
    console.print(f"[{'green' if ok else 'red'}]Moteur d'inference : {'OK' if ok else 'KO'}[/]")


if __name__ == "__main__":
    app()
