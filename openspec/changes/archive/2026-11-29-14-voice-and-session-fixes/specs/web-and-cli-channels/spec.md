# Spec Delta

## ADDED Requirements

### Requirement: Guardrail Toggle API and Session Lifecycle Endpoints
The web app SHALL expose `POST /api/guardrails` (with `bool | null` override clearing while leaving omitted fields unchanged), accept per-turn `judge`/`mask` overrides on `/api/chat` and `/api/chat/stream`, clear `_guardrails` on login/logout/flush, and expose `POST /api/session` and `POST /api/page-leave`. Phoenix project lookups for trace links SHALL run off the asyncio event loop with a failure cooldown.

#### Scenario: Guardrail toggles override defaults and clear on explicit null
- **WHEN** a client calls `POST /api/guardrails` with `{user_id, judge: false, mask: false}` and later calls `POST /api/guardrails` with `{user_id, judge: null, mask: null}`
- **THEN** the overrides apply while set and are cleared back to mode defaults when explicit `null` is sent, and logging in again or flushing on tab close also clears stale overrides

#### Scenario: Session and page-leave endpoints preserve reloads and flush closed tabs
- **WHEN** a tab sends `POST /api/page-leave` with an epoch and no `POST /api/session` cancels it within `PAGE_LEAVE_GRACE_MS`
- **THEN** the server flushes the transcript to Mem0 once and drops the in-memory runner

#### Scenario: Unreachable Phoenix does not block async chat or voice handlers
- **WHEN** `TELEMETRY=true` and `PHOENIX_URL` is unreachable during `/api/chat/stream` or `/voice/ws`
- **THEN** the Phoenix `/v1/projects` lookup executes off the event loop and subsequent turns within the failure cooldown return the fallback `/projects` link without blocking

## MODIFIED Requirements

### Requirement: Idempotent Login and Single Mem0 Flush on Logout
`POST /api/login` SHALL authenticate against `users`, create or reuse a session, and return `ok`, `user_id`, `full_name`, `is_premium`, `items`, and `model`. `POST /api/logout` SHALL flush the transcript to Mem0 once.

#### Scenario: Login hydrates the profile
- **WHEN** valid email and password are posted to `/api/login`
- **THEN** the response includes `user_id`, `full_name`, `is_premium`, `items`, and `model`

### Requirement: Chat and Streamed Inspector Events
`POST /api/chat` SHALL return the final assistant text (passing `stream=False` to `text_pipeline`, including in Quick mode), and `POST /api/chat/stream` SHALL emit NDJSON for the stages that run. Explain (or omitted mode) SHALL run sanitizer, judge, tools, masker, and final; Quick SHALL run sanitizer and final and omit judge and masker even after normal browser login unless explicitly overridden. Both endpoints SHALL record sanitized user text in `_transcripts` / Mem0.

#### Scenario: Root pages are served
- **WHEN** a client GETs `/` or `/architecture` or `/architecture.svg`
- **THEN** the response is `200`

#### Scenario: Explain stream keeps the cascade
- **WHEN** a signed-in client posts `/api/chat/stream` with mode `explain`, or omits mode
- **THEN** the NDJSON includes sanitizer, judge, and masker before final

#### Scenario: Quick stream skips judge and masker
- **WHEN** a signed-in client posts `/api/chat/stream` with mode `quick`
- **THEN** the NDJSON includes sanitizer and final, and includes neither judge nor masker

#### Scenario: Quick stream skips judge and masker after normal browser login
- **WHEN** a shopper signs in via the browser without manually clicking `#toggleJudge` or `#toggleMask` and sends a `quick` turn
- **THEN** `/api/guardrails` is not pre-populated with forced `true` overrides and the NDJSON includes sanitizer and final with neither judge nor masker

### Requirement: CLI Uses Sanitized Input and Preserves Casing
The operator CLI SHALL pass sanitized text to `runner.run()`, preserve masked reply casing, honor `MASK=false` via `mask_enabled()`, reuse `greet_user()`, set `thinking_budget=0`, close DB handles in a `finally:` block, omit fake no-op order-loading sleeps, and trace repeated tool calls FIFO.

#### Scenario: CLI validate_input returns clean text
- **WHEN** `validate_input` succeeds
- **THEN** the returned string is the sanitized text used for the run

#### Scenario: CLI skips masking when MASK=false
- **WHEN** `MASK=false` and `run_turn` executes in `src/api/cli.py`
- **THEN** `_mask_response` is skipped and the raw agent reply is returned

#### Scenario: CLI traces repeated calls to the same tool with distinct args
- **WHEN** the CLI agent invokes the same tool twice in one turn with different arguments
- **THEN** each `tool.<name>` span records its own call arguments in FIFO order

### Requirement: Tab close flushes only if the tab does not return
Leaving the page SHALL NOT drop the server session before a reload of that same tab can keep it. A leave that no reload confirms SHALL drop the server session and SHALL flush the transcript to Mem0 once. A frozen page and an actively capturing microphone SHALL NOT schedule that flush, whereas an idle paused Push-to-Talk session SHALL allow tab-close flush.

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
- **WHEN** the microphone is actively capturing speech and the page hides
- **THEN** no flush is scheduled

#### Scenario: Idle Push-to-Talk session allows tab-close flush
- **WHEN** a shopper completes a Push-to-Talk turn, releases the mic so PTT pauses idle, and then closes the tab
- **THEN** `window.csVoiceOn` is false, `/api/page-leave` is beaconed, and Mem0 is flushed after the grace window

### Requirement: Light and Dark Theme Toggle
The shopper page and architecture inspector SHALL provide `#themeToggle` switching between light and dark (`data-theme="dark"`), persisted in `localStorage["cs-theme"]` and synced across tabs via `storage` events on both pages. On `/`, `.ds-aurora`/`.ds-grain` SHALL sit outside `.login` (removed on sign-in) and `.steps summary .pill` SHALL NOT inherit `.pill:hover` lift.

#### Scenario: Switching to dark theme persists across pages
- **WHEN** a user clicks `#themeToggle` to switch to dark mode
- **THEN** `document.documentElement` receives `data-theme="dark"`, `localStorage["cs-theme"]` stores `"dark"`, and both `/` and `/architecture` honor the dark palette on load

#### Scenario: Theme toggle live-syncs between open chat and architecture tabs
- **WHEN** a user toggles `#themeToggle` in `/architecture` while `/` is open in another tab
- **THEN** `/` receives the `storage` event for `cs-theme` and updates its `data-theme` attribute immediately
