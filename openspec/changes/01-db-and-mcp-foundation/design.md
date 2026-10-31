# Design: Database Schema, Seed Data & MCP Tool Catalog

## Context

See `proposal.md`. This slice creates `mcp_toolbox/`, `compose.yaml` (Postgres service), `requirements.txt`, `.env.example`, `pytest.ini`, and the `src/` package root. Later slices implement application code under `src/`.

## Goals / Non-Goals

**Goals:**
- Commit schema and MCP tool contracts that later slices can import.
- Tenant-scope `get-order-status` at the SQL layer from the first slice.
- Boot local Postgres with `podman compose` and apply `seed.sql`.
- Make `src/` a real Python package and `pytest` runnable from the repo root before any application module lands.

**Non-Goals:**
- Starting MCP Toolbox, A2A, or the web app (Group 7).
- Python application modules (`src/core` and later).
- Neon or Railway (change `08-railway-deploy`).

## Decisions

### Decision 1: seed.sql is the schema source
Commit `mcp_toolbox/seed.sql` with the three tables and demo rows. Apply it to the local Podman Postgres in this slice. Group 7 `run.sh` / compose heredoc MUST match this file.

### Decision 2: Tenant filter on get-order-status
`get-order-status` uses `WHERE order_id = $1 AND customer_email = $2` (not order ID alone). The SQL and parameter names are the contract. The Postgres **hostname** in `tools.yaml` is rewritten in Group 7 (`postgres` on the compose network); host-side pytest still uses `127.0.0.1:5432`.

### Decision 3: One requirements file for local PoC
Include only packages this stack needs locally: ADK, MCP Toolbox, Mem0, FastAPI, Postgres, `pytest`, `pytest-asyncio`, `httpx`, `pyyaml`, and Phoenix/OTel (`arize-phoenix`, `openinference-instrumentation-google-genai`, `openinference-semantic-conventions`, `opentelemetry-sdk==1.42.1` and siblings). Do not add unused PoC leftovers (`google-cloud-dlp`, `google-cloud-secret-manager`, unused `google-auth`). Group 7 must not keep a drifting extra pip list.

### Decision 4: Layout contract (all later slices)
- Package name is `src`. Imports are `from src.core...`, `from src.security...`, `from src.a2a...`, `from src.agents...`, `from src.voice...`, `from src.api...`.
- `pytest.ini` sets `pythonpath = .` and `testpaths = tests`.
- Grow a group's test file task-by-task so sequential apply stays green (`-k` filters until the last task of the group runs the full file).

### Decision 5: Env template is local-first
Document `GOOGLE_API_KEY`, `MEM0_API_KEY`, and localhost defaults for `DATABASE_URL`, `TOOLBOX_URL`, `A2A_*`, `PHOENIX_*`, `HOST`, `PORT`, and `WEB_PORT` (alias of `PORT`). `DATABASE_URL` defaults to the Podman Postgres service. Do not add unused PoC leftovers (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`). Neon / Railway hostnames belong in change `08-railway-deploy`.

### Decision 6: Local Postgres is Podman
Add `compose.yaml` with service `postgres` (official `postgres` image). Start it with `podman compose up -d postgres`. Do not write `docker` or `docker compose` commands. Group 7 extends this file with Toolbox, A2A, web, and optional Phoenix. If `podman compose` is missing, use `podman-compose` as the same Compose spec.

## Risks / Trade-offs

- **[Risk] Podman machine not running on macOS** → Mitigation: README / task verify `podman info`; start `podman machine` if needed.
- **[Risk] `run.sh setup` overwrites tools.yaml** → Mitigation: Group 7 heredoc stays in lockstep with this committed YAML.
