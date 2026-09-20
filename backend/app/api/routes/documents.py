from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_clause_analyzer, get_current_user
from app.crud.document import (
    create_document,
    get_document_for_user,
    get_documents_for_user,
    get_latest_risk_summary,
    get_list_summaries,
    mark_document_failed,
    save_analysis_results,
)
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentDetail, DocumentListItem, RiskSummary
from app.services.document_parser import SUPPORTED_EXTENSIONS, UnsupportedFileTypeError, extract_text
from app.services.nlp.base import ClauseAnalyzer

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_detail(document: Document) -> DocumentDetail:
    return DocumentDetail(
        id=document.id,
        filename=document.filename,
        status=document.status,
        uploaded_at=document.uploaded_at,
        clauses=document.clauses,
        risk_summary=RiskSummary(**get_latest_risk_summary(document)),
    )


@router.post("/upload", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analyzer: ClauseAnalyzer = Depends(get_clause_analyzer),
) -> DocumentDetail:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A filename is required")

    extension = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    file_bytes = file.file.read()
    document = create_document(db, owner_id=current_user.id, filename=file.filename)

    try:
        text = extract_text(file.filename, file_bytes)
        clause_results = analyzer.analyze(text)
        document = save_analysis_results(db, document, clause_results)
    except (UnsupportedFileTypeError, ValueError):
        mark_document_failed(db, document)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not parse document")

    return _to_detail(document)


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DocumentListItem]:
    documents = get_documents_for_user(db, owner_id=current_user.id)
    summaries = get_list_summaries(db, [document.id for document in documents])
    return [
        DocumentListItem.model_validate(document).model_copy(
            update={**summaries[document.id], "key_findings": RiskSummary(**summaries[document.id]["key_findings"])}
        )
        for document in documents
    ]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    document = get_document_for_user(db, document_id=document_id, owner_id=current_user.id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_detail(document)
