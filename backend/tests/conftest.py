import os

import pytest
from sqlalchemy import create_engine, text

os.environ["LLM_PROVIDER"] = "fake"
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://faro:faro@localhost:5432/faro",
)
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""


def _can_connect() -> bool:
    engine = create_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def database_ready():
    if not _can_connect():
        if os.getenv("REQUIRE_POSTGRES") == "1":
            pytest.fail("PostgreSQL es obligatorio y no responde")
        pytest.skip("PostgreSQL no disponible")
    from app.config import get_settings
    from app.db import run_migrations

    get_settings.cache_clear()
    run_migrations()
    yield


@pytest.fixture
def db(database_ready):
    from app.db import SessionLocal, get_engine

    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE TABLE chunks, documents, memberships, communities, users CASCADE")
        )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.celery_app import celery
    from app.main import app

    celery.conf.task_always_eager = True
    celery.conf.task_eager_propagates = True
    with TestClient(app) as test_client:
        yield test_client
    celery.conf.task_always_eager = False
    celery.conf.task_eager_propagates = False
