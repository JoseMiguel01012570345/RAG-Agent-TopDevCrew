from uuid import UUID

from sqlalchemy import func, select

from app.models import Chunk, Document
from app.services.ingestion import rewrite_chunks, run_ingestion
from tests.pdfutil import build_pdf


def _create_community(client, user: str, name: str) -> str:
    response = client.post("/communities", headers={"X-User-Id": user}, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(client, user: str, community_id: str, filename: str, payload: bytes, media: str):
    response = client.post(
        f"/communities/{community_id}/documents",
        headers={"X-User-Id": user},
        files={"file": (filename, payload, media)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_missing_user_is_rejected(client):
    response = client.post("/communities", json={"name": "Alameda"})
    assert response.status_code == 401


def test_text_ingestion_is_ready_and_idempotent(client, db):
    community_id = _create_community(client, "ana", "Alameda")
    payload = "Se aprobó la reparación del ascensor en marzo.".encode()
    first = _upload(client, "ana", community_id, "acta.txt", payload, "text/plain")
    assert first["status"] == "ready"
    assert first["page_count"] == 1
    second = _upload(client, "ana", community_id, "acta.txt", payload, "text/plain")
    assert second["id"] == first["id"]
    count = db.scalar(select(func.count()).select_from(Chunk))
    assert count == 1
    run_ingestion(first["id"])
    again = db.scalar(select(func.count()).select_from(Chunk))
    assert again == 1


def test_failed_upload_can_be_reingested(client, monkeypatch):
    community_id = _create_community(client, "ana", "Roble")
    calls: list[str] = []
    from app.tasks import ingest_document

    original = ingest_document.delay

    def wrapped(document_id: str):
        calls.append(document_id)
        return original(document_id)

    monkeypatch.setattr("app.api.routes.ingest_document.delay", wrapped)
    payload = b"%PDF-1.4 esto no es un pdf"
    first = _upload(client, "ana", community_id, "roto.pdf", payload, "application/pdf")
    assert first["status"] == "failed"
    assert first["error_code"] == "corrupt_pdf"
    second = _upload(client, "ana", community_id, "otra-copia.pdf", payload, "application/pdf")
    assert second["id"] != first["id"]
    assert second["filename"] == "otra-copia.pdf"
    assert second["status"] == "failed"
    listing = client.get(
        f"/communities/{community_id}/documents",
        headers={"X-User-Id": "ana"},
    )
    assert {item["id"] for item in listing.json()} == {first["id"], second["id"]}
    assert calls == [first["id"], second["id"]]


def test_distinct_failed_pdfs_stay_in_the_list(client):
    community_id = _create_community(client, "ana", "Dos fallos")
    first = _upload(
        client,
        "ana",
        community_id,
        "acta-a.pdf",
        b"%PDF-1.4 documento alfa sin estructura",
        "application/pdf",
    )
    second = _upload(
        client,
        "ana",
        community_id,
        "acta-b.pdf",
        b"%PDF-1.4 documento beta distinto",
        "application/pdf",
    )
    assert first["status"] == "failed"
    assert second["status"] == "failed"
    assert first["id"] != second["id"]
    listing = client.get(
        f"/communities/{community_id}/documents",
        headers={"X-User-Id": "ana"},
    )
    assert {item["filename"] for item in listing.json()} == {"acta-a.pdf", "acta-b.pdf"}


def test_blank_pdf_fails_with_no_text_layer(client):
    community_id = _create_community(client, "ana", "Olmo")
    document = _upload(
        client,
        "ana",
        community_id,
        "vacio.pdf",
        build_pdf([""]),
        "application/pdf",
    )
    assert document["status"] == "failed"
    assert document["error_code"] == "no_text_layer"


def test_too_many_pages_fails(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings().model_copy(update={"max_pages": 1})
    monkeypatch.setattr("app.services.ingestion.get_settings", lambda: settings)
    community_id = _create_community(client, "ana", "Pino")
    document = _upload(
        client,
        "ana",
        community_id,
        "largo.pdf",
        build_pdf(["uno", "dos"]),
        "application/pdf",
    )
    assert document["status"] == "failed"
    assert document["error_code"] == "too_many_pages"


def test_question_cites_the_page_that_contains_the_fact(client):
    community_id = _create_community(client, "ana", "Encina")
    _upload(
        client,
        "ana",
        community_id,
        "zonas.pdf",
        build_pdf(["El jardin tiene rosales.", "La caldera del edificio la revisa CalderasDelta."]),
        "application/pdf",
    )
    response = client.post(
        f"/communities/{community_id}/questions",
        headers={"X-User-Id": "ana"},
        json={"question": "¿Quién revisa la caldera del edificio?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sufficient_evidence"] is True
    assert body["degraded"] is False
    matched = [
        citation
        for citation in body["citations"]
        if citation["page"] == 2 and "CalderasDelta" in citation["fragment"]
    ]
    assert matched


def test_rollback_keeps_existing_chunks(client, db):
    community_id = _create_community(client, "ana", "Sauce")
    uploaded = _upload(
        client,
        "ana",
        community_id,
        "acta.txt",
        b"Texto estable del portal.",
        "text/plain",
    )
    before = db.scalar(select(func.count()).select_from(Chunk))
    document = db.get(Document, UUID(uploaded["id"]))
    assert document is not None
    rewrite_chunks(db, document, [], [])
    db.rollback()
    db.expire_all()
    after = db.scalar(select(func.count()).select_from(Chunk))
    assert before == 1
    assert after == 1


def test_communities_are_isolated(client):
    secret = "quilomboalfa94"
    own = _create_community(client, "ana", "Privada")
    _upload(
        client,
        "ana",
        own,
        "secreto.txt",
        f"El codigo interno de la derrama es {secret}.".encode(),
        "text/plain",
    )
    other = _create_community(client, "luis", "Ajena")
    listing = client.get(f"/communities/{own}/documents", headers={"X-User-Id": "luis"})
    assert listing.status_code == 404
    assert secret not in listing.text
    denied = client.post(
        f"/communities/{own}/questions",
        headers={"X-User-Id": "luis"},
        json={"question": "¿Cuál es el codigo interno de la derrama?"},
    )
    assert denied.status_code == 404
    own_answer = client.post(
        f"/communities/{own}/questions",
        headers={"X-User-Id": "ana"},
        json={"question": "¿Cuál es el codigo interno de la derrama?"},
    )
    assert own_answer.status_code == 200
    assert secret in own_answer.text
    foreign = client.post(
        f"/communities/{other}/questions",
        headers={"X-User-Id": "luis"},
        json={"question": "¿Cuál es el codigo interno de la derrama?"},
    )
    assert foreign.status_code == 200
    body = foreign.json()
    assert body["sufficient_evidence"] is False
    assert body["citations"] == []
    assert secret not in foreign.text
    visible = client.get("/communities", headers={"X-User-Id": "luis"})
    names = [item["name"] for item in visible.json()]
    assert names == ["Ajena"]


def test_delete_document_drops_chunks_and_hides_it(client, db):
    community_id = _create_community(client, "ana", "Borrar acta")
    uploaded = _upload(
        client,
        "ana",
        community_id,
        "acta.txt",
        "Se aprobó pintar el portal de verde.".encode(),
        "text/plain",
    )
    assert db.scalar(select(func.count()).select_from(Chunk)) == 1
    outsider = client.delete(
        f"/communities/{community_id}/documents/{uploaded['id']}",
        headers={"X-User-Id": "luis"},
    )
    assert outsider.status_code == 404
    missing = client.delete(
        f"/communities/{community_id}/documents/{UUID(int=0)}",
        headers={"X-User-Id": "ana"},
    )
    assert missing.status_code == 404
    removed = client.delete(
        f"/communities/{community_id}/documents/{uploaded['id']}",
        headers={"X-User-Id": "ana"},
    )
    assert removed.status_code == 204
    assert removed.content == b""
    listing = client.get(
        f"/communities/{community_id}/documents",
        headers={"X-User-Id": "ana"},
    )
    assert listing.json() == []
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    assert db.get(Document, UUID(uploaded["id"])) is None
    answer = client.post(
        f"/communities/{community_id}/questions",
        headers={"X-User-Id": "ana"},
        json={"question": "¿De qué color se pintó el portal?"},
    )
    assert answer.status_code == 200
    assert answer.json()["sufficient_evidence"] is False
    assert answer.json()["citations"] == []
    again = _upload(
        client,
        "ana",
        community_id,
        "acta.txt",
        "Se aprobó pintar el portal de verde.".encode(),
        "text/plain",
    )
    assert again["id"] != uploaded["id"]
    assert again["status"] == "ready"


def test_delete_community_removes_documents_for_members_only(client, db):
    community_id = _create_community(client, "ana", "Temporal")
    kept = _create_community(client, "ana", "Se queda")
    _upload(
        client,
        "ana",
        community_id,
        "nota.txt",
        b"La derrama del tejado son 400 euros.",
        "text/plain",
    )
    assert db.scalar(select(func.count()).select_from(Chunk)) == 1
    denied = client.delete(f"/communities/{community_id}", headers={"X-User-Id": "luis"})
    assert denied.status_code == 404
    removed = client.delete(f"/communities/{community_id}", headers={"X-User-Id": "ana"})
    assert removed.status_code == 204
    listing = client.get("/communities", headers={"X-User-Id": "ana"})
    assert [item["id"] for item in listing.json()] == [kept]
    gone = client.get(
        f"/communities/{community_id}/documents",
        headers={"X-User-Id": "ana"},
    )
    assert gone.status_code == 404
    question = client.post(
        f"/communities/{community_id}/questions",
        headers={"X-User-Id": "ana"},
        json={"question": "¿Cuánto es la derrama del tejado?"},
    )
    assert question.status_code == 404
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    assert db.scalar(select(func.count()).select_from(Document)) == 0
