"""Code index using ChromaDB for semantic search."""

import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from ghoststack.brain.embeddings import EmbeddingModel


class CodeIndex:
    """ChromaDB-based code index for semantic search."""

    COLLECTION_NAME = "ghoststack_code"

    def __init__(self, db_path: Path):
        """Initialize the code index.

        Args:
            db_path: Path to the ChromaDB storage directory.
        """
        self.db_path = db_path
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with persistent storage
        self._client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create the code collection
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "GhostStack code embeddings"},
        )

        # Lazy-load embedding model
        self._embedder = None

    @property
    def embedder(self) -> EmbeddingModel:
        """Get the embedding model (lazy-loaded)."""
        if self._embedder is None:
            self._embedder = EmbeddingModel(use_fallback=True)  # Use fallback for now
        return self._embedder

    @staticmethod
    def _hash_content(content: str) -> str:
        """Generate a hash of the content for change detection."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def add_file(
        self,
        file_path: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add or update a file in the index.

        Args:
            file_path: Relative path to the file.
            content: The file content to index.
            metadata: Optional metadata (language, etc.).

        Returns:
            The document ID.
        """
        doc_id = file_path.replace("/", "_").replace(".", "_")
        content_hash = self._hash_content(content)

        # Check if file is already indexed with same content
        existing = self._collection.get(ids=[doc_id], include=["metadatas"])
        if existing["ids"] and existing["metadatas"]:
            existing_meta = existing["metadatas"][0]
            if existing_meta.get("content_hash") == content_hash:
                # Content unchanged, skip re-indexing
                return doc_id

        # Generate embedding
        embedding = self.embedder.embed(content)

        # Prepare metadata
        meta = {
            "file_path": file_path,
            "content_hash": content_hash,
            **(metadata or {}),
        }

        # Upsert the document
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[meta],
        )

        return doc_id

    def add_chunk(
        self,
        file_path: str,
        chunk_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a chunk of a file to the index.

        Args:
            file_path: Relative path to the source file.
            chunk_id: Unique identifier for this chunk (e.g., function name).
            content: The chunk content.
            metadata: Optional metadata.

        Returns:
            The document ID.
        """
        doc_id = f"{file_path}::{chunk_id}".replace("/", "_").replace(".", "_")
        content_hash = self._hash_content(content)

        # Check for existing
        existing = self._collection.get(ids=[doc_id], include=["metadatas"])
        if existing["ids"] and existing["metadatas"]:
            if existing["metadatas"][0].get("content_hash") == content_hash:
                return doc_id

        embedding = self.embedder.embed(content)

        meta = {
            "file_path": file_path,
            "chunk_id": chunk_id,
            "content_hash": content_hash,
            **(metadata or {}),
        }

        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[meta],
        )

        return doc_id

    def search(
        self,
        query: str,
        n_results: int = 10,
        file_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for relevant code.

        Args:
            query: The search query.
            n_results: Maximum number of results.
            file_filter: Optional list of file paths to exclude.

        Returns:
            List of search results with file_path, content, and score.
        """
        query_embedding = self.embedder.embed(query)

        # Build where filter to exclude certain files
        where_filter = None
        if file_filter:
            where_filter = {"file_path": {"$nin": file_filter}}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # Format results
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": doc_id,
                    "file_path": results["metadatas"][0][i].get("file_path", ""),
                    "chunk_id": results["metadatas"][0][i].get("chunk_id"),
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                    "metadata": results["metadatas"][0][i],
                })

        return formatted

    def get_related_files(
        self,
        changed_files: list[str],
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Find files related to a set of changed files.

        This is used to identify "hidden impact" - files that might be
        affected by changes but weren't directly modified.

        Args:
            changed_files: List of file paths that were changed.
            n_results: Number of related files to return per changed file.

        Returns:
            List of related files with relevance scores.
        """
        related = {}

        for file_path in changed_files:
            # Get the content of the changed file from the index
            doc_id = file_path.replace("/", "_").replace(".", "_")
            result = self._collection.get(ids=[doc_id], include=["documents"])

            if result["documents"] and result["documents"][0]:
                content = result["documents"][0]
                # Search for related files, excluding the changed files
                matches = self.search(
                    query=content[:2000],  # Limit query size
                    n_results=n_results + len(changed_files),
                    file_filter=changed_files,
                )

                for match in matches:
                    path = match["file_path"]
                    if path not in changed_files:
                        if path not in related or match["distance"] < related[path]["distance"]:
                            related[path] = match

        # Sort by relevance (lower distance = more relevant)
        return sorted(related.values(), key=lambda x: x["distance"])

    def remove_file(self, file_path: str) -> bool:
        """Remove a file from the index.

        Args:
            file_path: The file path to remove.

        Returns:
            True if removed, False if not found.
        """
        doc_id = file_path.replace("/", "_").replace(".", "_")
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception:
            return False

    def clear(self) -> None:
        """Clear all documents from the index."""
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "GhostStack code embeddings"},
        )

    @property
    def count(self) -> int:
        """Get the number of indexed documents."""
        return self._collection.count()
