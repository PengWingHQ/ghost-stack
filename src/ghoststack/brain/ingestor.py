"""File ingestor for indexing code files into ChromaDB."""

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Generator

from ghoststack.brain.index import CodeIndex


# File extensions to index by language
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
}

# Directories to skip
SKIP_DIRS = {
    ".git",
    ".ghoststack",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
    ".coverage",
}

# Maximum file size to index (in bytes)
MAX_FILE_SIZE = 500_000  # 500KB

# Chunk size for large files (in characters)
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200


class FileIngestor:
    """Scans and indexes code files into the vector database."""

    def __init__(self, repo_path: Path, index: CodeIndex):
        """Initialize the ingestor.

        Args:
            repo_path: Root path of the repository.
            index: The CodeIndex to populate.
        """
        self.repo_path = repo_path
        self.index = index
        self._hash_cache_path = repo_path / ".ghoststack" / "file_hashes.json"
        self._hash_cache: dict[str, str] = {}
        self._load_hash_cache()

    def _load_hash_cache(self) -> None:
        """Load the file hash cache from disk."""
        if self._hash_cache_path.exists():
            try:
                with open(self._hash_cache_path) as f:
                    self._hash_cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._hash_cache = {}

    def _save_hash_cache(self) -> None:
        """Save the file hash cache to disk."""
        self._hash_cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._hash_cache_path, "w") as f:
            json.dump(self._hash_cache, f, indent=2)

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Generate a hash of file content for change detection."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _should_index(self, path: Path) -> bool:
        """Check if a file should be indexed."""
        # Check extension
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False

        # Check file size
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                return False
        except OSError:
            return False

        return True

    def _get_relative_path(self, path: Path) -> str:
        """Get the path relative to the repo root."""
        return str(path.relative_to(self.repo_path))

    def scan_files(self) -> Generator[Path, None, None]:
        """Scan the repository for indexable files.

        Yields:
            Path objects for each file to index.
        """
        for path in self.repo_path.rglob("*"):
            # Skip directories in SKIP_DIRS
            if any(skip in path.parts for skip in SKIP_DIRS):
                continue

            if path.is_file() and self._should_index(path):
                yield path

    def _chunk_python(self, content: str, file_path: str) -> list[dict]:
        """Chunk Python code by function and class definitions.

        Args:
            content: The Python source code.
            file_path: Path to the file (for metadata).

        Returns:
            List of chunks with id, content, and metadata.
        """
        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to line-based chunking
            return self._chunk_by_lines(content, file_path)

        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno - 1
                end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 1

                chunk_content = "\n".join(lines[start_line:end_line])
                chunk_id = f"{node.name}"

                if isinstance(node, ast.ClassDef):
                    chunk_type = "class"
                else:
                    chunk_type = "function"

                chunks.append({
                    "id": chunk_id,
                    "content": chunk_content,
                    "metadata": {
                        "type": chunk_type,
                        "name": node.name,
                        "start_line": start_line + 1,
                        "end_line": end_line,
                    },
                })

        # If no chunks found, fall back to whole file
        if not chunks:
            chunks.append({
                "id": "module",
                "content": content[:CHUNK_SIZE],
                "metadata": {"type": "module"},
            })

        return chunks

    def _chunk_by_lines(self, content: str, file_path: str) -> list[dict]:
        """Chunk content by lines with overlap.

        Args:
            content: The file content.
            file_path: Path to the file (for metadata).

        Returns:
            List of chunks.
        """
        chunks = []

        if len(content) <= CHUNK_SIZE:
            return [{
                "id": "full",
                "content": content,
                "metadata": {"type": "full_file"},
            }]

        # Split into overlapping chunks
        start = 0
        chunk_num = 0
        while start < len(content):
            end = start + CHUNK_SIZE
            chunk_content = content[start:end]

            chunks.append({
                "id": f"chunk_{chunk_num}",
                "content": chunk_content,
                "metadata": {
                    "type": "chunk",
                    "chunk_num": chunk_num,
                    "start_char": start,
                    "end_char": min(end, len(content)),
                },
            })

            start += CHUNK_SIZE - CHUNK_OVERLAP
            chunk_num += 1

        return chunks

    def _chunk_file(self, path: Path, content: str) -> list[dict]:
        """Chunk a file based on its language.

        Args:
            path: Path to the file.
            content: File content.

        Returns:
            List of chunks.
        """
        rel_path = self._get_relative_path(path)
        ext = path.suffix.lower()
        language = SUPPORTED_EXTENSIONS.get(ext, "unknown")

        if language == "python":
            return self._chunk_python(content, rel_path)
        else:
            # For other languages, use line-based chunking
            # TODO: Add AST-based chunking for TypeScript, Go, etc.
            return self._chunk_by_lines(content, rel_path)

    def index_file(self, path: Path, force: bool = False) -> int:
        """Index a single file.

        Args:
            path: Path to the file to index.
            force: If True, re-index even if unchanged.

        Returns:
            Number of chunks indexed.
        """
        rel_path = self._get_relative_path(path)

        # Check if file has changed
        if not force:
            current_hash = self._hash_file(path)
            if self._hash_cache.get(rel_path) == current_hash:
                return 0
            self._hash_cache[rel_path] = current_hash

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except (IOError, OSError):
            return 0

        ext = path.suffix.lower()
        language = SUPPORTED_EXTENSIONS.get(ext, "unknown")

        # Get chunks
        chunks = self._chunk_file(path, content)

        # Index each chunk
        for chunk in chunks:
            self.index.add_chunk(
                file_path=rel_path,
                chunk_id=chunk["id"],
                content=chunk["content"],
                metadata={
                    "language": language,
                    **chunk["metadata"],
                },
            )

        return len(chunks)

    def index_all(
        self,
        force: bool = False,
        progress_callback=None,
    ) -> dict:
        """Index all code files in the repository.

        Args:
            force: If True, re-index all files even if unchanged.
            progress_callback: Optional callback(file_path, current, total).

        Returns:
            Stats dict with files_scanned, files_indexed, chunks_total.
        """
        files = list(self.scan_files())
        total_files = len(files)
        files_indexed = 0
        chunks_total = 0

        for i, path in enumerate(files):
            if progress_callback:
                rel_path = self._get_relative_path(path)
                progress_callback(rel_path, i + 1, total_files)

            chunks = self.index_file(path, force=force)
            if chunks > 0:
                files_indexed += 1
                chunks_total += chunks

        # Save the hash cache
        self._save_hash_cache()

        return {
            "files_scanned": total_files,
            "files_indexed": files_indexed,
            "chunks_total": chunks_total,
        }

    def remove_deleted_files(self) -> int:
        """Remove files from the index that no longer exist.

        Returns:
            Number of files removed.
        """
        removed = 0
        files_to_remove = []

        for rel_path in list(self._hash_cache.keys()):
            full_path = self.repo_path / rel_path
            if not full_path.exists():
                files_to_remove.append(rel_path)
                self.index.remove_file(rel_path)
                removed += 1

        for path in files_to_remove:
            del self._hash_cache[path]

        if removed > 0:
            self._save_hash_cache()

        return removed
