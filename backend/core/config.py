"""Application configuration.

All settings are read from environment variables (or the .env file) so that
nothing environment-specific is hard-coded in the source.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: .../Civic-AI (this file is at backend/core/config.py)
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings for the whole CivicAI project."""

    # --- Application ---
    app_name: str = "CivicAI"
    app_version: str = "0.1.0"
    debug: bool = True

    # --- Database ---
    # SQLite for now. Point this at PostgreSQL later without other changes.
    database_url: str = "sqlite:///./data/civicai.db"

    # --- Authentication ---
    jwt_secret_key: str = "change-me-to-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Frontend ---
    backend_url: str = "http://127.0.0.1:8000"

    # --- LLM (Groq) ---
    groq_api_key: str = ""
    # Groq retires models over time; check https://console.groq.com/docs/models
    # if a request fails with a "model not found" error.
    groq_model: str = "openai/gpt-oss-20b"

    # --- AI module paths and models ---
    chroma_dir: str = "./data/chroma"
    chroma_collection: str = "civicai_regulations"
    regulations_dir: str = "./data/regulations"
    upload_dir: str = "./data/uploads"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Regulation RAG ---
    # Chunk sizes are in characters.
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 150
    # Candidates fetched from ChromaDB before reranking.
    rag_top_k: int = 8
    # Chunks kept after reranking and sent to the LLM.
    rag_rerank_top_k: int = 3
    # Minimum cross-encoder score for a chunk to count as evidence. Below this
    # the assistant returns the insufficient-evidence answer instead of asking
    # the LLM to guess.
    rag_min_score: float = 0.0

    # --- OCR ---
    tesseract_cmd: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the settings, reading the environment only once."""
    return Settings()


settings = get_settings()
