"""Output utilities for agent-friendly formatting."""

import json
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()
error_console = Console(stderr=True)

# Global flag for JSON output mode
_json_mode = False


def set_json_mode(enabled: bool) -> None:
    """Enable or disable JSON output mode."""
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    """Check if JSON output mode is enabled."""
    return _json_mode


def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    console.print(json.dumps(data, indent=2, default=str))


def print_markdown(content: str) -> None:
    """Print content as rendered Markdown."""
    if _json_mode:
        print_json({"markdown": content})
    else:
        console.print(Markdown(content))


def print_success(message: str, details: dict[str, Any] | None = None) -> None:
    """Print a success message."""
    if _json_mode:
        print_json({"status": "success", "message": message, **(details or {})})
    else:
        console.print(f"[bold green]✓[/] {message}")
        if details:
            for key, value in details.items():
                console.print(f"  [dim]{key}:[/] {value}")


def print_error(message: str, details: dict[str, Any] | None = None) -> None:
    """Print an error message."""
    if _json_mode:
        print_json({"status": "error", "message": message, **(details or {})})
    else:
        error_console.print(f"[bold red]✗[/] {message}")
        if details:
            for key, value in details.items():
                error_console.print(f"  [dim]{key}:[/] {value}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    if _json_mode:
        print_json({"status": "warning", "message": message})
    else:
        console.print(f"[bold yellow]⚠[/] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    if _json_mode:
        print_json({"status": "info", "message": message})
    else:
        console.print(f"[bold blue]ℹ[/] {message}")


def print_stack_tree(stack: list[dict[str, Any]]) -> None:
    """Print the stack as a tree structure."""
    if _json_mode:
        print_json({"stack": stack})
        return

    if not stack:
        console.print("[dim]No branches in stack[/]")
        return

    console.print(Panel("[bold]📚 GhostStack[/]", expand=False))
    for i, item in enumerate(stack):
        prefix = "└──" if i == len(stack) - 1 else "├──"
        current = " [bold cyan]← current[/]" if item.get("current") else ""
        console.print(f"  {prefix} [bold]{item['name']}[/]{current}")
        if item.get("parent"):
            console.print(f"      [dim]↳ parent: {item['parent']}[/]")
