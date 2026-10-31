# database-and-mcp-tools Specification

## Purpose

Defines the PostgreSQL `toolbox_db` schema, demo seed population, and MCP Toolbox SQL tools the support agent uses to read orders and record audited customer intents.

## Requirements

### Requirement: Order Database Schema and Seed Population
The system SHALL provision PostgreSQL tables `users`, `customer_orders`, and `actions_log` and SHALL seed 10 demo shoppers and 17 orders spanning all five order statuses.

#### Scenario: Seed file defines required tables and demo accounts
- **WHEN** `mcp_toolbox/seed.sql` is inspected
- **THEN** it creates `users`, `customer_orders`, and `actions_log` and inserts 10 users (4 premium, 6 standard) and 17 orders

### Requirement: Tenant-Scoped MCP Order Lookup Tools
The MCP tool catalog SHALL expose parameterized SQL tools `get-order-status`, `find-customer-orders`, `action-log`, and `update-order-status`, and `get-order-status` MUST filter by both `order_id` and `customer_email`.

#### Scenario: get-order-status requires customer email
- **WHEN** `mcp_toolbox/tools.yaml` is loaded
- **THEN** `get-order-status` includes parameters `order_id` and `customer_email` and SQL `WHERE order_id = $1 AND customer_email = $2`

#### Scenario: Restricted write tool remains in the catalog
- **WHEN** toolset `cs_agent_tools` is listed
- **THEN** it includes `update-order-status` for compliance testing while `action-log` remains the intended mutation path

### Requirement: Local PoC Dependencies, Env Template, and Pytest Layout
`requirements.txt` SHALL list only packages needed to run this stack locally (ADK, MCP Toolbox, Mem0, FastAPI, Postgres, pytest, Phoenix/OTel). Do not add unused PoC leftovers (`google-cloud-dlp`, `google-cloud-secret-manager`, unused `google-auth`). `.env.example` SHALL document localhost defaults for `DATABASE_URL`, `TOOLBOX_URL`, `A2A_*`, `PHOENIX_*`, `HOST`, `PORT`, and `WEB_PORT`, plus `GOOGLE_API_KEY` and `MEM0_API_KEY` for live local turns. Do not add `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, or `MODEL_ARMOR_TEMPLATE_ID`. The repo SHALL provide `pytest.ini` with `pythonpath = .` so later slices import `src.*`.

#### Scenario: Requirements and env templates match local PoC
- **WHEN** `requirements.txt` and `.env.example` are inspected
- **THEN** they include the local packages and localhost URLs, `WEB_PORT` is documented as an alias of `PORT`, and unused DLP / Secret Manager / Model Armor packages and keys are absent

### Requirement: Local Postgres Runs in Podman
Local Postgres SHALL be the `postgres` service in `compose.yaml`, started with `podman compose` (not the docker CLI). Default `DATABASE_URL` SHALL point at that container (`toolbox_db` / `toolbox_user` / `mysecretpassword` on `127.0.0.1:5432`). Applying `mcp_toolbox/seed.sql` SHALL create the three tables and the demo rows.

#### Scenario: Podman Postgres accepts seed.sql
- **WHEN** `podman compose up -d postgres` has started and `mcp_toolbox/seed.sql` is applied
- **THEN** `users` has 10 rows and `customer_orders` has 17 rows
