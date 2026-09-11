"""ChromaDB vector store for regulation chunks.

Chunks are stored with the embeddings we pass in, so ChromaDB never needs to
download an embedding model of its own. Data is kept in a local directory under
data/ and is not committed to git.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ai_modules.regulation_rag.chunking import RegulationChunk
from ai_modules.regulation_rag.errors import VectorStoreUnavailableError


@dataclass
class RetrievedChunk:
    """A chunk returned by a similarity search."""

    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)
    distance: float = 0.0


class RegulationVectorStore:
    """Stores and searches regulation chunks in ChromaDB."""

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = "civicai_regulations",
        collection=None,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._collection = collection

    @property
    def collection(self):
        """The ChromaDB collection, opened on first use."""
        if self._collection is None:
            try:
                import chromadb
            except ImportError as error:
                raise VectorStoreUnavailableError(
                    "chromadb is not installed. "
                    "Install it with: pip install -r requirements.txt"
                ) from error

            try:
                self.persist_dir.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=str(self.persist_dir))
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    # Cosine distance suits normalised sentence embeddings.
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as error:
                raise VectorStoreUnavailableError(
                    f"Could not open ChromaDB at {self.persist_dir}: {error}"
                ) from error
        return self._collection

    def add_chunks(
        self, chunks: list[RegulationChunk], embeddings: list[list[float]]
    ) -> int:
        """Insert or update chunks. Re-ingesting a chunk overwrites it."""
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.as_metadata() for chunk in chunks],
        )
        return len(chunks)

    def delete_document(self, source: str) -> None:
        """Remove every chunk that came from one source file."""
        self.collection.delete(where={"source": source})

    def replace_document(
        self, source: str, chunks: list[RegulationChunk], embeddings: list[list[float]]
    ) -> int:
        """Replace a document's chunks, so shrinking a file leaves nothing stale."""
        self.delete_document(source)
        return self.add_chunks(chunks, embeddings)

    def search(self, query_embedding: list[float], top_k: int = 8) -> list[RetrievedChunk]:
        """Return the closest chunks to a query embedding."""
        if top_k <= 0:
            return []

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        retrieved = []
        for position, chunk_id in enumerate(ids):
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=documents[position] if position < len(documents) else "",
                    metadata=dict(metadatas[position] or {})
                    if position < len(metadatas)
                    else {},
                    distance=float(distances[position])
                    if position < len(distances)
                    else 0.0,
                )
            )
        return retrieved

    def count(self) -> int:
        """How many chunks are stored."""
        return self.collection.count()
