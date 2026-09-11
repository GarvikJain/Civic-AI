"""Regulation RAG Assistant.

Pipeline:
1. Load regulation documents from data/regulations/ (ingestion.py).
2. Split them into chunks that keep their citation metadata (chunking.py).
3. Embed the chunks with sentence-transformers (embeddings.py).
4. Store them in ChromaDB (vector_store.py).
5. Supplement retrieval with a NetworkX knowledge graph (knowledge_graph.py).
6. Rerank candidates with a cross-encoder (reranker.py).
7. Answer from that evidence with the Groq LLM (llm_service.py).

pipeline.py joins these together and returns a grounded answer with citations,
or a fixed "not enough information" reply when the evidence is too weak.

The heavy models are imported and loaded only when first used, so importing
this package is cheap and needs no model downloads.
"""

from ai_modules.regulation_rag.config import RagConfig
from ai_modules.regulation_rag.errors import (
    EmbeddingUnavailableError,
    LlmUnavailableError,
    RagError,
    RerankerUnavailableError,
    VectorStoreUnavailableError,
)
from ai_modules.regulation_rag.pipeline import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    Citation,
    RagAnswer,
    RegulationRagPipeline,
    get_pipeline,
    reset_pipeline,
)

__all__ = [
    "INSUFFICIENT_EVIDENCE_MESSAGE",
    "Citation",
    "EmbeddingUnavailableError",
    "LlmUnavailableError",
    "RagAnswer",
    "RagConfig",
    "RagError",
    "RegulationRagPipeline",
    "RerankerUnavailableError",
    "VectorStoreUnavailableError",
    "get_pipeline",
    "reset_pipeline",
]
