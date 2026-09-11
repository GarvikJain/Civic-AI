"""Tests for the Regulation RAG module (Phase 4).

No test downloads a model, calls Groq, or needs the internet. The embedding
model, cross-encoder and LLM are replaced with small deterministic stand-ins.
"""

import hashlib
import math
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_modules.regulation_rag.chunking import (
    RegulationChunk,
    chunk_document,
    detect_section,
    document_key,
)
from ai_modules.regulation_rag.config import RagConfig
from ai_modules.regulation_rag.embeddings import EmbeddingService
from ai_modules.regulation_rag.errors import LlmUnavailableError, RerankerUnavailableError
from ai_modules.regulation_rag.ingestion import (
    RegulationDocument,
    clean_text,
    load_document,
    load_documents,
    parse_header,
)
from ai_modules.regulation_rag.knowledge_graph import (
    KnowledgeGraphService,
    build_graph,
    graph_context,
)
from ai_modules.regulation_rag.llm_service import (
    INSUFFICIENT_MARKER,
    GroqLlmService,
    build_user_prompt,
)
from ai_modules.regulation_rag.pipeline import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    RegulationRagPipeline,
)
from ai_modules.regulation_rag.reranker import RankedChunk, RerankerService
from ai_modules.regulation_rag.vector_store import RegulationVectorStore, RetrievedChunk

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --- deterministic stand-ins for the AI models ------------------------------


def fake_vector(text: str, dim: int = 64) -> list[float]:
    """A stable bag-of-words vector, so similar text lands close together."""
    vector = [0.0] * dim
    for token in re.findall(r"[a-z]{3,}", text.lower()):
        index = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        vector[index] += 1.0
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / length for value in vector]


class FakeEncoder:
    """Stands in for a SentenceTransformer."""

    def encode(self, texts):
        return [fake_vector(text) for text in texts]


class FakeCrossEncoder:
    """Scores a pair by how many query words appear in the chunk."""

    def __init__(self, fixed_scores=None):
        self.fixed_scores = fixed_scores
        self.calls = []

    def predict(self, pairs):
        self.calls.append(pairs)
        if self.fixed_scores is not None:
            return self.fixed_scores[: len(pairs)]
        scores = []
        for query, text in pairs:
            words = set(re.findall(r"[a-z]{3,}", query.lower()))
            found = set(re.findall(r"[a-z]{3,}", text.lower()))
            scores.append(float(len(words & found)))
        return scores


class FakeVectorStore:
    """Returns canned candidates instead of talking to ChromaDB."""

    def __init__(self, candidates):
        self.candidates = candidates
        self.searches = []

    def search(self, query_embedding, top_k=8):
        self.searches.append(top_k)
        return self.candidates[:top_k]


class FakeLlm:
    """Records what it was asked and returns a canned answer."""

    def __init__(self, answer="Citizens must submit proof of income (Section 3)."):
        self.answer = answer
        self.calls = []

    def generate_answer(self, query, evidence, graph_context):
        self.calls.append(
            {"query": query, "evidence": evidence, "graph_context": graph_context}
        )
        return self.answer


def make_candidate(text, **metadata) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=metadata.get("chunk_id", "chunk-1"),
        text=text,
        metadata=metadata,
        distance=0.1,
    )


def build_pipeline(candidates, llm=None, cross_encoder=None, **config_kwargs):
    """A pipeline wired entirely with stand-ins."""
    config = RagConfig(**config_kwargs)
    return RegulationRagPipeline(
        config=config,
        embedder=EmbeddingService("fake", encoder=FakeEncoder()),
        vector_store=FakeVectorStore(candidates),
        reranker=RerankerService("fake", model=cross_encoder or FakeCrossEncoder()),
        llm=llm or FakeLlm(),
        knowledge_graph=KnowledgeGraphService([]),
    )


# --- 1. document loading ----------------------------------------------------

SAMPLE_DOCUMENT = """scheme_name: Income Certificate Scheme
department: Revenue
circular_reference: CIRC/2026/11
---
Section 1. Eligibility

Annual household income must be below 2,50,000 rupees.

Section 2. Required Documents

Proof of identity and proof of income are required.
"""


def test_header_and_body_are_parsed(tmp_path):
    header, body = parse_header(SAMPLE_DOCUMENT)
    assert header["scheme_name"] == "Income Certificate Scheme"
    assert header["department"] == "Revenue"
    assert header["circular_reference"] == "CIRC/2026/11"
    assert body.lstrip().startswith("Section 1.")


def test_document_without_a_header_uses_the_file_name(tmp_path):
    path = tmp_path / "old_age_pension.txt"
    path.write_text("Section 1. Anyone above sixty may apply.", encoding="utf-8")

    document = load_document(path)
    assert document.scheme_name == "Old Age Pension"
    assert document.department is None
    assert document.circular_reference is None


def test_load_document_reads_metadata_and_text(tmp_path):
    path = tmp_path / "income.txt"
    path.write_text(SAMPLE_DOCUMENT, encoding="utf-8")

    document = load_document(path)
    assert document.source == "income.txt"
    assert document.scheme_name == "Income Certificate Scheme"
    assert document.department == "Revenue"
    assert document.circular_reference == "CIRC/2026/11"
    assert "2,50,000" in document.text


def test_load_documents_skips_unsupported_files(tmp_path):
    (tmp_path / "a.txt").write_text("Section 1. Text", encoding="utf-8")
    (tmp_path / "b.md").write_text("Section 1. More text", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"not text")
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")

    documents = load_documents(tmp_path)
    assert sorted(d.source for d in documents) == ["a.txt", "b.md"]


def test_load_documents_handles_a_missing_directory(tmp_path):
    assert load_documents(tmp_path / "nope") == []


def test_unsupported_file_type_is_rejected(tmp_path):
    path = tmp_path / "regulation.pdf"
    path.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="Unsupported regulation file type"):
        load_document(path)


def test_clean_text_tidies_whitespace_but_keeps_paragraphs():
    cleaned = clean_text("Line  one   \r\n\r\n\r\n\r\nLine two\t\tend  ")
    assert cleaned == "Line one\n\nLine two end"


def test_the_bundled_example_document_loads():
    documents = load_documents(PROJECT_ROOT / "data" / "regulations")
    assert documents, "expected the example regulation document to be present"
    assert any("Example Income Certificate" in d.scheme_name for d in documents)


# --- 2. chunking ------------------------------------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Section 4. Eligibility", "Section 4"),
        ("SECTION 12", "Section 12"),
        ("Clause 3.1 Documents", "Clause 3.1"),
        ("Rule 7 Appeals", "Rule 7"),
        ("3.2) Processing", "Section 3.2"),
        ("Just an ordinary sentence.", None),
        ("", None),
    ],
)
def test_section_headings_are_detected(line, expected):
    assert detect_section(line) == expected


def test_chunking_is_deterministic():
    document = RegulationDocument(
        source="income.txt", text="Section 1. " + "word " * 400, scheme_name="Scheme"
    )
    first = chunk_document(document, chunk_size=200, overlap=20)
    second = chunk_document(document, chunk_size=200, overlap=20)

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert [c.text for c in first] == [c.text for c in second]


def test_chunk_ids_are_stable_and_unique():
    document = RegulationDocument(
        source="income.txt", text="Section 1. " + "word " * 400, scheme_name="Scheme"
    )
    chunks = chunk_document(document, chunk_size=200, overlap=20)

    assert len(chunks) > 1
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(c.chunk_id.startswith(document_key(document)) for c in chunks)


def test_chunks_respect_the_size_limit():
    document = RegulationDocument(
        source="income.txt",
        text="\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(8)),
        scheme_name="Scheme",
    )
    chunks = chunk_document(document, chunk_size=400, overlap=50)
    assert chunks
    # A little slack for the joined overlap text.
    assert all(len(chunk.text) <= 500 for chunk in chunks)


def test_chunking_keeps_the_section_of_each_chunk():
    document = RegulationDocument(
        source="income.txt",
        text=(
            "Section 1. Eligibility\nIncome below 2,50,000.\n\n"
            "Section 2. Required Documents\nProof of identity is required.\n\n"
            "Section 3. Appeals\nAppeal within sixty days."
        ),
        scheme_name="Income Certificate Scheme",
    )
    chunks = chunk_document(document, chunk_size=200, overlap=20)
    sections = {chunk.section for chunk in chunks}
    assert sections == {"Section 1", "Section 2", "Section 3"}

    documents_chunk = next(c for c in chunks if "identity" in c.text)
    assert documents_chunk.section == "Section 2"


# --- 3. metadata preservation ----------------------------------------------


def test_metadata_survives_chunking():
    document = RegulationDocument(
        source="income.txt",
        text="Section 2. Required Documents\nProof of income is required.",
        scheme_name="Income Certificate Scheme",
        department="Revenue",
        circular_reference="CIRC/2026/11",
        regulation_id=7,
    )
    chunk = chunk_document(document)[0]

    assert chunk.scheme_name == "Income Certificate Scheme"
    assert chunk.department == "Revenue"
    assert chunk.circular_reference == "CIRC/2026/11"
    assert chunk.regulation_id == 7
    assert chunk.source == "income.txt"
    assert chunk.section == "Section 2"


def test_metadata_leaves_out_missing_fields_instead_of_inventing_them():
    chunk = RegulationChunk(
        chunk_id="c-1",
        text="text",
        source="income.txt",
        scheme_name="Scheme",
        chunk_index=0,
    )
    metadata = chunk.as_metadata()

    assert metadata == {
        "source": "income.txt",
        "scheme_name": "Scheme",
        "chunk_index": 0,
    }
    # ChromaDB rejects None values, and a made-up section would be worse.
    assert "section" not in metadata
    assert "circular_reference" not in metadata
    assert None not in metadata.values()


# --- 4. ChromaDB ------------------------------------------------------------


@pytest.fixture
def vector_store(tmp_path):
    pytest.importorskip("chromadb")
    return RegulationVectorStore(tmp_path / "chroma", "test_regulations")


def ingest_sample(store, text, source="income.txt", **kwargs):
    kwargs.setdefault("scheme_name", "Income Certificate Scheme")
    document = RegulationDocument(source=source, text=text, **kwargs)
    chunks = chunk_document(document, chunk_size=300, overlap=30)
    embeddings = [fake_vector(chunk.text) for chunk in chunks]
    store.replace_document(source, chunks, embeddings)
    return chunks


def test_chunks_can_be_stored_and_retrieved(vector_store):
    ingest_sample(
        vector_store,
        "Section 2. Required Documents\nProof of income and proof of identity.\n\n"
        "Section 4. Processing Time\nApplications finish in fifteen working days.",
        scheme_name="Income Certificate Scheme",
        department="Revenue",
        circular_reference="CIRC/2026/11",
    )

    results = vector_store.search(fake_vector("required documents proof income"), top_k=2)
    assert results
    assert "proof of income" in results[0].text.lower()
    assert results[0].metadata["scheme_name"] == "Income Certificate Scheme"
    assert results[0].metadata["circular_reference"] == "CIRC/2026/11"
    assert results[0].metadata["section"] == "Section 2"


def test_re_ingesting_the_same_document_does_not_duplicate(vector_store):
    text = "Section 1. Eligibility\nIncome below 2,50,000 rupees."
    ingest_sample(vector_store, text)
    after_first = vector_store.count()

    ingest_sample(vector_store, text)
    assert vector_store.count() == after_first


def test_re_ingesting_a_shorter_document_removes_old_chunks(vector_store):
    ingest_sample(
        vector_store,
        "Section 1. Eligibility\n" + "word " * 200 + "\n\nSection 2. Documents\nProof.",
    )
    assert vector_store.count() > 1

    ingest_sample(vector_store, "Section 1. Eligibility\nShort version.")
    assert vector_store.count() == 1


def test_search_with_no_results_is_empty(vector_store):
    assert vector_store.search(fake_vector("anything"), top_k=0) == []


# --- 5. knowledge graph -----------------------------------------------------

GRAPH_RECORDS = [
    {
        "scheme_name": "Income Certificate Scheme",
        "department": "Revenue",
        "eligibility_criteria": "Annual income below 2,50,000; Resident for one year",
        "required_documents": "Aadhaar, Income Proof",
        "circular_reference": "CIRC/2026/11",
    },
    {
        "scheme_name": "Old Age Pension",
        "department": "Social Welfare",
        "required_documents": "Age Proof",
    },
]


def test_graph_links_schemes_to_departments_documents_and_circulars():
    pytest.importorskip("networkx")
    graph = build_graph(GRAPH_RECORDS)

    assert graph.nodes["Income Certificate Scheme"]["kind"] == "scheme"
    assert graph.nodes["Revenue"]["kind"] == "department"
    assert graph.has_edge("Income Certificate Scheme", "Revenue")
    assert graph.has_edge("Income Certificate Scheme", "Aadhaar")
    assert graph.has_edge("Income Certificate Scheme", "Income Proof")
    assert graph.has_edge("Income Certificate Scheme", "CIRC/2026/11")
    assert graph.has_edge("Old Age Pension", "Social Welfare")


def test_graph_skips_records_without_a_scheme_name():
    pytest.importorskip("networkx")
    graph = build_graph([{"department": "Revenue"}, {"scheme_name": ""}])
    assert graph.number_of_nodes() == 0


def test_graph_context_describes_only_known_schemes():
    pytest.importorskip("networkx")
    graph = build_graph(GRAPH_RECORDS)

    lines = graph_context(graph, ["Income Certificate Scheme", "Unknown Scheme"])
    assert any("handled by the Revenue department" in line for line in lines)
    assert any("requires the document: Aadhaar" in line for line in lines)
    assert not any("Unknown Scheme" in line for line in lines)


def test_graph_context_is_empty_before_the_graph_is_built():
    assert KnowledgeGraphService().context_for(["Anything"]) == []


# --- 6. reranking -----------------------------------------------------------


def test_reranking_orders_by_relevance():
    reranker = RerankerService("fake", model=FakeCrossEncoder())
    candidates = [
        make_candidate("Appeals must be filed within sixty days.", chunk_id="a"),
        make_candidate("Proof of income and proof of identity are required.", chunk_id="b"),
    ]

    ranked = reranker.rerank("which documents prove income", candidates)
    assert [item.chunk.chunk_id for item in ranked] == ["b", "a"]
    assert ranked[0].score >= ranked[1].score


def test_reranking_an_empty_candidate_list():
    reranker = RerankerService("fake", model=FakeCrossEncoder())
    assert reranker.rerank("anything", []) == []


def test_reranker_failure_is_reported_clearly():
    class BrokenModel:
        def predict(self, pairs):
            raise RuntimeError("model file is corrupt")

    reranker = RerankerService("fake", model=BrokenModel())
    with pytest.raises(RerankerUnavailableError, match="failed to score"):
        reranker.rerank("query", [make_candidate("text")])


def test_missing_reranker_package_is_reported_clearly(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", None)
    with pytest.raises(RerankerUnavailableError):
        RerankerService("cross-encoder/does-not-exist").rerank(
            "query", [make_candidate("text")]
        )


# --- 7 & 8. the pipeline and grounded answers -------------------------------

EVIDENCE_METADATA = {
    "scheme_name": "Income Certificate Scheme",
    "circular_reference": "CIRC/2026/11",
    "section": "Section 3",
    "source": "income.txt",
    "regulation_id": 7,
}


def test_pipeline_answers_from_the_retrieved_evidence():
    llm = FakeLlm("Submit proof of identity, residence and income (Section 3).")
    pipeline = build_pipeline(
        [make_candidate("Proof of income is required.", **EVIDENCE_METADATA)], llm=llm
    )

    result = pipeline.answer("which documents prove income")

    assert result.insufficient_evidence is False
    assert result.answer.startswith("Submit proof")
    assert result.evidence_count == 1
    assert llm.calls, "the LLM should be asked once there is real evidence"


def test_pipeline_sends_only_the_top_chunks_to_the_llm():
    llm = FakeLlm()
    candidates = [
        make_candidate(f"Proof of income document {i}", chunk_id=f"c{i}", **EVIDENCE_METADATA)
        for i in range(6)
    ]
    pipeline = build_pipeline(candidates, llm=llm, rerank_top_k=2, top_k=5)

    pipeline.answer("proof of income")

    assert pipeline.vector_store.searches == [5]
    assert len(llm.calls[0]["evidence"]) == 2


def test_pipeline_passes_knowledge_graph_context_to_the_llm():
    pytest.importorskip("networkx")
    llm = FakeLlm()
    pipeline = build_pipeline(
        [make_candidate("Proof of income is required.", **EVIDENCE_METADATA)], llm=llm
    )
    pipeline.knowledge_graph.refresh(GRAPH_RECORDS)

    pipeline.answer("which documents prove income")

    context = llm.calls[0]["graph_context"]
    assert any("Revenue department" in line for line in context)


# --- 9. citations -----------------------------------------------------------


def test_citations_come_from_the_stored_metadata():
    pipeline = build_pipeline(
        [make_candidate("Proof of income is required.", **EVIDENCE_METADATA)]
    )
    result = pipeline.answer("which documents prove income")

    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.scheme_name == "Income Certificate Scheme"
    assert citation.circular_reference == "CIRC/2026/11"
    assert citation.section == "Section 3"
    assert citation.source == "income.txt"
    assert citation.regulation_id == 7
    assert result.primary_regulation_id == 7


def test_missing_citation_fields_stay_empty_rather_than_invented():
    pipeline = build_pipeline(
        [
            make_candidate(
                "Proof of income is required.",
                scheme_name="Unlabelled Scheme",
                source="notes.txt",
            )
        ]
    )
    citation = pipeline.answer("proof of income").citations[0]

    assert citation.scheme_name == "Unlabelled Scheme"
    assert citation.circular_reference is None
    assert citation.section is None
    assert citation.regulation_id is None


def test_duplicate_citations_are_merged():
    candidates = [
        make_candidate("Proof of income part one.", chunk_id="a", **EVIDENCE_METADATA),
        make_candidate("Proof of income part two.", chunk_id="b", **EVIDENCE_METADATA),
    ]
    pipeline = build_pipeline(candidates, rerank_top_k=2)

    result = pipeline.answer("proof of income")
    assert result.evidence_count == 2
    assert len(result.citations) == 1


# --- 10. insufficient evidence ---------------------------------------------


def test_no_candidates_means_no_llm_call():
    llm = FakeLlm()
    pipeline = build_pipeline([], llm=llm)

    result = pipeline.answer("what is the moon made of")

    assert result.insufficient_evidence is True
    assert result.answer == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.citations == []
    assert llm.calls == []


def test_weak_evidence_means_no_llm_call():
    """Below the score threshold the LLM is never asked to guess."""
    llm = FakeLlm()
    pipeline = build_pipeline(
        [make_candidate("Unrelated text about parking permits.", **EVIDENCE_METADATA)],
        llm=llm,
        cross_encoder=FakeCrossEncoder(fixed_scores=[-4.0]),
        min_score=0.5,
    )

    result = pipeline.answer("which documents prove income")

    assert result.insufficient_evidence is True
    assert result.answer == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.citations == []
    assert llm.calls == []


def test_the_threshold_is_configurable():
    """The same weak evidence is accepted when the threshold allows it."""
    llm = FakeLlm()
    candidates = [make_candidate("Parking permit rules.", **EVIDENCE_METADATA)]
    pipeline = build_pipeline(
        candidates,
        llm=llm,
        cross_encoder=FakeCrossEncoder(fixed_scores=[-4.0]),
        min_score=-10.0,
    )

    assert pipeline.answer("anything").insufficient_evidence is False


def test_llm_reporting_insufficient_context_is_passed_through():
    pipeline = build_pipeline(
        [make_candidate("Proof of income is required.", **EVIDENCE_METADATA)],
        llm=FakeLlm(INSUFFICIENT_MARKER),
    )
    result = pipeline.answer("what are the parking fees")

    assert result.insufficient_evidence is True
    assert result.answer == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.citations == []


def test_an_empty_question_is_not_sent_anywhere():
    llm = FakeLlm()
    pipeline = build_pipeline([make_candidate("text", **EVIDENCE_METADATA)], llm=llm)

    assert pipeline.answer("   ").insufficient_evidence is True
    assert llm.calls == []


# --- prompt and Groq configuration -----------------------------------------


def test_the_prompt_tells_the_model_not_to_invent_anything():
    from ai_modules.regulation_rag.llm_service import SYSTEM_PROMPT

    lowered = SYSTEM_PROMPT.lower()
    assert "only from the regulation context" in lowered
    assert "never invent eligibility criteria" in lowered
    assert INSUFFICIENT_MARKER in SYSTEM_PROMPT


def test_the_prompt_contains_the_question_evidence_and_citations():
    evidence = [
        RankedChunk(
            chunk=make_candidate("Proof of income is required.", **EVIDENCE_METADATA),
            score=3.0,
        )
    ]
    prompt = build_user_prompt(
        "which documents prove income", evidence, ["Scheme is handled by Revenue."]
    )

    assert "which documents prove income" in prompt
    assert "Proof of income is required." in prompt
    assert "CIRC/2026/11" in prompt
    assert "Section: Section 3" in prompt
    assert "handled by Revenue" in prompt


def test_long_chunks_are_trimmed_before_going_to_the_llm():
    from ai_modules.regulation_rag.llm_service import MAX_CHARS_PER_CHUNK

    evidence = [
        RankedChunk(chunk=make_candidate("word " * 2000, **EVIDENCE_METADATA), score=1.0)
    ]
    prompt = build_user_prompt("query", evidence, [])
    assert len(prompt) < MAX_CHARS_PER_CHUNK + 1000


def test_groq_needs_a_configured_api_key():
    service = GroqLlmService(api_key="", model="llama-3.1-8b-instant")
    with pytest.raises(LlmUnavailableError, match="GROQ_API_KEY is not configured"):
        _ = service.client


def test_groq_key_comes_from_configuration_not_the_source():
    """No API key may be hard-coded anywhere in the project's source."""
    suspicious = []
    for folder in ("ai_modules", "backend", "frontend"):
        for path in (PROJECT_ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "gsk_" in text:
                suspicious.append(path.name)
    assert suspicious == []

    config = RagConfig()
    assert config.groq_api_key == ""


def test_groq_answer_uses_the_configured_model():
    captured = {}

    def create(model, messages, temperature):
        captured["model"] = model
        captured["messages"] = messages
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" Answer text "))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    service = GroqLlmService(api_key="unused", model="test-model", client=client)
    evidence = [
        RankedChunk(chunk=make_candidate("Proof of income.", **EVIDENCE_METADATA), score=2.0)
    ]

    answer = service.generate_answer("query", evidence, [])

    assert answer == "Answer text"
    assert captured["model"] == "test-model"
    assert captured["messages"][0]["role"] == "system"


def test_groq_failures_do_not_leak_the_key():
    def create(**kwargs):
        raise RuntimeError("401 invalid api key gsk_secret_value")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    service = GroqLlmService(api_key="gsk_secret_value", model="m", client=client)
    evidence = [RankedChunk(chunk=make_candidate("text", **EVIDENCE_METADATA), score=1.0)]

    with pytest.raises(LlmUnavailableError) as error:
        service.generate_answer("query", evidence, [])
    assert "gsk_secret_value" not in str(error.value)


# --- ingestion through the pipeline -----------------------------------------


def test_pipeline_ingests_documents_into_the_vector_store(tmp_path):
    pytest.importorskip("chromadb")
    store = RegulationVectorStore(tmp_path / "chroma", "ingest_test")
    pipeline = RegulationRagPipeline(
        config=RagConfig(chunk_size=300, chunk_overlap=30),
        embedder=EmbeddingService("fake", encoder=FakeEncoder()),
        vector_store=store,
        reranker=RerankerService("fake", model=FakeCrossEncoder()),
        llm=FakeLlm(),
    )
    document = RegulationDocument(
        source="income.txt",
        text="Section 2. Required Documents\nProof of income is required.",
        scheme_name="Income Certificate Scheme",
        department="Revenue",
        circular_reference="CIRC/2026/11",
    )

    stored = pipeline.ingest_documents([document])

    assert stored == {"income.txt": 1}
    assert store.count() == 1

    result = pipeline.answer("which documents prove income")
    assert result.insufficient_evidence is False
    assert result.citations[0].circular_reference == "CIRC/2026/11"
