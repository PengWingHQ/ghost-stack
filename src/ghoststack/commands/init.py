"""Init command - Initialize GhostStack in a repository."""

from pathlib import Path

import typer

from ghoststack.core.config import ConfigManager, GhostStackConfig
from ghoststack.core.git import Git, GitError
from ghoststack.utils.output import print_error, print_info, print_success


def init_command(
    path: Path = typer.Argument(
        Path("."),
        help="Path to the Git repository",
    ),
    base_branch: str = typer.Option(
        "main",
        "--base",
        "-b",
        help="Default base branch for stacking",
    ),
) -> None:
    """Initialize GhostStack in a Git repository.

    This creates a .ghoststack/ directory with configuration files.
    """
    repo_path = path.resolve()

    # Check if this is a Git repository
    git = Git(repo_path)
    try:
        if not git.is_repo():
            print_error("Not a Git repository", {"path": str(repo_path)})
            raise typer.Exit(1)
    except GitError as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Check if already initialized
    config_manager = ConfigManager(repo_path)
    if config_manager.is_initialized():
        print_info("GhostStack is already initialized")
        raise typer.Exit(0)

    # Create config
    config = GhostStackConfig(default_base=base_branch)
    config_manager.initialize(config)

    # Add .ghoststack to .gitignore if not already there
    gitignore_path = repo_path / ".gitignore"
    ghoststack_entry = ".ghoststack/"

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if ghoststack_entry not in content:
            with open(gitignore_path, "a") as f:
                if not content.endswith("\n"):
                    f.write("\n")
                f.write(f"\n# GhostStack local data\n{ghoststack_entry}\n")
    else:
        gitignore_path.write_text(f"# GhostStack local data\n{ghoststack_entry}\n")

    print_success(
        "GhostStack initialized",
        {
            "path": str(repo_path),
            "base_branch": base_branch,
            "config": str(config_manager.config_file),
        },
    )
