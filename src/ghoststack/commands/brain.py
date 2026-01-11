"""Brain commands - Manage the code index."""

from pathlib import Path
from typing import Annotated

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ghoststack.core.config import ConfigManager
from ghoststack.core.git import Git
from ghoststack.utils.output import (
    is_json_mode,
    print_error,
    print_info,
    print_json,
    print_success,
)

app = typer.Typer(help="Manage the code intelligence index")


def _require_init() -> ConfigManager:
    """Ensure GhostStack is initialized."""
    config_manager = ConfigManager()
    if not config_manager.is_initialized():
        print_error("GhostStack not initialized. Run 'gs init' first.")
        raise typer.Exit(1)
    return config_manager


@app.command("index")
def index_command(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Re-index all files even if unchanged")
    ] = False,
) -> None:
    """Index all code files in the repository.

    This scans the repository for source files and creates embeddings
    for semantic search. Only changed files are re-indexed unless --force.

    Example:
        gs brain index         # Index changed files
        gs brain index --force # Re-index everything
    """
    from ghoststack.brain import CodeIndex, FileIngestor

    config_manager = _require_init()

    git = Git()
    if not git.is_repo():
        print_error("Not a Git repository")
        raise typer.Exit(1)

    # Initialize the index
    chroma_path = config_manager.ghoststack_dir / "chroma"
    index = CodeIndex(chroma_path)
    ingestor = FileIngestor(Path.cwd(), index)

    print_info("Scanning repository for code files...")

    if is_json_mode():
        # Simple progress for JSON mode
        stats = ingestor.index_all(force=force)
        print_json({
            "status": "success",
            "files_scanned": stats["files_scanned"],
            "files_indexed": stats["files_indexed"],
            "chunks_total": stats["chunks_total"],
        })
    else:
        # Rich progress for terminal
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Indexing...", total=None)

            def update_progress(file_path: str, current: int, total: int):
                progress.update(
                    task,
                    description=f"[{current}/{total}] {file_path[:50]}",
                )

            stats = ingestor.index_all(
                force=force,
                progress_callback=update_progress,
            )

        print_success(
            "Indexing complete",
            {
                "files_scanned": stats["files_scanned"],
                "files_indexed": stats["files_indexed"],
                "chunks": stats["chunks_total"],
            },
        )


@app.command("status")
def status_command() -> None:
    """Show the status of the code index.

    Displays:
    - Whether the index exists
    - Number of indexed documents
    - Index location
    """
    from ghoststack.brain import CodeIndex

    config_manager = _require_init()

    chroma_path = config_manager.ghoststack_dir / "chroma"
    exists = chroma_path.exists()

    if not exists:
        if is_json_mode():
            print_json({
                "initialized": False,
                "count": 0,
                "path": str(chroma_path),
            })
        else:
            print_info("Code index not initialized")
            print_info("Run 'gs brain index' to create it")
        return

    try:
        index = CodeIndex(chroma_path)
        count = index.count
    except Exception as e:
        print_error(f"Could not read index: {e}")
        raise typer.Exit(1)

    if is_json_mode():
        print_json({
            "initialized": True,
            "count": count,
            "path": str(chroma_path),
        })
    else:
        print_success(
            "Code index active",
            {
                "documents": count,
                "path": str(chroma_path),
            },
        )


@app.command("clear")
def clear_command(
    confirm: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation")
    ] = False,
) -> None:
    """Clear all indexed documents.

    This removes all embeddings from the index. You'll need to
    run 'gs brain index' again to rebuild it.
    """
    from ghoststack.brain import CodeIndex

    config_manager = _require_init()
    chroma_path = config_manager.ghoststack_dir / "chroma"

    if not chroma_path.exists():
        print_info("Index does not exist")
        return

    if not confirm:
        confirm = typer.confirm("Clear all indexed documents?")
        if not confirm:
            print_info("Cancelled")
            return

    index = CodeIndex(chroma_path)
    index.clear()

    print_success("Index cleared")
