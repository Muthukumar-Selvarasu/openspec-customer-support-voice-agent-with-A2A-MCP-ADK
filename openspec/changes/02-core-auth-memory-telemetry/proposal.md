# Proposal: Core Auth, Memory, Prompts & Telemetry (`02-core-auth-memory-telemetry`)

## Why

Shopper authentication, Premium/Standard greeting, Mem0 recall, the Read-Confirm-Audit prompt, and optional Phoenix tracing are leaf modules. They have no project-internal imports, so they can be implemented under `src/core/` and unit-tested after Group 1 without FastAPI, A2A, or voice.

This slice closes PoC findings #6 (`parameters_json` vs `parameters`) and the hardcoded `127.0.0.1` Postgres / Phoenix URLs.

## What Changes

- Add `src/core/greet.py` with env-driven `DATABASE_URL` or `PG*` connection resolution, `authenticate_user`, `greet_user`, and `get_user_actions`.
- Add `src/core/memory.py` wrapping Mem0 `search_memory` and `save_memory`, lazy-initialized so import does not require `MEM0_API_KEY`.
- Add `src/core/prompts.py` with `SQL_PROMPT_INSTRUCTION` using `parameters` (not `parameters_json`) and `get-order-status` bound to the authenticated email.
- Add `src/core/telemetry.py` with `_NoopTracer` when `TELEMETRY=false`, `PHOENIX_URL` / `PHOENIX_PUBLIC_URL` when on, and no `webbrowser.open()` when `PHOENIX_OPEN_BROWSER=false`.
- Use `src.core.*` imports only.

## Capabilities

### New Capabilities
- `auth-memory-telemetry`: Credential auth, tier greeting, Mem0 memory, agent prompt contract, and optional OpenTelemetry.

### Modified Capabilities

## Impact

- `src/core/{__init__.py, greet.py, memory.py, prompts.py, telemetry.py}`
- `tests/unit/test_core.py`

## Channels

- **In scope:** none (library modules only)
- **Out of scope:** Web Chat, Voice WebSocket, Terminal CLI, A2A Judge/Masker

## Out of Scope

- FastAPI, A2A servers, voice, sanitizer/blocker/masker
- Live Mem0 or Phoenix processes (unit tests mock or no-op)
