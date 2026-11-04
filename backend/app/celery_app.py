from celery import Celery
from celery.signals import worker_init, worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from app.config import get_settings
from app.logging_config import setup_logging
from app.telemetry import setup_telemetry

settings = get_settings()

celery = Celery("faro", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

_celery_instrumented = False
if not _celery_instrumented:
    CeleryInstrumentor().instrument()
    _celery_instrumented = True


@worker_init.connect
def init_worker(**_kwargs) -> None:
    setup_logging()
    setup_telemetry("faro-worker")
    from app.db import run_migrations

    run_migrations()


@worker_process_init.connect
def init_worker_process(**_kwargs) -> None:
    setup_logging()
    setup_telemetry("faro-worker")
    from app.db import get_engine

    SQLAlchemyInstrumentor().instrument(engine=get_engine())
