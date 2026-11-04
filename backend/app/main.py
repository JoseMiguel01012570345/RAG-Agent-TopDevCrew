from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from app.api.routes import router
from app.config import get_settings
from app.db import get_engine, run_migrations
from app.logging_config import setup_logging
from app.telemetry import setup_telemetry

_db_instrumented = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _db_instrumented
    setup_logging()
    setup_telemetry(get_settings().otel_service_name)
    run_migrations()
    if not _db_instrumented:
        SQLAlchemyInstrumentor().instrument(engine=get_engine())
        _db_instrumented = True
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Faro Administraciones",
        version="0.1.0",
        summary="Asistente documental con ingesta asíncrona y citas verificables.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8080"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
