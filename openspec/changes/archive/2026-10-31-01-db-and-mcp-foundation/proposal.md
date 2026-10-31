# Proposal: Database Schema, Seed Data & MCP Tool Catalog (`01-db-and-mcp-foundation`)

## Why

The platform cannot authenticate shoppers or look up orders until PostgreSQL `toolbox_db` and the MCP Toolbox SQL catalog exist. This is the first independently testable slice: schema, seed data, a local Podman Postgres, tool YAML, env/dependency templates, and the `src/` + `pytest` layout later slices copy into. No application runtime yet.

## What Changes

- Add `mcp_toolbox/seed.sql` with `users`, `customer_orders`, and `actions_log`, plus 10 demo users and 17 orders.
- Add `mcp_toolbox/tools.yaml` exposing `get-order-status`, `find-customer-orders`, `action-log`, and restricted `update-order-status`.
- Scope `get-order-status` to `WHERE order_id = $1 AND customer_email = $2` so another customer's row cannot be returned by order ID alone.
- Add `requirements.txt` and `.env.example` for local PoC: `GOOGLE_API_KEY`, `MEM0_API_KEY`, localhost service URLs. Do not add unused PoC leftovers (`GOOGLE_CLOUD_PROJECT`, `google-cloud-dlp`, `google-cloud-secret-manager`).
- Put Phoenix/OTel, `pyyaml`, `httpx`, and pytest into `requirements.txt` so Podman images / CI do not need a second pip list.
- Add `compose.yaml` with a `postgres` service started by `podman compose`; apply `seed.sql` and verify 10 users / 17 orders.
- Add `pytest.ini`, `src/__init__.py`, and `tests/unit/test_db_and_mcp.py`.
- Document optional `DATABASE_URL`, `TOOLBOX_URL`, `A2A_JUDGE_HOST`, `A2A_MASK_HOST`, `PHOENIX_URL`, `HOST`, `PORT`, and `WEB_PORT` with localhost defaults pointing at Podman services.

## Channels

- **In scope:** none (schema, YAML, env templates, and test harness only)
- **Out of scope:** Web Chat, Voice WebSocket, Terminal CLI, A2A Judge/Masker processes

## Capabilities

### New Capabilities
- `database-and-mcp-tools`: PostgreSQL schema, seed population, MCP Toolbox SQL tool contracts, and the repo test/package layout.

### Modified Capabilities

## Impact

- `mcp_toolbox/seed.sql`, `mcp_toolbox/tools.yaml`, `compose.yaml`, `requirements.txt`, `.env.example`
- `pytest.ini`, `src/__init__.py`, `tests/unit/test_db_and_mcp.py`

## Out of Scope

- Python runtime modules (`src/core/`, FastAPI, A2A, voice)
- MCP Toolbox / A2A / web containers (Group 7)
- Neon / Railway (change `08-railway-deploy`)
