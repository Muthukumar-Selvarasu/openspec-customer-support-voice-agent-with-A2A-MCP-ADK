# Spec Delta

## ADDED Requirements

### Requirement: Live STT Env Defaults, Pytest Phoenix Flag, and Railway SDK Packaging
`.env.example` SHALL document `VOICE_STT_LIVE_MODEL`, `VOICE_PRICE_STT_IN`, `VOICE_PRICE_STT_OUT`, and empty `RAILWAY_TOKEN=`. `pytest.ini` SHALL set `addopts = -p no:phoenix`, and Railway SDK dependencies SHALL stay isolated in `.railway/requirements.txt` outside `requirements.txt`.

#### Scenario: Extended env, pytest, and Railway packaging files stay aligned
- **WHEN** `.env.example`, `pytest.ini`, and `.railway/requirements.txt` are inspected
- **THEN** live STT model/price vars and empty `RAILWAY_TOKEN=` are documented, `pytest.ini` disables the `phoenix` pytest plugin, and `railway-sdk` lives only in `.railway/requirements.txt`

## MODIFIED Requirements

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
