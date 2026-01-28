import os
import logging
from typing import Optional
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource

# Try importing OTLP exporters, handle if missing (e.g. during minimal local test)
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False

logger = logging.getLogger(__name__)

class TelemetryManager:
    """
    Manages OpenTelemetry setup for MeshForge Runtime.
    Supports OTLP export and console fallback.
    """
    def __init__(self, service_name: str = "meshforge-runtime", otlp_endpoint: Optional[str] = None, enable_console: bool = False):
        self.service_name = service_name
        self.endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self.enable_console = enable_console
        
        self.resource = Resource.create(attributes={"service.name": self.service_name})
        self.tracer_provider = TracerProvider(resource=self.resource)
        self.meter_provider = None
        
        self._setup_tracing()
        self._setup_metrics()
        
        # Set globals
        trace.set_tracer_provider(self.tracer_provider)
        if self.meter_provider:
            metrics.set_meter_provider(self.meter_provider)

    def _setup_tracing(self):
        if OTLP_AVAILABLE:
            try:
                span_exporter = OTLPSpanExporter(endpoint=self.endpoint, insecure=True)
                self.tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
                logger.info(f"OTLP Tracing enabled on {self.endpoint}")
            except Exception as e:
                logger.warning(f"Failed to initialize OTLP Tracing: {e}")
        
        if self.enable_console:
            self.tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    def _setup_metrics(self):
        readers = []
        if OTLP_AVAILABLE:
            try:
                metric_exporter = OTLPMetricExporter(endpoint=self.endpoint, insecure=True)
                readers.append(PeriodicExportingMetricReader(metric_exporter))
                logger.info(f"OTLP Metrics enabled on {self.endpoint}")
            except Exception as e:
                logger.warning(f"Failed to initialize OTLP Metrics: {e}")

        if self.enable_console:
            readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))

        if readers:
            self.meter_provider = MeterProvider(resource=self.resource, metric_readers=readers)
        else:
            # Fallback to no-op if no readers
            self.meter_provider = MeterProvider(resource=self.resource)

    @staticmethod
    def get_tracer(name: str):
        return trace.get_tracer(name)

    @staticmethod
    def get_meter(name: str):
        return metrics.get_meter(name)
