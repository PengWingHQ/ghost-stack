"""Stack commands - Manage stacked branches."""

from typing import Annotated, Optional

import typer

from ghoststack.core.config import ConfigManager
from ghoststack.core.git import Git, GitError
from ghoststack.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
    print_stack_tree,
    print_warning,
    is_json_mode,
)

app = typer.Typer(help="Manage stacked branches")


def _require_init() -> tuple[ConfigManager, Git]:
    """Ensure GhostStack is initialized and return config manager and git."""
    config_manager = ConfigManager()
    if not config_manager.is_initialized():
        print_error("GhostStack not initialized. Run 'gs init' first.")
        raise typer.Exit(1)

    git = Git()
    if not git.is_repo():
        print_error("Not a Git repository")
        raise typer.Exit(1)

    return config_manager, git


@app.command("list")
def list_stack() -> None:
    """List all branches in the current stack.

    Output Format (for AI Agents):
    - JSON mode: Returns a structured tree of branches with parent relationships
    - Normal mode: Renders a visual tree in the terminal
    """
    config_manager, git = _require_init()

    stack = config_manager.load_stack()
    current_branch = git.get_current_branch()

    # Build the display data
    stack_data = []
    for item in stack.items:
        stack_data.append({
            "name": item.name,
            "parent": item.parent or stack.base_branch,
            "current": item.name == current_branch,
            "created_at": item.created_at,
        })

    # Add base branch info
    base_info = {
        "base_branch": stack.base_branch,
        "current_branch": current_branch,
        "stack": stack_data,
    }

    if is_json_mode():
        print_json(base_info)
    else:
        if not stack_data:
            print_info(f"Stack is empty. Base branch: {stack.base_branch}")
            print_info("Use 'gs stack add <name>' to create a new branch")
        else:
            print_stack_tree(stack_data)


@app.command("add")
def add_branch(
    name: Annotated[str, typer.Argument(help="Name for the new branch")],
    parent: Annotated[
        Optional[str],
        typer.Option("--parent", "-p", help="Parent branch (default: current branch)")
    ] = None,
) -> None:
    """Create a new branch stacked on the current branch.

    This command:
    1. Creates a new branch from the current HEAD
    2. Tracks the parent relationship for future syncs
    3. Checks out the new branch

    Example:
        gs stack add feature/auth
        gs stack add feature/ui --parent feature/auth
    """
    config_manager, git = _require_init()

    # Determine parent branch
    current_branch = git.get_current_branch()
    if current_branch is None:
        print_error("Cannot stack from detached HEAD state")
        raise typer.Exit(1)

    parent_branch = parent or current_branch

    # Check if branch already exists
    if git.branch_exists(name):
        print_error(f"Branch '{name}' already exists")
        raise typer.Exit(1)

    # Check for dirty tree
    if git.is_dirty():
        print_warning("Working tree has uncommitted changes")
        print_info("Auto-stashing changes...")
        stashed = True
        git.stash_push("GhostStack: auto-stash before stack add")
    else:
        stashed = False

    try:
        # Create and checkout new branch
        git.create_branch(name, checkout=True)

        # Update stack state
        stack = config_manager.load_stack()
        stack.add_item(name=name, parent=parent_branch)
        config_manager.save_stack(stack)

        print_success(
            f"Created branch '{name}'",
            {
                "parent": parent_branch,
                "stashed": stashed,
            },
        )

    except GitError as e:
        print_error("Failed to create branch", {"error": str(e)})
        raise typer.Exit(1)

    finally:
        # Restore stashed changes if we stashed
        if stashed:
            print_info("Restoring stashed changes...")
            try:
                git.stash_pop()
            except GitError:
                print_warning("Could not restore stash automatically. Run 'git stash pop' manually.")


@app.command("sync")
def sync_stack(
    target: Annotated[
        Optional[str],
        typer.Option("--target", "-t", help="Target branch to rebase onto")
    ] = None,
    update_refs: Annotated[
        bool,
        typer.Option("--update-refs/--no-update-refs", help="Use git rebase --update-refs")
    ] = True,
) -> None:
    """Sync (rebase) the current stack onto the base branch.

    This command uses `git rebase --update-refs` to efficiently
    rebase the entire stack while maintaining branch pointers.

    Example:
        gs stack sync              # Rebase onto default base (main)
        gs stack sync -t develop   # Rebase onto develop
    """
    config_manager, git = _require_init()

    stack = config_manager.load_stack()
    target_branch = target or stack.base_branch

    # Check for dirty tree
    if git.is_dirty():
        print_error("Working tree has uncommitted changes")
        print_info("Please commit or stash your changes before syncing")
        raise typer.Exit(1)

    current_branch = git.get_current_branch()
    if current_branch is None:
        print_error("Cannot sync from detached HEAD state")
        raise typer.Exit(1)

    print_info(f"Syncing stack onto '{target_branch}'...")

    try:
        git.rebase(target_branch, update_refs=update_refs)
        print_success(
            "Stack synced successfully",
            {
                "target": target_branch,
                "current_branch": current_branch,
                "update_refs": update_refs,
            },
        )

    except GitError as e:
        print_error("Rebase failed", {"error": str(e)})
        print_info("Resolve conflicts and run 'git rebase --continue', or 'git rebase --abort'")
        raise typer.Exit(1)


@app.command("remove")
def remove_branch(
    name: Annotated[str, typer.Argument(help="Name of the branch to remove from stack")],
    delete_branch: Annotated[
        bool,
        typer.Option("--delete/--no-delete", "-d", help="Also delete the Git branch")
    ] = False,
) -> None:
    """Remove a branch from the stack tracking.

    This removes the branch from GhostStack's tracking. Optionally
    also deletes the Git branch itself.

    Example:
        gs stack remove feature/old       # Remove from tracking only
        gs stack remove feature/old -d    # Also delete the Git branch
    """
    config_manager, git = _require_init()

    stack = config_manager.load_stack()

    # Check if in stack
    item = stack.get_item(name)
    if item is None:
        print_error(f"Branch '{name}' is not in the stack")
        raise typer.Exit(1)

    # Check for children
    children = stack.get_children(name)
    if children:
        child_names = [c.name for c in children]
        print_error(
            f"Cannot remove '{name}': other branches depend on it",
            {"children": child_names},
        )
        raise typer.Exit(1)

    # Remove from stack
    stack.remove_item(name)
    config_manager.save_stack(stack)

    # Optionally delete Git branch
    if delete_branch:
        current = git.get_current_branch()
        if current == name:
            print_error("Cannot delete the currently checked out branch")
            raise typer.Exit(1)

        try:
            git._run("branch", "-D", name)
            print_success(f"Removed and deleted branch '{name}'")
        except GitError as e:
            print_warning(f"Removed from stack, but failed to delete Git branch: {e}")
    else:
        print_success(f"Removed '{name}' from stack (Git branch still exists)")
