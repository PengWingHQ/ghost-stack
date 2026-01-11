"""Embedding model wrapper for code intelligence."""

import hashlib
import warnings
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


# Default model - good balance of speed and quality for code
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Flag to track if we're in fallback mode
_USE_FALLBACK = False


def _simple_hash_embedding(text: str, dimension: int = 384) -> list[float]:
    """Generate a simple hash-based embedding as fallback.
    
    This is NOT semantic, just for testing when sentence-transformers fails.
    """
    import struct
    
    # Create deterministic pseudo-random values from text hash
    hasher = hashlib.sha256(text.encode())
    digest = hasher.digest()
    
    embedding = []
    for i in range(dimension):
        # Use different parts of hash for different dimensions
        h = hashlib.sha256(digest + struct.pack('i', i)).digest()
        # Convert first 4 bytes to float between -1 and 1
        val = struct.unpack('f', h[:4])[0]
        # Normalize to reasonable range
        embedding.append((val % 2) - 1)
    
    return embedding


@lru_cache(maxsize=1)
def _get_model(model_name: str = DEFAULT_MODEL) -> "SentenceTransformer":
    """Lazy-load the embedding model (cached)."""
    global _USE_FALLBACK
    
    try:
        # Suppress warnings during import
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except Exception as e:
        _USE_FALLBACK = True
        raise RuntimeError(f"Failed to load sentence-transformers: {e}")


class EmbeddingModel:
    """Wrapper for generating text embeddings."""

    def __init__(self, model_name: str = DEFAULT_MODEL, use_fallback: bool = False):
        """Initialize with the specified model.
        
        Args:
            model_name: Name of the sentence-transformers model.
            use_fallback: If True, use hash-based fallback instead of real embeddings.
        """
        self.model_name = model_name
        self._model = None
        self._fallback = use_fallback
        self._dimension = 384  # Default for MiniLM

    @property
    def model(self) -> "SentenceTransformer":
        """Get the model, loading it on first access."""
        if self._fallback:
            raise RuntimeError("Model disabled, using fallback")
        if self._model is None:
            try:
                self._model = _get_model(self.model_name)
            except RuntimeError:
                self._fallback = True
                raise
        return self._model

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if self._fallback:
            return _simple_hash_embedding(text, self._dimension)
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception:
            self._fallback = True
            return _simple_hash_embedding(text, self._dimension)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []
        
        if self._fallback:
            return [_simple_hash_embedding(t, self._dimension) for t in texts]
        
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return [e.tolist() for e in embeddings]
        except Exception:
            self._fallback = True
            return [_simple_hash_embedding(t, self._dimension) for t in texts]

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        if self._fallback:
            return self._dimension
        try:
            return self.model.get_sentence_embedding_dimension()
        except Exception:
            return self._dimension
    
    @property
    def is_fallback(self) -> bool:
        """Check if using fallback mode."""
        return self._fallback
