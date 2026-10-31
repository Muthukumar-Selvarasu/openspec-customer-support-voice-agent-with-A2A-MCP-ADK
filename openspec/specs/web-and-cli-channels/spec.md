# web-and-cli-channels Specification

## Purpose

Defines the shopper FastAPI app, glass-box UI, architecture visualization, operator CLI, and deterministic tenant isolation on tool calls.

## Requirements

### Requirement: Idempotent Login and Single Mem0 Flush on Logout
`POST /api/login` SHALL authenticate against `users` and create or reuse a session. `POST /api/logout` SHALL flush the transcript to Mem0 once.

#### Scenario: Login hydrates the profile
- **WHEN** valid email and password are posted to `/api/login`
- **THEN** the response includes `user_id`, `full_name`, and Premium flag

### Requirement: Chat and Streamed Inspector Events
`POST /api/chat` SHALL return the final assistant text. `POST /api/chat/stream` SHALL emit NDJSON for the stages that run. Explain, and a request that omits mode, SHALL include sanitizer, judge, tool_call, tool_result, masker, and final. Quick SHALL include sanitizer and final, SHALL omit judge and masker, and SHALL still return the assistant text.

#### Scenario: Root pages are served
- **WHEN** a client GETs `/` or `/architecture` or `/architecture.svg`
- **THEN** the response is `200`

#### Scenario: Explain stream keeps the cascade
- **WHEN** a signed-in client posts `/api/chat/stream` with mode `explain`, or omits mode
- **THEN** the NDJSON includes sanitizer, judge, and masker before final

#### Scenario: Quick stream skips judge and masker
- **WHEN** a signed-in client posts `/api/chat/stream` with mode `quick`
- **THEN** the NDJSON includes sanitizer and final, and includes neither judge nor masker

### Requirement: Demo mode toggle
The shopper page SHALL offer Explain and Quick, with Explain as the default. The choice SHALL persist in the browser and SHALL be sent on each streamed chat turn and each voice turn. Explain SHALL show the "What happened" panel. Quick SHALL hide that panel and show the assistant answer.

#### Scenario: First visit is Explain
- **WHEN** the shopper page loads with no saved choice
- **THEN** the toggle shows Explain and the next turn sends mode `explain`

#### Scenario: Quick hides the step list
- **WHEN** the shopper selects Quick and sends a typed turn
- **THEN** the assistant bubble shows the answer and the "What happened" panel is not shown

#### Scenario: Saved choice survives reload
- **WHEN** the shopper selects Quick and reloads the page
- **THEN** the toggle still shows Quick

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
