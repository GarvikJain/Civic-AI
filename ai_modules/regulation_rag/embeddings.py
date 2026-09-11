"""Embedding service built on sentence-transformers.

The model is loaded once, the first time it is needed, and then reused. It is
never loaded at import time, so the API can start (and the tests can run)
without the model being present.
"""

from ai_modules.regulation_rag.errors import EmbeddingUnavailableError


class EmbeddingService:
    """Turns text into vectors.

    Pass `encoder` to use an already loaded model, or a stand-in during tests.
    """

    def __init__(self, model_name: str, encoder=None) -> None:
        self.model_name = model_name
        self._encoder = encoder

    @property
    def encoder(self):
        """The sentence-transformers model, loaded on first use."""
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise EmbeddingUnavailableError(
                    "sentence-transformers is not installed. "
                    "Install it with: pip install -r requirements.txt"
                ) from error

            try:
                self._encoder = SentenceTransformer(self.model_name)
            except Exception as error:
                raise EmbeddingUnavailableError(
                    f"Could not load the embedding model '{self.model_name}': {error}"
                ) from error
        return self._encoder

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed several texts, for ingestion."""
        if not texts:
            return []
        vectors = self.encoder.encode(texts)
        return [list(map(float, vector)) for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed one search query."""
        return self.embed_texts([text])[0]
