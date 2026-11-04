import logging
import uuid
from datetime import UTC, datetime

from opentelemetry import trace
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import EMBEDDING_DIM, get_settings
from app.db import SessionLocal
from app.models import Chunk, Document
from app.services.chunking import chunk_document
from app.services.embeddings import build_embedder, embed_texts
from app.services.parsing import PermanentIngestionError, parse_document

log = logging.getLogger("faro.ingest")


def run_ingestion(document_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    tracer = trace.get_tracer("faro")
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            log.warning("ingest.missing document_id=%s", document_id)
            return
        document.status = "processing"
        document.error_code = None
        document.error_message = None
        document.updated_at = datetime.now(UTC)
        db.commit()
        with tracer.start_as_current_span("rag.ingest") as span:
            span.set_attribute("faro.document_id", document_id)
            span.set_attribute("faro.community_id", str(document.community_id))
            pages = parse_document(
                document.content,
                document.content_type,
                document.filename,
                settings.max_pages,
            )
            drafts = chunk_document(pages, settings.chunk_size, settings.chunk_overlap)
            if not drafts:
                raise PermanentIngestionError(
                    "no_text_layer",
                    "El documento no produjo texto utilizable.",
                )
            embedder = build_embedder(settings)
            vectors = embed_texts(embedder, [draft.text for draft in drafts])
            if len(vectors) != len(drafts) or any(
                len(vector) != EMBEDDING_DIM for vector in vectors
            ):
                raise RuntimeError("Los embeddings no coinciden con los fragmentos")
            span.set_attribute("gen_ai.request.model", embedder.model)
            rewrite_chunks(db, document, drafts, vectors)
            document.status = "ready"
            document.page_count = len(pages)
            document.updated_at = datetime.now(UTC)
            db.commit()
            span.set_attribute("rag.chunk_count", len(drafts))
            span.set_attribute("rag.page_count", len(pages))
            log.info(
                "ingest.ready document_id=%s chunks=%s pages=%s model=%s",
                document_id,
                len(drafts),
                len(pages),
                embedder.model,
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def rewrite_chunks(session: Session, document: Document, drafts, vectors) -> None:
    session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    for index, (draft, vector) in enumerate(zip(drafts, vectors, strict=True)):
        session.add(
            Chunk(
                community_id=document.community_id,
                document_id=document.id,
                page=draft.page,
                chunk_index=index,
                text=draft.text,
                embedding=vector,
            )
        )
    session.flush()


def mark_failed(document_id: str, code: str, message: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            return
        document.status = "failed"
        document.error_code = code
        document.error_message = message
        document.updated_at = datetime.now(UTC)
        db.commit()
        log.info("ingest.failed document_id=%s code=%s", document_id, code)
    finally:
        db.close()
