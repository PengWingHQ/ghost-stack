"""GhostStack CLI - The Agent-First Stack Manager."""

from typing import Annotated

import typer

from ghoststack import __version__
from ghoststack.commands.init import init_command
from ghoststack.commands.stack import app as stack_app
from ghoststack.utils.output import set_json_mode

# Create main app
app = typer.Typer(
    name="gs",
    help="👻 GhostStack - The Agent-First Stack Manager",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print(f"GhostStack v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output in JSON format (for AI agents)",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = False,
) -> None:
    """GhostStack - The Agent-First Stack Manager.

    A local-first workflow engine for managing stacked PRs,
    designed for AI agents and "vibe coders" alike.

    Use --json flag for machine-readable output.
    """
    set_json_mode(json_output)


# Register commands
app.command("init")(init_command)
app.add_typer(stack_app, name="stack")


# Add status command for quick overview
@app.command("status")
def status() -> None:
    """Show current GhostStack status.

    Displays:
    - Whether GhostStack is initialized
    - Current branch and its position in the stack
    - Any uncommitted changes
    """
    from ghoststack.core.config import ConfigManager
    from ghoststack.core.git import Git
    from ghoststack.utils.output import print_error, print_info, print_json, is_json_mode

    config_manager = ConfigManager()
    git = Git()

    if not git.is_repo():
        print_error("Not a Git repository")
        raise typer.Exit(1)

    initialized = config_manager.is_initialized()
    current_branch = git.get_current_branch()
    is_dirty = git.is_dirty()

    status_data = {
        "initialized": initialized,
        "current_branch": current_branch,
        "dirty": is_dirty,
    }

    if initialized:
        stack = config_manager.load_stack()
        item = stack.get_item(current_branch) if current_branch else None
        status_data["in_stack"] = item is not None
        status_data["parent"] = item.parent if item else None
        status_data["base_branch"] = stack.base_branch
        status_data["stack_size"] = len(stack.items)

    if is_json_mode():
        print_json(status_data)
    else:
        if not initialized:
            print_info("GhostStack is not initialized. Run 'gs init' to get started.")
        else:
            print_info(f"Branch: {current_branch or 'detached HEAD'}")
            if is_dirty:
                print_info("Status: [yellow]dirty[/] (uncommitted changes)")
            else:
                print_info("Status: [green]clean[/]")

            item = stack.get_item(current_branch) if current_branch else None
            if item:
                print_info(f"Stack: {item.name} → {item.parent or stack.base_branch}")
            else:
                print_info("Stack: not in stack")


if __name__ == "__main__":
    app()
