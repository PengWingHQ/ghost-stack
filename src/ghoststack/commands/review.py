"""Review command - AI-powered code review with semantic search."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from ghoststack.core.config import ConfigManager
from ghoststack.core.git import Git, GitError
from ghoststack.utils.output import (
    is_json_mode,
    print_error,
    print_info,
    print_json,
    print_markdown,
    print_success,
    print_warning,
)


def _get_diff_files(git: Git, base: str) -> list[dict]:
    """Get list of changed files between current branch and base.

    Returns:
        List of dicts with path, status, additions, deletions.
    """
    result = git._run(
        "diff", "--numstat", "--name-status", base, "HEAD",
        check=False,
    )

    if not result.success:
        return []

    files = []
    lines = result.stdout.strip().split("\n") if result.stdout else []

    # Parse numstat output (additions, deletions, path)
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            additions = int(parts[0]) if parts[0].isdigit() else 0
            deletions = int(parts[1]) if parts[1].isdigit() else 0
            path = parts[2]
            files.append({
                "path": path,
                "additions": additions,
                "deletions": deletions,
            })
        elif len(parts) >= 2:
            # name-status format
            status = parts[0]
            path = parts[1]
            files.append({
                "path": path,
                "status": status,
            })

    return files


def _get_diff_content(git: Git, base: str, file_path: str) -> str:
    """Get the diff content for a specific file."""
    result = git._run("diff", base, "HEAD", "--", file_path, check=False)
    return result.stdout if result.success else ""


def _calculate_risk_level(
    changed_files: list[dict],
    related_files: list[dict],
) -> tuple[str, list[str]]:
    """Calculate the risk level of the changes.

    Returns:
        Tuple of (risk_level, reasons).
    """
    reasons = []
    risk_score = 0

    # More changes = higher risk
    total_changes = sum(f.get("additions", 0) + f.get("deletions", 0) for f in changed_files)
    if total_changes > 500:
        risk_score += 2
        reasons.append(f"Large changeset ({total_changes} lines)")
    elif total_changes > 100:
        risk_score += 1

    # Many files = higher risk
    if len(changed_files) > 10:
        risk_score += 2
        reasons.append(f"Many files changed ({len(changed_files)})")
    elif len(changed_files) > 5:
        risk_score += 1

    # Related files not in diff = potential hidden impact
    if len(related_files) > 3:
        risk_score += 2
        reasons.append(f"Found {len(related_files)} potentially impacted files not in diff")
    elif len(related_files) > 0:
        risk_score += 1
        reasons.append(f"Found {len(related_files)} related file(s)")

    # Determine risk level
    if risk_score >= 4:
        return "High", reasons
    elif risk_score >= 2:
        return "Medium", reasons
    else:
        return "Low", reasons


def review_command(
    base: Annotated[
        Optional[str],
        typer.Option("--base", "-b", help="Base branch to compare against")
    ] = None,
    show_related: Annotated[
        int,
        typer.Option("--related", "-r", help="Number of related files to show")
    ] = 5,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Show detailed analysis")
    ] = False,
) -> None:
    """Generate an AI-powered review of your changes.

    This command:
    1. Analyzes the diff between your branch and its parent
    2. Searches for semantically related files (hidden impact)
    3. Generates a risk assessment and recommendations

    Example:
        gs review              # Compare against parent branch
        gs review --base main  # Compare against main
    """
    from ghoststack.brain import CodeIndex

    config_manager = ConfigManager()
    if not config_manager.is_initialized():
        print_error("GhostStack not initialized. Run 'gs init' first.")
        raise typer.Exit(1)

    git = Git()
    if not git.is_repo():
        print_error("Not a Git repository")
        raise typer.Exit(1)

    # Determine base branch
    current_branch = git.get_current_branch()
    if not current_branch:
        print_error("Cannot review in detached HEAD state")
        raise typer.Exit(1)

    # Try to find parent from stack, fall back to default base
    if base is None:
        stack = config_manager.load_stack()
        item = stack.get_item(current_branch)
        if item and item.parent:
            base = item.parent
        else:
            base = stack.base_branch
            if not git.branch_exists(base):
                # Try origin/main
                result = git._run("rev-parse", "--verify", f"origin/{base}", check=False)
                if result.success:
                    base = f"origin/{base}"
                else:
                    print_error(f"Base branch '{base}' not found")
                    raise typer.Exit(1)

    print_info(f"Comparing {current_branch} → {base}")

    # Get changed files
    changed_files = _get_diff_files(git, base)
    if not changed_files:
        print_success("No changes detected")
        if is_json_mode():
            print_json({
                "status": "success",
                "message": "No changes detected",
                "branch": current_branch,
                "base": base,
            })
        raise typer.Exit(0)

    # Load the code index
    chroma_path = config_manager.ghoststack_dir / "chroma"
    if not chroma_path.exists():
        print_warning("Code index not found. Run 'gs brain index' first.")
        related_files = []
    else:
        try:
            index = CodeIndex(chroma_path)
            if index.count == 0:
                print_warning("Code index is empty. Run 'gs brain index' first.")
                related_files = []
            else:
                # Find related files
                changed_paths = [f["path"] for f in changed_files]
                related_files = index.get_related_files(
                    changed_paths,
                    n_results=show_related,
                )
        except Exception as e:
            if verbose:
                print_warning(f"Could not load index: {e}")
            related_files = []

    # Calculate risk
    risk_level, risk_reasons = _calculate_risk_level(changed_files, related_files)

    # Build output
    if is_json_mode():
        output = {
            "branch": current_branch,
            "base": base,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "changed_files": changed_files,
            "related_files": [
                {
                    "path": f["file_path"],
                    "relevance": round(1 - f["distance"], 3) if f.get("distance") else None,
                    "chunk": f.get("chunk_id"),
                }
                for f in related_files
            ],
        }
        print_json(output)
    else:
        # Markdown output
        md_lines = [
            f"## 👻 GhostStack Review",
            "",
            f"**Branch:** `{current_branch}` → `{base}`",
            "",
        ]

        # Risk level with emoji
        risk_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(risk_level, "⚪")
        md_lines.append(f"**Risk Level:** {risk_emoji} {risk_level}")

        if risk_reasons:
            for reason in risk_reasons:
                md_lines.append(f"  - {reason}")

        md_lines.append("")

        # Changed files
        md_lines.append("### 📝 Changed Files")
        md_lines.append("")
        for f in changed_files[:10]:  # Limit display
            adds = f.get("additions", 0)
            dels = f.get("deletions", 0)
            md_lines.append(f"- `{f['path']}` (+{adds}, -{dels})")

        if len(changed_files) > 10:
            md_lines.append(f"- ... and {len(changed_files) - 10} more")

        md_lines.append("")

        # Related files (hidden impact)
        if related_files:
            md_lines.append("### ⚠️ Hidden Impact")
            md_lines.append("")
            md_lines.append("These files weren't changed but may be affected:")
            md_lines.append("")
            for f in related_files:
                relevance = round((1 - f.get("distance", 0)) * 100)
                chunk = f.get("chunk_id", "")
                chunk_info = f" ({chunk})" if chunk and chunk != "full" else ""
                md_lines.append(f"- `{f['file_path']}`{chunk_info} — {relevance}% relevant")
        else:
            md_lines.append("### ✅ No Hidden Impact Detected")
            md_lines.append("")
            md_lines.append("No semantically related files found outside your changes.")

        print_markdown("\n".join(md_lines))
