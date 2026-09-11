"""The Regulation RAG pipeline.

    citizen query
      -> embed the query
      -> search ChromaDB for candidate chunks
      -> add knowledge graph context
      -> rerank candidates with the cross-encoder
      -> keep only evidence above the score threshold
      -> ask Groq for an answer grounded in that evidence
      -> return the answer with citations

If the evidence is too weak, the LLM is never called and a fixed
"not enough information" answer is returned instead.
"""

from dataclasses import dataclass, field
from functools import lru_cache

from ai_modules.regulation_rag.chunking import RegulationChunk, chunk_document
from ai_modules.regulation_rag.config import RagConfig
from ai_modules.regulation_rag.embeddings import EmbeddingService
from ai_modules.regulation_rag.ingestion import RegulationDocument
from ai_modules.regulation_rag.knowledge_graph import KnowledgeGraphService
from ai_modules.regulation_rag.llm_service import INSUFFICIENT_MARKER, GroqLlmService
from ai_modules.regulation_rag.reranker import RankedChunk, RerankerService
from ai_modules.regulation_rag.vector_store import RegulationVectorStore

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I could not find sufficient information in the available official "
    "regulations to answer this question."
)


@dataclass(frozen=True)
class Citation:
    """Where a piece of the answer came from.

    Every field comes from the stored document metadata. A field stays None if
    the source did not provide it; nothing is ever invented.
    """

    scheme_name: str | None = None
    circular_reference: str | None = None
    section: str | None = None
    source: str | None = None
    regulation_id: int | None = None


@dataclass
class RagAnswer:
    """The pipeline's result."""

    answer: str
    citations: list[Citation] = field(default_factory=list)
    insufficient_evidence: bool = False
    evidence_count: int = 0

    @property
    def primary_regulation_id(self) -> int | None:
        """The regulation of the best-supported citation, if there is one."""
        for citation in self.citations:
            if citation.regulation_id is not None:
                return citation.regulation_id
        return None


def _citation_from_metadata(metadata: dict) -> Citation:
    regulation_id = metadata.get("regulation_id")
    return Citation(
        scheme_name=metadata.get("scheme_name"),
        circular_reference=metadata.get("circular_reference"),
        section=metadata.get("section"),
        source=metadata.get("source"),
        regulation_id=int(regulation_id) if regulation_id is not None else None,
    )


def _unique_citations(evidence: list[RankedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    for ranked in evidence:
        citation = _citation_from_metadata(ranked.chunk.metadata)
        if citation not in citations:
            citations.append(citation)
    return citations


class RegulationRagPipeline:
    """Runs retrieval, reranking and answering.

    Every service can be replaced, which is how the tests avoid loading models.
    """

    def __init__(
        self,
        config: RagConfig | None = None,
        embedder: EmbeddingService | None = None,
        vector_store: RegulationVectorStore | None = None,
        reranker: RerankerService | None = None,
        llm: GroqLlmService | None = None,
        knowledge_graph: KnowledgeGraphService | None = None,
    ) -> None:
        self.config = config or RagConfig()
        self.embedder = embedder or EmbeddingService(self.config.embedding_model)
        self.vector_store = vector_store or RegulationVectorStore(
            self.config.chroma_dir, self.config.collection_name
        )
        self.reranker = reranker or RerankerService(self.config.reranker_model)
        self.llm = llm or GroqLlmService(
            self.config.groq_api_key, self.config.groq_model
        )
        self.knowledge_graph = knowledge_graph or KnowledgeGraphService()

    # --- ingestion ---------------------------------------------------------

    def ingest_document(self, document: RegulationDocument) -> list[RegulationChunk]:
        """Chunk, embed and store one document, replacing any earlier version."""
        chunks = chunk_document(
            document,
            chunk_size=self.config.chunk_size,
            overlap=self.config.chunk_overlap,
        )
        if not chunks:
            return []

        embeddings = self.embedder.embed_texts([chunk.text for chunk in chunks])
        self.vector_store.replace_document(document.source, chunks, embeddings)
        return chunks

    def ingest_documents(
        self, documents: list[RegulationDocument]
    ) -> dict[str, int]:
        """Ingest several documents. Returns chunks stored per source file."""
        return {
            document.source: len(self.ingest_document(document))
            for document in documents
        }

    # --- answering ---------------------------------------------------------

    def _insufficient(self) -> RagAnswer:
        return RagAnswer(
            answer=INSUFFICIENT_EVIDENCE_MESSAGE,
            citations=[],
            insufficient_evidence=True,
            evidence_count=0,
        )

    def answer(self, query: str) -> RagAnswer:
        """Answer a citizen's question from the stored regulations."""
        query = (query or "").strip()
        if not query:
            return self._insufficient()

        candidates = self.vector_store.search(
            self.embedder.embed_query(query), top_k=self.config.top_k
        )
        if not candidates:
            return self._insufficient()

        scheme_names = [
            candidate.metadata.get("scheme_name", "") for candidate in candidates
        ]
        graph_context = self.knowledge_graph.context_for(scheme_names)

        ranked = self.reranker.rerank(query, candidates)
        evidence = [item for item in ranked if item.score >= self.config.min_score][
            : self.config.rerank_top_k
        ]
        if not evidence:
            # Weak evidence only, so the LLM is not asked to fill the gap.
            return self._insufficient()

        answer_text = self.llm.generate_answer(query, evidence, graph_context)

        # The model reports insufficient context with a marker word.
        if not answer_text or INSUFFICIENT_MARKER in answer_text:
            return self._insufficient()

        return RagAnswer(
            answer=answer_text,
            citations=_unique_citations(evidence),
            insufficient_evidence=False,
            evidence_count=len(evidence),
        )


@lru_cache
def get_pipeline() -> RegulationRagPipeline:
    """The shared pipeline.

    Cached so the embedding and reranker models are loaded at most once per
    process instead of once per request.
    """
    return RegulationRagPipeline(RagConfig.from_settings())


def reset_pipeline() -> None:
    """Drop the cached pipeline, so new configuration is picked up."""
    get_pipeline.cache_clear()
