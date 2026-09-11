"""Errors raised by the Regulation RAG module.

Each service raises a clear error when it cannot start, so the API can answer
with "service unavailable" instead of returning a guessed answer.
"""


class RagError(RuntimeError):
    """Base class for every Regulation RAG failure."""


class EmbeddingUnavailableError(RagError):
    """The sentence-transformers embedding model could not be loaded."""


class VectorStoreUnavailableError(RagError):
    """ChromaDB could not be opened."""


class RerankerUnavailableError(RagError):
    """The cross-encoder reranker could not be loaded."""


class LlmUnavailableError(RagError):
    """The Groq LLM is not configured or could not be reached."""
