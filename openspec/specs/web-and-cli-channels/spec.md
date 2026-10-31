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

### Requirement: Reload keeps the signed-in shopper
A reload of a signed-in shopper page SHALL show that same shopper, including the name and the composer, while the server session still exists. The reload SHALL NOT ask for the password and SHALL NOT submit a new login. The remembered record SHALL NOT contain the password.

#### Scenario: Reload shows the shop
- **WHEN** the shopper is signed in and reloads the page, and the server session still exists
- **THEN** the page shows that shopper and the composer, and does not show the login form

#### Scenario: Reload does not start a new login
- **WHEN** the shopper reloads a signed-in page
- **THEN** the page does not submit email and password

#### Scenario: The password is not remembered
- **WHEN** the shopper signs in
- **THEN** the tab's remembered record does not contain the password

### Requirement: A missing server session shows login
The shopper page SHALL show the login form and SHALL forget the remembered shopper when the server reports that shopper is not signed in.

#### Scenario: Server session is gone
- **WHEN** the page loads with a remembered shopper and the server reports that shopper is not signed in
- **THEN** the page shows the login form and does not keep that remembered shopper

### Requirement: Sign out ends the session now
Sign out SHALL drop the server session, flush the transcript to Mem0 once, forget the remembered shopper, and the following page load SHALL show the login form.

#### Scenario: Sign out returns to login
- **WHEN** the shopper chooses Sign out
- **THEN** the server session is gone, the transcript was flushed once, and the next load shows the login form

### Requirement: Tab close flushes only if the tab does not return
Leaving the page SHALL NOT drop the server session before a reload of that same tab can keep it. A leave that no reload confirms SHALL drop the server session and SHALL flush the transcript to Mem0 once. A frozen page and an open microphone SHALL NOT schedule that flush.

#### Scenario: Reload cancels the flush
- **WHEN** the shopper reloads and the new page confirms the server session
- **THEN** the server session is still present and that leave does not flush Mem0

#### Scenario: Closed tab flushes
- **WHEN** the shopper leaves the page and no reload confirms the session
- **THEN** the server session is dropped and the transcript is flushed to Mem0 once

#### Scenario: Frozen page does not schedule a flush
- **WHEN** the page is hidden and kept for later restore without a new document
- **THEN** no flush is scheduled

#### Scenario: Open microphone does not schedule a flush
- **WHEN** the microphone is on and the page hides
- **THEN** no flush is scheduled
