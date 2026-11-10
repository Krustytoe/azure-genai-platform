from dataclasses import dataclass, field
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ragapi.config import Settings
from ragapi.providers.base import Completion, Passage
from ragapi.telemetry import Telemetry

CORPUS = Path(__file__).resolve().parents[2] / "evals" / "corpus"


@dataclass
class StubRetriever:
    passages: list[Passage]
    queries: list[str] = field(default_factory=list)

    def retrieve(self, query: str, top_k: int) -> list[Passage]:
        self.queries.append(query)
        return self.passages[:top_k]


@dataclass
class StubModel:
    completion: Completion
    system: str = "stub"
    model_id: str = "stub-model"
    calls: list[dict] = field(default_factory=list)

    def generate(self, **kwargs) -> Completion:
        self.calls.append(kwargs)
        return self.completion


@dataclass
class TelemetryHarness:
    telemetry: Telemetry
    spans: InMemorySpanExporter
    metrics: InMemoryMetricReader

    def metric_points(self, name: str) -> list:
        data = self.metrics.get_metrics_data()
        return [
            point
            for rm in data.resource_metrics
            for sm in rm.scope_metrics
            for m in sm.metrics
            if m.name == name
            for point in m.data.data_points
        ]


@pytest.fixture
def harness() -> TelemetryHarness:
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    return TelemetryHarness(Telemetry(tracer_provider, meter_provider), spans, reader)


@pytest.fixture
def settings() -> Settings:
    return Settings(provider="fake", fake_corpus_dir=CORPUS)


@pytest.fixture
def passages() -> list[Passage]:
    return [
        Passage("The domestic meal per diem is $75 per day.", "s3://docs/travel.md", 0.82),
        Passage("Hotel stays are reimbursed up to $250 per night.", "s3://docs/travel.md", 0.61),
        Passage("Unrelated text about holidays.", "s3://docs/pto.md", 0.12),
    ]
