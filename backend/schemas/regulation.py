"""Pydantic schemas for regulations (government schemes)."""

from pydantic import BaseModel, ConfigDict, Field


class RegulationCreate(BaseModel):
    """Fields an administrator provides when registering a scheme."""

    scheme_name: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=120)
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
