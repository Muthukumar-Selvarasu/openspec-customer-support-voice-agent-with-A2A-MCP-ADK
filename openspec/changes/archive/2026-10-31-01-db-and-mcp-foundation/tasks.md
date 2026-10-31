# Tasks: `01-db-and-mcp-foundation`

Application code lives under `src/` (`from src...`). Tests live under `tests/unit`, `tests/integration`, and `tests/evals`. `pytest.ini` sets `pythonpath = .` and `testpaths = tests`.

## 1. Harness, dependencies, and env template

- [x] 1.1 Create `pytest.ini` (`pythonpath = .`, `testpaths = tests`), `src/__init__.py`, and `tests/unit/`, then verify `pytest --collect-only` exits 0 from the repo root
- [x] 1.2 Write `requirements.txt` for the local PoC (ADK, MCP Toolbox, Mem0, FastAPI, Postgres); include `pytest`, `pytest-asyncio`, `httpx`, `pyyaml`, `arize-phoenix`, `openinference-instrumentation-google-genai`, `openinference-semantic-conventions`, and pin `opentelemetry-sdk==1.42.1`, `opentelemetry-api==1.42.1`, `opentelemetry-exporter-otlp-proto-http==1.42.1`, `opentelemetry-semantic-conventions==0.63b1`; do not add unused PoC leftovers (`google-cloud-dlp`, `google-cloud-secret-manager`, unused `google-auth`); add `tests/unit/test_db_and_mcp.py` that asserts those leftover packages are absent and the local packages are present; verify with `pytest tests/unit/test_db_and_mcp.py -k requirements`
- [x] 1.3 Write `.env.example` with `GOOGLE_API_KEY`, `MEM0_API_KEY`, `MASK`, `AGENT_RESPONSE_STREAM`, and `TELEMETRY`; add `DATABASE_URL`, `TOOLBOX_URL`, `A2A_JUDGE_HOST`, `A2A_JUDGE_PORT`, `A2A_MASK_HOST`, `A2A_MASK_PORT`, `PHOENIX_URL`, `PHOENIX_PUBLIC_URL`, `HOST`, `PORT`, and `WEB_PORT` (alias of `PORT`) with localhost defaults; do not add unused PoC leftovers (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`); extend `tests/unit/test_db_and_mcp.py` and verify with `pytest tests/unit/test_db_and_mcp.py -k env`

## 2. Schema, seed, and MCP tools

- [x] 2.1 Create `mcp_toolbox/seed.sql` that defines `users`, `customer_orders`, and `actions_log` and seeds 10 shoppers (4 premium, 6 standard) and 17 orders across all five statuses; extend `tests/unit/test_db_and_mcp.py` and verify with `pytest tests/unit/test_db_and_mcp.py -k seed`
- [x] 2.2 Create `mcp_toolbox/tools.yaml` with toolset `cs_agent_tools` exposing `get-order-status`, `find-customer-orders`, `action-log`, and restricted `update-order-status`; make `get-order-status` take `order_id` + `customer_email` and SQL `WHERE order_id = $1 AND customer_email = $2`; extend `tests/unit/test_db_and_mcp.py` and verify with `pytest tests/unit/test_db_and_mcp.py`

## 3. Local Postgres via Podman

- [x] 3.1 Add `compose.yaml` with a `postgres` service (official `postgres` image, database `toolbox_db`, user `toolbox_user`, password `mysecretpassword`, host port `5432`); commands MUST be `podman compose` (not `docker`); verify `podman info` works and `podman compose config` lists service `postgres`
- [x] 3.2 Start Postgres with `podman compose up -d postgres`, apply `mcp_toolbox/seed.sql`, and verify 10 users and 17 orders via `podman compose exec postgres psql -U toolbox_user -d toolbox_db -c "SELECT count(*) FROM users;"` and the matching orders count; extend `tests/unit/test_db_and_mcp.py` or record those commands; verify with `pytest tests/unit/test_db_and_mcp.py -k postgres_podman` or the `psql` counts
