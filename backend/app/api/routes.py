import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Community, Document, Membership, User
from app.schemas import AnswerResponse, CommunityCreate, CommunityOut, DocumentOut, QuestionIn
from app.services.answering import answer_question
from app.services.uploads import USER_ID_RE, UploadRejected, validate_upload
from app.tasks import ingest_document

router = APIRouter()


def get_current_user(
    db: Session = Depends(get_db),
    x_user_id: Annotated[str | None, Header()] = None,
) -> User:
    if x_user_id is None or USER_ID_RE.fullmatch(x_user_id.strip()) is None:
        raise HTTPException(status_code=401, detail="Cabecera X-User-Id inválida o ausente")
    external_id = x_user_id.strip()
    user = db.scalar(select(User).where(User.external_id == external_id))
    if user is None:
        user = User(external_id=external_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def require_community(community_id: uuid.UUID, user: User, db: Session) -> Community:
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.community_id == community_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    community = db.get(Community, community_id)
    if community is None:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    return community


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok"}


@router.post("/communities", response_model=CommunityOut, status_code=201)
def create_community(
    body: CommunityCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Community:
    community = Community(name=body.name)
    db.add(community)
    db.flush()
    db.add(Membership(user_id=user.id, community_id=community.id, role="admin"))
    db.commit()
    db.refresh(community)
    return community


@router.get("/communities", response_model=list[CommunityOut])
def list_communities(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Community]:
    rows = db.scalars(
        select(Community)
        .join(Membership, Membership.community_id == Community.id)
        .where(Membership.user_id == user.id)
        .order_by(Community.created_at.desc())
    )
    return list(rows)


@router.post("/communities/{community_id}/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    community_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    require_community(community_id, user, db)
    payload = file.file.read()
    settings = get_settings()
    try:
        filename, content_type = validate_upload(
            file.filename,
            file.content_type,
            payload,
            settings.max_upload_bytes,
        )
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    digest = hashlib.sha256(payload).hexdigest()
    existing = db.scalar(
        select(Document).where(
            Document.community_id == community_id,
            Document.sha256 == digest,
        )
    )
    if existing is not None and existing.status != "failed":
        return existing

    if existing is None:
        document = Document(
            community_id=community_id,
            filename=filename,
            content_type=content_type,
            sha256=digest,
            content=payload,
            status="pending",
        )
        db.add(document)
    else:
        document = existing
        document.status = "pending"
        document.error_code = None
        document.error_message = None
        document.filename = filename
        document.content_type = content_type
        document.content = payload
        document.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(document)
    ingest_document.delay(str(document.id))
    db.refresh(document)
    return document


@router.get("/communities/{community_id}/documents", response_model=list[DocumentOut])
def list_documents(
    community_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Document]:
    require_community(community_id, user, db)
    rows = db.scalars(
        select(Document)
        .where(Document.community_id == community_id)
        .order_by(Document.created_at.desc())
    )
    return list(rows)


@router.delete("/communities/{community_id}", status_code=204)
def delete_community(
    community_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    community = require_community(community_id, user, db)
    db.delete(community)
    db.commit()


@router.delete("/communities/{community_id}/documents/{document_id}", status_code=204)
def delete_document(
    community_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_community(community_id, user, db)
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.community_id == community_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    db.delete(document)
    db.commit()


@router.get("/communities/{community_id}/documents/{document_id}", response_model=DocumentOut)
def get_document(
    community_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    require_community(community_id, user, db)
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.community_id == community_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document


@router.post("/communities/{community_id}/questions", response_model=AnswerResponse)
def ask_question(
    community_id: uuid.UUID,
    body: QuestionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnswerResponse:
    require_community(community_id, user, db)
    return answer_question(db, community_id, body.question)
