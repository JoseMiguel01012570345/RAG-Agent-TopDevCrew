from collections.abc import Generator
from pathlib import Path

from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)

        @event.listens_for(_engine, "connect")
        def _register_vector(dbapi_connection, _connection_record) -> None:
            register_vector(dbapi_connection)

    return _engine


def SessionLocal() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    url = get_settings().database_url.replace("%", "%%")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
