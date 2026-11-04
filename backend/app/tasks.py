from app.celery_app import celery
from app.services.ingestion import mark_failed, run_ingestion
from app.services.parsing import PermanentIngestionError


@celery.task(
    bind=True,
    name="app.tasks.ingest_document",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
)
def ingest_document(self, document_id: str) -> str:
    try:
        run_ingestion(document_id)
    except PermanentIngestionError as exc:
        mark_failed(document_id, exc.code, exc.message)
        return "failed"
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            mark_failed(
                document_id,
                "internal_error",
                "Falló el procesamiento tras reintentos.",
            )
            return "failed"
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
    return "ready"
