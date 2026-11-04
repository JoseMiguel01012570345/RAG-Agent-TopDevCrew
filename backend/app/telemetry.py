from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import get_settings

_configured = False


def setup_telemetry(service_name: str | None = None) -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    name = service_name or settings.otel_service_name
    provider = TracerProvider(resource=Resource.create({"service.name": name}))
    endpoint = settings.otel_exporter_otlp_endpoint
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True
