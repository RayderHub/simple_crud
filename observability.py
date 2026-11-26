import base64
from datetime import datetime, timezone
import logging
import os
import threading
import time
from typing import Any, Dict, Optional
import requests

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("simple_crud")


def _openobserve_auth_header() -> Optional[str]:
    user = os.getenv("OPENOBSERVE_USER", "").strip()
    password = os.getenv("OPENOBSERVE_PASSWORD", "").strip()
    if not user or not password:
        return None
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _openobserve_base_url() -> str:
    return os.getenv("OPENOBSERVE_URL", "").strip().rstrip("/")


def _openobserve_org() -> str:
    return os.getenv("OPENOBSERVE_ORG", "default").strip() or "default"


def send_openobserve_log(stream: str, record: Dict[str, Any]) -> None:
    """Envía un log estructurado JSON a OpenObserve de forma asíncrona (no bloqueante)."""
    base_url = _openobserve_base_url()
    auth = _openobserve_auth_header()
    if not base_url or not auth:
        return

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": os.getenv("OTEL_SERVICE_NAME", "simple-crud-flask"),
        **record,
    }
    url = f"{base_url}/api/{_openobserve_org()}/{stream}/_json"
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
    }

    def _post():
        try:
            requests.post(url, json=[payload], headers=headers, timeout=3)
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()


def setup_observability(app) -> None:
    """Instrumenta la aplicación Flask con OpenTelemetry (Traces, Metrics y Logs hacia OpenObserve)."""
    service_name = os.getenv("OTEL_SERVICE_NAME", "simple-crud-flask")
    base_url = _openobserve_base_url()
    auth = _openobserve_auth_header()
    org = _openobserve_org()

    if base_url and auth:
        resource = Resource.create({"service.name": service_name})
        otlp_headers = {
            "Authorization": auth,
            "organization": org,
            "stream-name": "default",
        }

        # 1. Traces (OTLP/HTTP)
        tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(
            endpoint=f"{base_url}/api/{org}/v1/traces",
            headers=otlp_headers,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # 2. Metrics (OTLP/HTTP)
        metric_exporter = OTLPMetricExporter(
            endpoint=f"{base_url}/api/{org}/v1/metrics",
            headers=otlp_headers,
        )
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=10000
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        # Instrumentación automática de Flask y Requests (trazas distribuidas hasta Supabase)
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()

        meter = metrics.get_meter(service_name)
        req_counter = meter.create_counter(
            name="http_server_requests_total",
            description="Total de peticiones HTTP recibidas por endpoint",
        )
        req_duration = meter.create_histogram(
            name="http_server_request_duration_ms",
            description="Latencia de peticiones HTTP en milisegundos",
            unit="ms",
        )
        req_errors = meter.create_counter(
            name="http_server_errors_total",
            description="Total de errores HTTP (4xx/5xx) por endpoint",
        )
    else:
        req_counter = None
        req_duration = None
        req_errors = None

    @app.before_request
    def _otel_before_request():
        from flask import g
        g._req_start_time = time.perf_counter()

    @app.after_request
    def _otel_after_request(response):
        from flask import g, request
        elapsed_ms = round((time.perf_counter() - getattr(g, "_req_start_time", time.perf_counter())) * 1000, 2)
        endpoint = request.path
        method = request.method
        status_code = response.status_code

        attrs = {
            "http.method": method,
            "http.route": endpoint,
            "http.status_code": str(status_code),
        }
        if req_counter:
            req_counter.add(1, attrs)
        if req_duration:
            req_duration.record(elapsed_ms, attrs)
        if req_errors and status_code >= 400:
            req_errors.add(1, attrs)

        send_openobserve_log(
            "app_logs",
            {
                "level": "ERROR" if status_code >= 500 else ("WARN" if status_code >= 400 else "INFO"),
                "method": method,
                "endpoint": endpoint,
                "statusCode": status_code,
                "latency_ms": elapsed_ms,
                "remote_addr": request.remote_addr,
                "message": f"{method} {endpoint} -> {status_code} ({elapsed_ms} ms)",
            },
        )
        return response

    @app.errorhandler(Exception)
    def _otel_handle_exception(err):
        from flask import request
        from werkzeug.exceptions import HTTPException
        if isinstance(err, HTTPException):
            return err
        send_openobserve_log(
            "app_logs",
            {
                "level": "ERROR",
                "method": request.method,
                "endpoint": request.path,
                "statusCode": 500,
                "exception": type(err).__name__,
                "message": f"Excepción no controlada: {err}",
            },
        )
        return {"ok": False, "error": "Error interno del servidor"}, 500
