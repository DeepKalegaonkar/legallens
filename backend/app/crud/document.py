from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.analysis import AnalysisHistory
from app.models.clause import Clause
from app.models.document import Document, DocumentStatus
from app.models.risk_finding import RiskFinding
from app.services.nlp.base import ClauseResult
from app.services.nlp.risk_taxonomy import GENERAL_RISK_TYPE

PREVIEW_CHARS = 280


def create_document(db: Session, owner_id: int, filename: str) -> Document:
    document = Document(owner_id=owner_id, filename=filename, status=DocumentStatus.PROCESSING)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def save_analysis_results(db: Session, document: Document, clause_results: list[ClauseResult]) -> Document:
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for index, clause_result in enumerate(clause_results):
        clause = Clause(
            document_id=document.id,
            order_index=index,
            text=clause_result.text,
            clause_type=clause_result.clause_type,
            confidence=clause_result.confidence,
        )
        db.add(clause)
        db.flush()

        for risk in clause_result.risks:
            db.add(
                RiskFinding(
                    clause_id=clause.id,
                    risk_type=risk.risk_type,
                    severity=risk.severity,
                    confidence=risk.confidence,
                    explanation=risk.explanation,
                    source=risk.source,
                )
            )
            risk_counts[risk.severity.value] += 1

    document.status = DocumentStatus.COMPLETED
    db.add(
        AnalysisHistory(
            document_id=document.id,
            status=DocumentStatus.COMPLETED,
            risk_summary=risk_counts,
        )
    )
    db.commit()
    db.refresh(document)
    return document


def mark_document_failed(db: Session, document: Document) -> None:
    document.status = DocumentStatus.FAILED
    db.add(AnalysisHistory(document_id=document.id, status=DocumentStatus.FAILED, risk_summary=None))
    db.commit()


def get_documents_for_user(db: Session, owner_id: int) -> list[Document]:
    return (
        db.query(Document)
        .filter(Document.owner_id == owner_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def get_document_for_user(db: Session, document_id: int, owner_id: int) -> Document | None:
    return (
        db.query(Document)
        .options(joinedload(Document.clauses).joinedload(Clause.risks))
        .filter(Document.id == document_id, Document.owner_id == owner_id)
        .first()
    )


def get_latest_risk_summary(document: Document) -> dict:
    if not document.analyses:
        return {"low": 0, "medium": 0, "high": 0, "critical": 0}
    latest = max(document.analyses, key=lambda a: a.started_at)
    return latest.risk_summary or {"low": 0, "medium": 0, "high": 0, "critical": 0}


def get_list_summaries(db: Session, document_ids: list[int]) -> dict[int, dict]:
    """Clause count, opening text and risk counts for each document, in a few grouped queries."""
    if not document_ids:
        return {}

    summaries = {
        document_id: {"clause_count": 0, "preview": "", "key_findings": {}, "other_flags": 0}
        for document_id in document_ids
    }

    counts = (
        db.query(Clause.document_id, func.count(Clause.id))
        .filter(Clause.document_id.in_(document_ids))
        .group_by(Clause.document_id)
        .all()
    )
    for document_id, count in counts:
        summaries[document_id]["clause_count"] = count

    opening = (
        db.query(Clause.document_id, Clause.text)
        .filter(Clause.document_id.in_(document_ids), Clause.order_index < 2)
        .order_by(Clause.document_id, Clause.order_index)
        .all()
    )
    for document_id, text in opening:
        preview = f"{summaries[document_id]['preview']} {text}".strip()
        summaries[document_id]["preview"] = preview[:PREVIEW_CHARS]

    is_general = (RiskFinding.risk_type == GENERAL_RISK_TYPE).label("is_general")
    findings = (
        db.query(Clause.document_id, RiskFinding.severity, is_general, func.count(RiskFinding.id))
        .join(RiskFinding, RiskFinding.clause_id == Clause.id)
        .filter(Clause.document_id.in_(document_ids))
        .group_by(Clause.document_id, RiskFinding.severity, is_general)
        .all()
    )
    for document_id, severity, general, count in findings:
        if general:
            summaries[document_id]["other_flags"] += count
        else:
            summaries[document_id]["key_findings"][severity.value] = count
    return summaries
