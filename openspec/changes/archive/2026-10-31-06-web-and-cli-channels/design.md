# Design: Web Chat, Architecture UI & Operator CLI

## Context

See `proposal.md`. Depends on Groups 2–5. Implement the shopper FastAPI app under `src/api/web.py`, the operator CLI under `src/api/cli.py`, and UI assets under `src/static/`. Closes PoC bug #5 (IDOR in `tool_result`) and CLI sanitizer/lowercase drift.

## Goals / Non-Goals

**Goals:**
- One FastAPI app for chat, inspector UI, architecture SVG, and voice mount.
- Tenant isolation in SQL (Group 1) **and** ADK callback (this slice).
- Importable without Toolbox/A2A running.

**Non-Goals:**
- Merging Judge/Masker into this process.
- Container/CI (Group 7).

## Decisions

### Decision 1: Layout `src/api/` + `src/static/`
`web.py` and `cli.py` live under `src/api/`. Static assets under `src/static/`. `diagram.png` stays at repo root for README.

### Decision 2: Paths are relative to `src/api/web.py`
`web.py` lives at `src/api/web.py`.

- `_REPO_ROOT = Path(__file__).resolve().parents[2]` → repo root (`mcp_toolbox/tools.yaml`, `.env`)
- `_STATIC = Path(__file__).resolve().parents[1] / "static"` → `src/static`

Import `src.core`, `src.security`, `src.a2a`, `src.voice`. Do not use `sys.path` hacks.

### Decision 3: Dual tenant enforcement
SQL `WHERE order_id = $1 AND customer_email = $2` is necessary but not sufficient (PoC leaked Bob's row in `tool_result` before the LLM refused). `_enforce_tenant_tool_callback` overwrites `user_id` / `email` / `customer_email` / `user_email` with the session identity (the shopper email) and blocks `update-order-status`.

### Decision 4: CLI parity with web
`validate_input` returns the sanitized text, `runner.run()` uses that string, and masked output keeps original casing (no `.lower()`).

### Decision 5: Lazy Toolbox client and env aliases
Lazy-init `ToolboxSyncClient` so tests can import `app` without Toolbox. Read `TOOLBOX_URL`, `A2A_*`, `PHOENIX_*`, `HOST`, `PORT` with localhost defaults. `WEB_PORT` is an alias of `PORT`.

### Decision 6: Integration tests mock Toolbox/A2A when down
`GET /` and static routes always run. Login/chat/tenant tests skip or mock unless `DATABASE_URL` and Toolbox are available. Tenant callback tests use a fake tool context and do not need Gemini.

## Risks / Trade-offs

- **[Risk] Full chat tests need Gemini + Toolbox + A2A** → Mitigation: unit-test the tenant callback with a fake tool context; keep one optional live path.
