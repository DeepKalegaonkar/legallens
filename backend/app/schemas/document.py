from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus
from app.schemas.clause import ClauseOut


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: DocumentStatus
    uploaded_at: datetime


class RiskSummary(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class DocumentListItem(DocumentOut):
    """A document plus what the dashboard needs to preview it without opening the report."""

    clause_count: int = 0
    preview: str = ""
    # Findings from the named risk categories, and how many more clauses only the general model flagged.
    key_findings: RiskSummary = Field(default_factory=RiskSummary)
    other_flags: int = 0


class DocumentDetail(DocumentOut):
    clauses: list[ClauseOut]
    risk_summary: RiskSummary
