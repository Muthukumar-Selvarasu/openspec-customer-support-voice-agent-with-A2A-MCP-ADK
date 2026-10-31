# Design: Core Auth, Memory, Prompts & Telemetry

## Context

See `proposal.md`. Depends on `01-db-and-mcp-foundation`. Implement leaf modules under `src/core/` (`from src.core...`).

## Goals / Non-Goals

**Goals:**
- Leaf modules with no FastAPI/A2A/voice imports.
- Env-driven DB and Phoenix URLs with localhost defaults.
- Importable without Mem0 or Phoenix credentials.

**Non-Goals:**
- HTTP routes, sessions, or ADK `before_tool_callback` (Group 6).
- Starting Phoenix or Mem0.

## Decisions

### Decision 1: Package as `src/core/`
Implement `greet.py`, `memory.py`, `prompts.py`, and `telemetry.py` under `src/core/`. Later slices import `src.core.*`. Do not use `sys.path` hacks.

### Decision 2: DATABASE_URL first, then PG*, then cascade localhost defaults
Replace hardcoded `127.0.0.1` in `_pg()` so `DATABASE_URL` is preferred, then `PG*`, then localhost, without a stray `PGUSER` hijacking local `./run.sh setup`.

### Decision 3: Prompt parameter names match tools.yaml
`SQL_PROMPT_INSTRUCTION` uses `parameters` (the MCP tool field), not `parameters_json`. It also states that `get-order-status` takes `order_id` plus the authenticated `customer_email` (Group 6 callback injects the email so the model cannot pick another shopper).

### Decision 4: Skip browser open when headless
`telemetry.py` currently opens Phoenix in a browser. Skip that when `PHOENIX_OPEN_BROWSER=false`. Honor `PHOENIX_URL` / `PHOENIX_PUBLIC_URL` instead of hard-coding `http://localhost:6006`.

### Decision 5: Lazy Mem0 client
Construct `MemoryClient` on first `search_memory` / `save_memory` call, not at import, so `import src.core.memory` works without `MEM0_API_KEY`.

## Risks / Trade-offs

- **[Risk] Auth tests need Postgres** → Mitigation: unit-test connection-string parsing without a live DB; live `authenticate_user` tests use Group 1 Podman Postgres when it is up and skip when it is not.
