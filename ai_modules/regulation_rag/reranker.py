"""Cross-encoder reranking.

Vector search is fast but approximate. The cross-encoder reads the query and
each candidate chunk together, which ranks the evidence far more accurately.

If the model cannot be loaded the service raises an error instead of returning
an unranked list, so a weak ranking can never be mistaken for a good one.
"""

from dataclasses import dataclass

from ai_modules.regulation_rag.errors import RerankerUnavailableError
from ai_modules.regulation_rag.vector_store import RetrievedChunk


@dataclass
class RankedChunk:
    """A candidate chunk with its relevance score."""

    chunk: RetrievedChunk
    score: float


class RerankerService:
    """Scores query/chunk pairs with a sentence-transformers CrossEncoder.

    Pass `model` to use an already loaded model, or a stand-in during tests.
    """

    def __init__(self, model_name: str, model=None) -> None:
        self.model_name = model_name
        self._model = model

    @property
    def model(self):
        """The cross-encoder, loaded on first use."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as error:
                raise RerankerUnavailableError(
                    "sentence-transformers is not installed. "
                    "Install it with: pip install -r requirements.txt"
                ) from error

            try:
                self._model = CrossEncoder(self.model_name)
            except Exception as error:
                raise RerankerUnavailableError(
                    f"Could not load the reranker model '{self.model_name}': {error}"
                ) from error
        return self._model

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RankedChunk]:
        """Return the candidates ordered from most to least relevant."""
        if not candidates:
            return []

        pairs = [(query, candidate.text) for candidate in candidates]
        try:
            scores = self.model.predict(pairs)
        except Exception as error:
            raise RerankerUnavailableError(
                f"The reranker failed to score the candidates: {error}"
            ) from error

        ranked = [
            RankedChunk(chunk=candidate, score=float(score))
            for candidate, score in zip(candidates, scores)
        ]
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked
