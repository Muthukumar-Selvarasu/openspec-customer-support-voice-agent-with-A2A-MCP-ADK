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
`SQL_PROMPT_INSTRUCTION` SHALL instruct the agent to read first, confirm with the shopper, write only via `action-log`, never call `update-order-status`, pass `parameters` (not `parameters_json`), and treat `get-order-status` `customer_email` as the authenticated shopper.

#### Scenario: Prompt matches tools.yaml
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it contains `parameters` and does not contain `parameters_json`

### Requirement: No-Op Tracer When Telemetry Is Off
When `TELEMETRY` is unset or false, `get_tracer()` SHALL return `_NoopTracer` without importing Phoenix. When true, the tracer SHALL export to `PHOENIX_URL` (default `http://localhost:6006`) and SHALL NOT call `webbrowser.open()` in headless/container environments.

#### Scenario: TELEMETRY=false is a no-op
- **WHEN** `TELEMETRY=false`
- **THEN** `get_tracer().start_as_current_span(...)` is a no-op context manager
