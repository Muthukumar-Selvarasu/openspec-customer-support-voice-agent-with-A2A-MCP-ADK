# Tasks: `02-core-auth-memory-telemetry`

Implement leaf modules under `src/core/` with `src.core.*` imports. Mock Mem0 in tests. Live Postgres tests use the Group 1 Podman `postgres` service; skip them if that container is not running.

## 1. Auth, memory, and prompt contract

- [ ] 1.1 Implement `src/core/greet.py` with `authenticate_user`, `greet_user`, and `get_user_actions`; resolve Postgres via `DATABASE_URL`, then `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`, then `127.0.0.1:5432` / `toolbox_db` / `toolbox_user` / `mysecretpassword`; add connection-string unit tests that do not need a live DB; verify with `pytest tests/unit/test_core.py -k greet`
- [ ] 1.2 Implement `src/core/memory.py` with `search_memory` and `save_memory` scoped by `user_id`; lazy-init the Mem0 client so `import src.core.memory` succeeds without `MEM0_API_KEY`; mock Mem0 in tests; verify with `pytest tests/unit/test_core.py -k memory`
- [ ] 1.3 Implement `src/core/prompts.py` `SQL_PROMPT_INSTRUCTION`: read first, confirm with the shopper, write only via `action-log`, never call `update-order-status`, pass `parameters` (not `parameters_json`), and treat `get-order-status` `customer_email` as the authenticated shopper; verify `SQL_PROMPT_INSTRUCTION.format(USER_ID=...)` with `pytest tests/unit/test_core.py -k prompt`

## 2. Telemetry

- [ ] 2.1 Implement `src/core/telemetry.py`: `get_tracer()` returns `_NoopTracer` when `TELEMETRY` is unset/false without importing Phoenix; when enabled, export to `PHOENIX_URL` / `PHOENIX_PUBLIC_URL` (default `http://localhost:6006`) and skip `webbrowser.open()` when `PHOENIX_OPEN_BROWSER=false`; verify with `pytest tests/unit/test_core.py`
