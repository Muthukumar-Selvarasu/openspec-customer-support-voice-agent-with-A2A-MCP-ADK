# Spec Delta: `web-and-cli-channels`

## Purpose

Defines the shopper FastAPI app, glass-box UI, architecture visualization, operator CLI, and deterministic tenant isolation on tool calls.

## ADDED Requirements

### Requirement: Idempotent Login and Single Mem0 Flush on Logout
`POST /api/login` SHALL authenticate against `users` and create or reuse a session. `POST /api/logout` SHALL flush the transcript to Mem0 once.

#### Scenario: Login hydrates the profile
- **WHEN** valid email and password are posted to `/api/login`
- **THEN** the response includes `user_id`, `full_name`, and Premium flag

### Requirement: Chat and Streamed Inspector Events
`POST /api/chat` SHALL return the final assistant text. `POST /api/chat/stream` SHALL emit NDJSON events for sanitizer, judge, tool_call, tool_result, masker, and final.

#### Scenario: Root pages are served
- **WHEN** a client GETs `/` or `/architecture` or `/architecture.svg`
- **THEN** the response is `200`

### Requirement: Deterministic Tenant Isolation on Tools
An ADK `before_tool_callback` SHALL overwrite cross-tenant emails/`user_id` with the session identity and SHALL block `update-order-status`. Combined with Group 1 SQL, a shopper MUST NEVER receive another customer's row in `tool_result`.

#### Scenario: Cross-tenant order id is scoped
- **WHEN** Alice's session asks for an order that belongs to Bob
- **THEN** `get-order-status` is invoked with Alice's email and `tool_result` does not contain Bob's row

#### Scenario: Direct status update is blocked
- **WHEN** the model attempts `update-order-status`
- **THEN** the callback blocks the call

### Requirement: CLI Uses Sanitized Input and Preserves Casing
The operator CLI SHALL pass the sanitized string to `runner.run()` and MUST NOT lowercase the masked assistant reply.

#### Scenario: CLI validate_input returns clean text
- **WHEN** `validate_input` succeeds
- **THEN** the returned string is the sanitized text used for the run

### Requirement: Env-Driven Service URLs
The web app SHALL read `TOOLBOX_URL`, `A2A_JUDGE_HOST`, `A2A_JUDGE_PORT`, `A2A_MASK_HOST`, `A2A_MASK_PORT`, `PHOENIX_URL`, `PHOENIX_PUBLIC_URL`, `HOST`, and `PORT` with localhost defaults. `WEB_PORT` MUST be accepted as an alias of `PORT`. Importing `src.api.web` MUST NOT require a running MCP Toolbox process.

#### Scenario: Local defaults work without extra env
- **WHEN** those variables are unset
- **THEN** the app targets `127.0.0.1` toolbox `:5000`, A2A `:10002`/`:10003`, Phoenix `:6006`, and web `:8000`

#### Scenario: WEB_PORT aliases PORT
- **WHEN** `PORT` is unset and `WEB_PORT=8000`
- **THEN** the web process listens on port `8000`

#### Scenario: Static pages resolve from src/static
- **WHEN** `GET /`, `GET /architecture`, or `GET /architecture.svg` is served from `src/api/web.py`
- **THEN** files are read from `src/static/`, not `src/api/static/`
