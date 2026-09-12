"""Pydantic schemas for regulations (government schemes)."""

from pydantic import BaseModel, ConfigDict, Field


class RegulationCreate(BaseModel):
    """Fields an administrator provides when registering a scheme."""

    scheme_name: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=120)
    eligibility_criteria: str | None = None
    required_documents: str | None = None
    circular_reference: str | None = Field(default=None, max_length=200)


class RegulationUpdate(BaseModel):
    """Partial update of a stored scheme. Omitted fields stay unchanged."""

    model_config = ConfigDict(extra="forbid")

    scheme_name: str | None = Field(default=None, min_length=1, max_length=200)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    eligibility_criteria: str | None = None
    required_documents: str | None = None
    circular_reference: str | None = Field(default=None, max_length=200)


class RegulationRead(BaseModel):
    """A stored regulation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    regulation_id: int
    scheme_name: str
    department: str
    eligibility_criteria: str | None
    required_documents: str | None
    circular_reference: str | None


class RegulationQuery(BaseModel):
    """A citizen's question.

    There is no citizen_id here on purpose: the owner of the query is taken
    from the JWT, never from the request body.
    """

    query: str = Field(min_length=3, max_length=1000)


class Citation(BaseModel):
    """Where part of an answer came from. Absent fields stay null."""

    model_config = ConfigDict(from_attributes=True)

    scheme_name: str | None = None
    circular_reference: str | None = None
    section: str | None = None
    source: str | None = None
    regulation_id: int | None = None


class RegulationAnswer(BaseModel):
    """A grounded answer from the Regulation RAG Assistant."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = False
    evidence_count: int = 0


class RegulationIngestResult(BaseModel):
    """What an ingestion run stored."""

    documents: int
    chunks: int
    chunks_per_document: dict[str, int] = Field(default_factory=dict)
