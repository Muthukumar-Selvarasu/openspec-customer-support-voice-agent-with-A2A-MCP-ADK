# database-and-mcp-tools Specification

## Purpose

Defines the PostgreSQL `toolbox_db` schema, demo seed population, and MCP Toolbox SQL tools the support agent uses to read orders and record audited customer intents.

## Requirements

### Requirement: Order Database Schema and Seed Population
The system SHALL provision `users`, `customer_orders`, and `actions_log` and seed 10 shoppers and 17 orders across all five statuses. `mcp_toolbox/seed.sql` SHALL be idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, conflict-safe inserts, no `DROP TABLE IF EXISTS`) and SHALL guard `GRANT ... TO toolbox_user` with a `pg_roles` check so it runs cleanly on Neon and local Postgres.

#### Scenario: Seed file defines required tables and demo accounts
- **WHEN** `mcp_toolbox/seed.sql` is inspected
- **THEN** it creates `users`, `customer_orders`, and `actions_log` and inserts 10 users (4 premium, 6 standard) and 17 orders

#### Scenario: Seed file is safe to re-run on Neon and local Postgres
- **WHEN** `mcp_toolbox/seed.sql` is applied twice to either Neon or local Podman Postgres
- **THEN** it contains no `DROP TABLE IF EXISTS`, guards `toolbox_user` grants with a `pg_roles` check, succeeds without error, and preserves `10` demo users and `17` demo orders without duplicating rows

### Requirement: Tenant-Scoped MCP Order Lookup Tools
The MCP tool catalog SHALL expose parameterized SQL tools `get-order-status`, `find-customer-orders`, `action-log`, and `update-order-status`, and `get-order-status` MUST filter by both `order_id` and `customer_email`. The `action-log` `action_type` parameter description in `mcp_toolbox/tools.yaml` SHALL match the canonical names in `src/core/prompts.py` (`UPDATE_ORDER_STATUS`, `RETURN_ITEM`, `UPDATE_DELIVERY_ADDRESS`, `UPDATE_PROFILE_DETAILS`).

#### Scenario: get-order-status requires customer email
- **WHEN** `mcp_toolbox/tools.yaml` is loaded
- **THEN** `get-order-status` includes parameters `order_id` and `customer_email` and SQL `WHERE order_id = $1 AND customer_email = $2`

#### Scenario: Restricted write tool remains in the catalog
- **WHEN** toolset `cs_agent_tools` is listed
- **THEN** it includes `update-order-status` for compliance testing while `action-log` remains the intended mutation path

#### Scenario: action-log action types match prompts.py
- **WHEN** `mcp_toolbox/tools.yaml` is loaded
- **THEN** `action-log`'s `action_type` description lists `UPDATE_ORDER_STATUS`, `RETURN_ITEM`, `UPDATE_DELIVERY_ADDRESS`, and `UPDATE_PROFILE_DETAILS`

### Requirement: Local PoC Dependencies, Env Template, and Pytest Layout
`requirements.txt` SHALL list direct PoC packages with upper major bounds aligned to the running stack (`google-adk>=2.15.0,<3`, `google-genai>=2.34.0,<3`, `toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`, FastAPI/Uvicorn, Postgres, OTel exporters) and MUST NOT include `requests`, `arize-phoenix`, or unused GCP leftovers. `.env.example` SHALL document localhost defaults without GCP vars; `pytest.ini` SHALL set `pythonpath = .`.

#### Scenario: Requirements and env templates match local PoC
- **WHEN** `requirements.txt`, `.env.example`, and `pytest.ini` are inspected
- **THEN** `requirements.txt` declares `google-adk>=2.15.0,<3`, `google-genai>=2.34.0,<3`, `toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`, `openinference-semantic-conventions`, `opentelemetry-sdk==1.42.1`, `opentelemetry-api==1.42.1`, `opentelemetry-exporter-otlp-proto-http==1.42.1`, and `opentelemetry-semantic-conventions==0.63b1`, omits `arize-phoenix`, `requests`, `google-cloud-dlp`, `google-cloud-secret-manager`, and `google-auth`, `.env.example` documents localhost defaults with `WEB_PORT` as an alias of `PORT` (without `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, or `MODEL_ARMOR_TEMPLATE_ID`), and `pytest.ini` sets `pythonpath = .`

### Requirement: Local Postgres Runs in Podman
Local Postgres SHALL be the `postgres` service in `compose.yaml`, started with `podman compose` (not the docker CLI). Default `DATABASE_URL` SHALL point at that container (`toolbox_db` / `toolbox_user` / `mysecretpassword` on `127.0.0.1:5432`). Applying `mcp_toolbox/seed.sql` SHALL create the three tables and the demo rows.

#### Scenario: Podman Postgres accepts seed.sql
- **WHEN** `podman compose up -d postgres` has started and `mcp_toolbox/seed.sql` is applied
- **THEN** `users` has 10 rows and `customer_orders` has 17 rows

### Requirement: Reproducible Dependency Constraints Lockfile
The repository SHALL commit a Linux/universal Python 3.12 `constraints.txt` file alongside `requirements.txt` so `pip install -r requirements.txt -c constraints.txt` resolves deterministic package versions across host `.venv`, container builds, CI, and Railway without adding transitive dependencies (such as `google-auth`) into `requirements.txt`.

#### Scenario: Constraints file locks transitive versions without polluting requirements.txt
- **WHEN** `constraints.txt` and `requirements.txt` are inspected
- **THEN** `constraints.txt` exists with exact `==` version pins compatible with Python 3.12 on Linux and macOS, passes `pip install --dry-run -r requirements.txt -c constraints.txt`, and `requirements.txt` stays free of `google-auth`, `requests`, and `arize-phoenix`

### Requirement: Live STT Env Defaults, Pytest Phoenix Flag, and Railway SDK Packaging
`.env.example` SHALL document `VOICE_STT_LIVE_MODEL`, `VOICE_PRICE_STT_IN`, `VOICE_PRICE_STT_OUT`, and empty `RAILWAY_TOKEN=`. `pytest.ini` SHALL set `addopts = -p no:phoenix`, and Railway SDK dependencies SHALL stay isolated in `.railway/requirements.txt` outside `requirements.txt`.

#### Scenario: Extended env, pytest, and Railway packaging files stay aligned
- **WHEN** `.env.example`, `pytest.ini`, and `.railway/requirements.txt` are inspected
- **THEN** live STT model/price vars and empty `RAILWAY_TOKEN=` are documented, `pytest.ini` disables the `phoenix` pytest plugin, and `railway-sdk` lives only in `.railway/requirements.txt`
