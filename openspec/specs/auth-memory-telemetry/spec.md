# auth-memory-telemetry Specification

## Purpose

Defines shopper authentication against PostgreSQL `users`, Premium/Standard greeting, Mem0 memory tools, the Read-Confirm-Audit prompt contract, and optional Phoenix tracing.

## Requirements

### Requirement: Environment-Driven Postgres Connection
The system SHALL open Postgres using `DATABASE_URL` when set, otherwise `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`, falling back to `127.0.0.1:5432` / `toolbox_db` / `toolbox_user` / `mysecretpassword`.

#### Scenario: DATABASE_URL is preferred
- **WHEN** `DATABASE_URL` is set
- **THEN** `src/core/greet.py` uses that URL and does not hard-code `127.0.0.1`

### Requirement: Customer Credential Authentication and Tier Greeting
The system SHALL authenticate by email and password against `users` and SHALL greet Premium shoppers with name and `total_items_purchased`.

#### Scenario: Premium shopper is recognized
- **WHEN** `authenticate_user` succeeds for a row with `is_premium_customer = true`
- **THEN** `greet_user` includes the shopper's name, Premium status, and purchase count

#### Scenario: Unknown credentials fail closed
- **WHEN** email and password do not match a `users` row
- **THEN** `authenticate_user` returns `None`

### Requirement: Mem0 Search and Save Tools
The system SHALL expose `search_memory(query, user_id)` and `save_memory(messages, user_id)` scoped to the authenticated `user_id`. Importing `src.core.memory` MUST succeed when `MEM0_API_KEY` is unset (client constructed on first use).

#### Scenario: Search uses the session user id
- **WHEN** `search_memory` is called
- **THEN** the Mem0 filter includes that `user_id` and does not accept a different identity from the model

#### Scenario: Memory module imports without a key
- **WHEN** `MEM0_API_KEY` is unset
- **THEN** `import src.core.memory` does not raise

### Requirement: Read-Confirm-Audit Prompt Uses MCP Parameter Names
`SQL_PROMPT_INSTRUCTION` SHALL instruct the agent to read first, confirm with the shopper, write only via `action-log`, never call `update-order-status`, pass `parameters` (not `parameters_json`), and treat `get-order-status` `customer_email` as the authenticated shopper. To keep voice and chat turn latency within 3–5 seconds, `SQL_PROMPT_INSTRUCTION` SHALL instruct the agent to call `search_memory` only when the shopper asks about past conversations, saved preferences, or context not available from the order tools (rather than calling `search_memory` unconditionally before every order lookup), and SHALL instruct the agent to keep responses concise (1–3 clear sentences).

#### Scenario: Prompt matches tools.yaml
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it contains `parameters` and does not contain `parameters_json`

#### Scenario: Prompt scopes memory search to preference or history context and encourages concise replies
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it does not instruct the agent to `ALWAYS use the search_memory function` on every query, directs order lookups straight to `get-order-status` or `find-customer-orders`, and includes a concise response guideline

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
