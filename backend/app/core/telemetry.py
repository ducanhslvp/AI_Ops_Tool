from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import make_asgi_app

from app.core.config import Settings


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    if settings.otel_exporter_otlp_endpoint:
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=False)
            )
        )
        trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    if settings.metrics_enabled:
        app.mount("/metrics", make_asgi_app())
