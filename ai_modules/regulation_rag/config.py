"""Settings for the Regulation RAG pipeline.

This dataclass has working defaults of its own, so the AI code can be used and
tested without the FastAPI application. from_settings() fills it in from the
project's .env configuration.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RagConfig:
    # Where the local regulation documents live.
    regulations_dir: Path = Path("data/regulations")

    # Vector store
    chroma_dir: Path = Path("data/chroma")
    collection_name: str = "civicai_regulations"

    # Models
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Chunking, in characters
    chunk_size: int = 900
    chunk_overlap: int = 150

    # Retrieval
    top_k: int = 8
    rerank_top_k: int = 3
    min_score: float = 0.0

    # LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    @classmethod
    def from_settings(cls) -> "RagConfig":
        """Build the config from the project's environment settings."""
        from backend.core.config import BASE_DIR, settings

        def absolute(path_value: str) -> Path:
            path = Path(path_value)
            return path if path.is_absolute() else BASE_DIR / path

        return cls(
            regulations_dir=absolute(settings.regulations_dir),
            chroma_dir=absolute(settings.chroma_dir),
            collection_name=settings.chroma_collection,
            embedding_model=settings.embedding_model,
            reranker_model=settings.reranker_model,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            top_k=settings.rag_top_k,
            rerank_top_k=settings.rag_rerank_top_k,
            min_score=settings.rag_min_score,
            groq_api_key=settings.groq_api_key,
            groq_model=settings.groq_model,
        )
