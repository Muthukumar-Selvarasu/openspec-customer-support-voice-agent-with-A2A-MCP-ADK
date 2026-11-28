# Spec Delta

## MODIFIED Requirements

### Requirement: No-Op Tracer When Telemetry Is Off
When `TELEMETRY` is unset or false, `get_tracer()` SHALL return `_NoopTracer` without initializing OTel SDK/OTLP exporters, `GoogleGenAIInstrumentor`, or `phoenix`. When true, `init_telemetry()` SHALL configure `OTLPSpanExporter` for `${PHOENIX_URL}/v1/traces` (sending `Authorization: Bearer <PHOENIX_API_KEY>` if set) and `GoogleGenAIInstrumentor`, MUST NOT import `phoenix` or call `px.launch_app()`, and MUST gate `webbrowser.open()` on `PHOENIX_OPEN_BROWSER=true`.

#### Scenario: TELEMETRY=false is a no-op
- **WHEN** `TELEMETRY=false`
- **THEN** `get_tracer().start_as_current_span(...)` is a no-op context manager and does not initialize an OTLP exporter or import `phoenix`

#### Scenario: TELEMETRY=true exports via OTLP without launching an embedded Phoenix server
- **WHEN** `TELEMETRY=true` and `PHOENIX_URL` is set (or defaults to `http://localhost:6006`) with `PHOENIX_API_KEY` unset
- **THEN** `init_telemetry()` registers `OTLPSpanExporter` targeting `${PHOENIX_URL}/v1/traces` with no auth header and `GoogleGenAIInstrumentor`, does not import `phoenix` or invoke `px.launch_app()`, and does not open a browser when `PHOENIX_OPEN_BROWSER` is unset or false

#### Scenario: PHOENIX_API_KEY configures Bearer header for authenticated Phoenix
- **WHEN** `TELEMETRY=true` and `PHOENIX_API_KEY=secret-token`
- **THEN** `init_telemetry()` passes `headers={"Authorization": "Bearer secret-token"}` to `OTLPSpanExporter`

#### Scenario: Unmocked telemetry packages import cleanly in tests
- **WHEN** `tests/unit/test_core.py` imports `TracerProvider`, `BatchSpanProcessor`, `OTLPSpanExporter`, `GoogleGenAIInstrumentor`, and `SpanAttributes` without mocking
- **THEN** all imports succeed without raising `ImportError` or requiring the `arize-phoenix` server package
