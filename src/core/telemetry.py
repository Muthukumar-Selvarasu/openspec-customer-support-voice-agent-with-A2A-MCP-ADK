"""Optional OpenTelemetry export to Phoenix. Off by default, never imported unless enabled."""

from __future__ import annotations

import os
from urllib.parse import urlparse

DEFAULT_PHOENIX_URL = "http://localhost:6006"

try:
    from openinference.semconv.trace import SpanAttributes as ATTR  # type: ignore
except Exception:  # pragma: no cover - fallback when openinference isn't installed

    class ATTR:  # noqa: N801 - mirror of openinference constant names
        OPENINFERENCE_SPAN_KIND = "openinference.span.kind"
        INPUT_VALUE = "input.value"
        OUTPUT_VALUE = "output.value"
        TOOL_NAME = "tool.name"
        LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
        LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
        LLM_TOKEN_COUNT_TOTAL = "llm.token_count.total"
        LLM_COST_PROMPT = "llm.cost.prompt"
        LLM_COST_COMPLETION = "llm.cost.completion"
        LLM_COST_TOTAL = "llm.cost.total"


class _NoopSpan:
    def set_attribute(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None

    def set_status(self, *args, **kwargs):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _NoopTracer:
    def start_as_current_span(self, *args, **kwargs):
        return _NoopSpan()


def telemetry_enabled() -> bool:
    """True when ``TELEMETRY`` is a truthy string."""
    return os.getenv("TELEMETRY", "false").strip().lower() in ("1", "true", "yes", "on")


def resolve_phoenix_urls() -> tuple[str, str]:
    """Return ``(export_url, public_url)`` with localhost defaults."""
    export = os.getenv("PHOENIX_URL") or os.getenv("PHOENIX_PUBLIC_URL") or DEFAULT_PHOENIX_URL
    public = os.getenv("PHOENIX_PUBLIC_URL") or export
    return export.rstrip("/"), public.rstrip("/")


def _open_browser_enabled() -> bool:
    return os.getenv("PHOENIX_OPEN_BROWSER", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _port_from_url(url: str, default: int = 6006) -> int:
    parsed = urlparse(url)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else default


def init_telemetry():
    """Configure the OTLP exporter and Phoenix, then return a real tracer.

    Heavy imports stay inside this function so disabled runs never load Phoenix.
    """
    import webbrowser

    import phoenix as px
    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    export_url, public_url = resolve_phoenix_urls()
    port = _port_from_url(export_url)
    grpc_port = 4317 + (port - 6006)
    os.environ["PHOENIX_PORT"] = str(port)
    os.environ["PHOENIX_GRPC_PORT"] = str(grpc_port)
    try:
        px.launch_app()
    except Exception as exc:  # noqa: BLE001
        print(f"[telemetry] reusing Phoenix at {export_url} (launch skipped: {exc})")

    exporter = OTLPSpanExporter(endpoint=f"{export_url}/v1/traces")
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    GoogleGenAIInstrumentor().instrument(tracer_provider=provider)

    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", export_url)
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")

    if _open_browser_enabled():
        try:
            webbrowser.open(public_url)
        except Exception:  # noqa: BLE001 - headless / no browser is fine
            pass

    return trace.get_tracer("src.core.telemetry")


_started = False
_tracer = None


def reset_telemetry_state() -> None:
    """Clear the cached tracer. Used by tests."""
    global _started, _tracer
    _started = False
    _tracer = None


def get_tracer():
    """Return a Phoenix tracer when ``TELEMETRY`` is on, otherwise ``_NoopTracer``.

    Idempotent and never raises — tracing must not block the app.
    """
    global _started, _tracer
    if _started:
        return _tracer
    _started = True
    if telemetry_enabled():
        try:
            _tracer = init_telemetry()
            _export, public = resolve_phoenix_urls()
            print(f"[telemetry] ENABLED -> Phoenix UI at {public}")
        except Exception as exc:  # noqa: BLE001 - never let telemetry break the app
            print(f"[telemetry] init failed, continuing without it: {exc}")
            _tracer = _NoopTracer()
    else:
        _tracer = _NoopTracer()
    return _tracer
