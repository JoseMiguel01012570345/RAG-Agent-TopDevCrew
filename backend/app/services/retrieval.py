import uuid
from dataclasses import dataclass
from datetime import datetime

from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.embeddings import build_embedder, embed_texts, to_pgvector
from app.services.textutil import lexical_query

RRF_K = 60


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page: int
    text: str
    uploaded_at: datetime
    score: float
    similarity: float
    lexical: bool


def reciprocal_rank_fusion(
    rankings: list[list[uuid.UUID]],
    k: int = RRF_K,
) -> list[tuple[uuid.UUID, float]]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def retrieve(
    session: Session,
    community_id: uuid.UUID,
    question: str,
    embedder=None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    embedder = embedder or build_embedder(settings)
    tracer = trace.get_tracer("faro")
    with tracer.start_as_current_span("rag.retrieve") as span:
        span.set_attribute("faro.community_id", str(community_id))
        embedding = embed_texts(embedder, [question])[0]
        vector_rows = _vector_search(session, community_id, embedding, settings.retrieval_top_k)
        lexical_rows = _lexical_search(session, community_id, question, settings.retrieval_top_k)
        similarity = {row["id"]: float(row["similarity"]) for row in vector_rows}
        lexical_ids = [row["id"] for row in lexical_rows]
        vector_ids = [row["id"] for row in vector_rows]
        fused = reciprocal_rank_fusion([vector_ids, lexical_ids])
        payloads = {row["id"]: row for row in vector_rows}
        missing = [chunk_id for chunk_id, _ in fused if chunk_id not in payloads]
        payloads.update(_load_chunks(session, community_id, missing))
        lexical_set = set(lexical_ids)
        selected: list[RetrievedChunk] = []
        for chunk_id, score in fused:
            row = payloads.get(chunk_id)
            if row is None:
                continue
            cosine = similarity.get(chunk_id, 0.0)
            is_lexical = chunk_id in lexical_set
            if not is_lexical and cosine < settings.min_cosine_similarity:
                continue
            selected.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=row["document_id"],
                    document_name=row["filename"],
                    page=int(row["page"]),
                    text=row["text"],
                    uploaded_at=row["uploaded_at"],
                    score=score,
                    similarity=cosine,
                    lexical=is_lexical,
                )
            )
            if len(selected) >= settings.retrieval_top_k:
                break
        span.set_attribute("rag.chunk_count", len(selected))
        span.set_attribute("rag.lexical_hits", len(lexical_ids))
        return selected


def _vector_search(
    session: Session,
    community_id: uuid.UUID,
    embedding: list[float],
    limit: int,
) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT c.id AS id,
                   c.document_id AS document_id,
                   c.page AS page,
                   c.text AS text,
                   d.filename AS filename,
                   d.created_at AS uploaded_at,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.community_id = :community_id
              AND d.status = 'ready'
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ),
        {
            "embedding": to_pgvector(embedding),
            "community_id": community_id,
            "limit": limit,
        },
    ).mappings()
    return [dict(row) for row in rows]


def _lexical_search(
    session: Session,
    community_id: uuid.UUID,
    question: str,
    limit: int,
) -> list[dict]:
    query = lexical_query(question)
    if query is None:
        return []
    try:
        with session.begin_nested():
            rows = session.execute(
                text(
                    """
                    SELECT c.id AS id,
                           ts_rank(c.tsv, to_tsquery('spanish', :query)) AS rank
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.community_id = :community_id
                      AND d.status = 'ready'
                      AND c.tsv @@ to_tsquery('spanish', :query)
                    ORDER BY rank DESC
                    LIMIT :limit
                    """
                ),
                {"query": query, "community_id": community_id, "limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
    except Exception:
        return []


def _load_chunks(session: Session, community_id: uuid.UUID, ids: list[uuid.UUID]) -> dict:
    if not ids:
        return {}
    params: dict = {"community_id": community_id}
    placeholders = []
    for index, chunk_id in enumerate(ids):
        key = f"id_{index}"
        placeholders.append(f":{key}")
        params[key] = chunk_id
    sql = f"""
        SELECT c.id AS id,
               c.document_id AS document_id,
               c.page AS page,
               c.text AS text,
               d.filename AS filename,
               d.created_at AS uploaded_at
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.community_id = :community_id
          AND d.status = 'ready'
          AND c.id IN ({", ".join(placeholders)})
    """
    rows = session.execute(text(sql), params).mappings()
    return {row["id"]: dict(row) for row in rows}
