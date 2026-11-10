"""OpenTelemetry traces and metrics using the GenAI semantic conventions.

Exports over OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set, so the same
build ships to an ADOT/OTel collector, CloudWatch, Grafana, Langfuse or
Datadog without code changes. With no endpoint it's a no-op.
"""

import os

from opentelemetry import metrics, trace
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import TracerProvider

_SCOPE = "ragapi"


def configure_from_env(service_name: str = "ragapi") -> None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", service_name)})
    tracer_provider = SdkTracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(
        SdkMeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
    )


class Telemetry:
    """Instruments for the pipeline. Inject providers in tests; defaults are global."""

    def __init__(
        self,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self.tracer = trace.get_tracer(_SCOPE, tracer_provider=tracer_provider)
        meter = (meter_provider or metrics.get_meter_provider()).get_meter(_SCOPE)

        self.token_usage = meter.create_histogram(
            "gen_ai.client.token.usage",
            unit="{token}",
            description="Tokens used per model call, split by gen_ai.token.type.",
        )
        self.requests = meter.create_counter(
            "rag.requests",
            unit="{request}",
            description="RAG requests by outcome: answered, no_context, blocked, error.",
        )
        self.cost = meter.create_counter(
            "rag.cost",
            unit="USD",
            description="Estimated model spend, attributed per tenant for chargeback.",
        )
        self.redactions = meter.create_counter(
            "rag.pii.redactions",
            unit="{entity}",
            description="PII entities redacted locally, by type and direction.",
        )
