"""Safe Git wrapper with auto-stash and error handling."""

import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass
class GitResult:
    """Result of a Git command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        """Return stdout if successful, stderr otherwise."""
        return self.stdout if self.success else self.stderr


class GitError(Exception):
    """Exception raised when a Git command fails."""

    def __init__(self, message: str, result: GitResult | None = None):
        super().__init__(message)
        self.result = result


class Git:
    """Safe Git wrapper with auto-stash protection."""

    def __init__(self, repo_path: Path | None = None):
        """Initialize Git wrapper for the given repository path."""
        self.repo_path = repo_path or Path.cwd()
        self._stash_created = False

    def _run(self, *args: str, check: bool = True) -> GitResult:
        """Run a Git command and return the result."""
        cmd = ["git", "-C", str(self.repo_path), *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            git_result = GitResult(
                success=result.returncode == 0,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                returncode=result.returncode,
            )
            if check and not git_result.success:
                raise GitError(f"Git command failed: {' '.join(args)}", git_result)
            return git_result
        except subprocess.TimeoutExpired as e:
            raise GitError(f"Git command timed out: {' '.join(args)}") from e
        except FileNotFoundError as e:
            raise GitError("Git is not installed or not in PATH") from e

    def is_repo(self) -> bool:
        """Check if the current directory is a Git repository."""
        result = self._run("rev-parse", "--git-dir", check=False)
        return result.success

    def is_dirty(self) -> bool:
        """Check if the working tree has uncommitted changes."""
        result = self._run("status", "--porcelain", check=False)
        return bool(result.stdout)

    def get_current_branch(self) -> str | None:
        """Get the current branch name, or None if in detached HEAD state."""
        result = self._run("symbolic-ref", "--short", "HEAD", check=False)
        return result.stdout if result.success else None

    def get_all_branches(self) -> list[str]:
        """Get list of all local branches."""
        result = self._run("branch", "--format=%(refname:short)")
        return [b for b in result.stdout.split("\n") if b]

    def branch_exists(self, name: str) -> bool:
        """Check if a branch exists."""
        result = self._run("show-ref", "--verify", f"refs/heads/{name}", check=False)
        return result.success

    def create_branch(self, name: str, checkout: bool = True) -> None:
        """Create a new branch, optionally checking it out."""
        if self.branch_exists(name):
            raise GitError(f"Branch '{name}' already exists")
        if checkout:
            self._run("checkout", "-b", name)
        else:
            self._run("branch", name)

    def checkout(self, ref: str) -> None:
        """Checkout a branch or commit."""
        self._run("checkout", ref)

    def get_merge_base(self, branch1: str, branch2: str) -> str:
        """Get the merge base of two branches."""
        result = self._run("merge-base", branch1, branch2)
        return result.stdout

    def rebase(self, target: str, update_refs: bool = False) -> None:
        """Rebase the current branch onto target."""
        args = ["rebase"]
        if update_refs:
            args.append("--update-refs")
        args.append(target)
        self._run(*args)

    def stash_push(self, message: str = "GhostStack auto-stash") -> bool:
        """Stash changes. Returns True if a stash was created."""
        if not self.is_dirty():
            return False
        self._run("stash", "push", "-m", message)
        return True

    def stash_pop(self) -> None:
        """Pop the most recent stash."""
        self._run("stash", "pop")

    @contextmanager
    def auto_stash(self) -> Generator[bool, None, None]:
        """Context manager that auto-stashes and restores changes.

        Yields True if a stash was created, False otherwise.
        """
        stashed = self.stash_push()
        try:
            yield stashed
        finally:
            if stashed:
                self.stash_pop()

    def get_config(self, key: str) -> str | None:
        """Get a Git config value."""
        result = self._run("config", "--get", key, check=False)
        return result.stdout if result.success else None

    def set_config(self, key: str, value: str, local: bool = True) -> None:
        """Set a Git config value."""
        args = ["config"]
        if local:
            args.append("--local")
        args.extend([key, value])
        self._run(*args)

    def get_remote_url(self, remote: str = "origin") -> str | None:
        """Get the URL of a remote."""
        result = self._run("remote", "get-url", remote, check=False)
        return result.stdout if result.success else None
