# Design

## Context

See `proposal.md` for motivation and drift citations. Remaining deployment, schema, spec-metadata, and documentation gaps after Changes `16`, `13`, and `14`:
- `scripts/start-toolbox.mjs` parses `DATABASE_URL` with `new URL(...)` and rewrites only `host`, `port`, `database`, `user`, `password` into `/tmp/tools.yaml`, dropping `?sslmode=require` (and any other Neon query params).
- `.railway/railway.py` line 65 sets `PHOENIX_PUBLIC_URL` to `_private("phoenix")` (`http://${{phoenix.RAILWAY_PRIVATE_DOMAIN}}:${{phoenix.PORT}}`), sets `PHOENIX_ENABLE_AUTH: "false"` (unsafe if Phoenix is exposed on a public Railway domain with customer trace content), and omits healthchecks on `mcp-toolbox`, `a2a-judge`, `a2a-masker`, and `phoenix`. `src/static/architecture.html` line 38 hardcodes `href="http://localhost:6006"`, and `src/api/web.py` line 189 hardcodes `"Toolbox :5000"`.
- `mcp_toolbox/seed.sql` starts with `DROP TABLE IF EXISTS`, bare `CREATE TABLE` / `INSERT INTO`, and unguarded `GRANT ... TO toolbox_user`, which risks data loss and fails on Neon (`neondb_owner`).
- `mcp_toolbox/tools.yaml` and `run.sh:153` list `CANCEL_ORDER, RETURN_ORDER, UPDATE_ADDRESS, UPDATE_PROFILE` whereas `src/core/prompts.py` specifies `UPDATE_ORDER_STATUS, RETURN_ITEM, UPDATE_DELIVERY_ADDRESS, UPDATE_PROFILE_DETAILS`.
- `run.sh` ignores `compose.runtime.yaml` on `down`/`ps` and unconditionally starts `phoenix`; `compose.yaml` omits `VOICE_STT_LIVE_MODEL` / `VOICE_PRICE_STT_*` forwarding.
- `docs/ENGAGEMENT.md`, `docs/01-discovery.md`, `docs/02-problem-metrics.md`, `docs/03-poc.md`, and `docs/DEVELOPMENT_STEPS.md` have accumulated drift across models, prices, paths, schema details, voice UI controls, SVG colors, `total_response`, blocker flood bounds, plain-text ` · premium`, and missing Steps `12`–`16`.

## Goals / Non-Goals

**Goals:**
- Preserve Neon SSL query parameters in MCP Toolbox on Railway.
- Make `"Open Phoenix"` and trace links work securely on both local Podman (`http://localhost:6006`, loopback unauthenticated) and Railway (`https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}` with `PHOENIX_ENABLE_AUTH: "true"` and `PHOENIX_SECRET: preserve()`), and declare healthchecks on all Railway services.
- Make `mcp_toolbox/seed.sql` idempotent and Neon-role-safe so re-running it never drops tables, fails on missing `toolbox_user`, or duplicates demo rows.
- Align `mcp_toolbox/tools.yaml` / `run.sh` action names, optional local Phoenix, `compose.runtime.yaml` lifecycle, spec headings/metadata (preserving Change `16`'s dependency/Phoenix specs), and all 5 FDE `docs/` files + `README.md` with the implemented codebase.

**Non-Goals:**
- Rewriting `docs/DESIGN.md` (external FDE Companion reference; spec wording is fixed to avoid falsely claiming `docs/DESIGN.md` defines dark tokens).
- Re-introducing GCP DLP, Model Armor, or a separate standalone Layer 2b topical microservice (domain scope is handled in Layer 2 A2A Judge + `SQL_PROMPT_INSTRUCTION` per Change `13`).
- Reverting any Change `16` dependency, `constraints.txt`, or `phoenix:version-22.0.1` updates.
- Automating live Railway redeployment inside this change (redeploy runs cleanly after Changes `16`, `13`, `14`, and `15` are verified).

## Decisions

1. **Preserving `DATABASE_URL` query parameters in `scripts/start-toolbox.mjs`:**
   - Extract `parsed.searchParams` from `DATABASE_URL` (e.g., `sslmode=require`, `channel_binding=require`).
   - Emit a `queryParams:` YAML map under `sources.cs-postgres` in `/tmp/tools.yaml` (verified against `@toolbox-sdk/server@1.5.0` Postgres source schema) whenever `parsed.searchParams` is non-empty, leaving local Podman Postgres URLs without query params unaffected.
   - Add a Node/pytest unit test executing `start-toolbox.mjs` (or its pure config-rewrite helper) against a Neon pooled URL with `?sslmode=require` to verify `/tmp/tools.yaml` preserves `sslmode: "require"`.

2. **Authenticated browser-reachable Railway Phoenix, service healthchecks & dynamic inspector labels (`.railway/railway.py`, `src/api/web.py`, `src/static/architecture.html`):**
   - In `.railway/railway.py`, set `PHOENIX_PUBLIC_URL` on `web-voice-app` to `"https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}"` (keeping `PHOENIX_URL` as `_private("phoenix")` for internal OTLP export and preserving `PHOENIX_API_KEY: preserve()` on `web-voice-app` so OTLP export and `/v1/projects` lookups authenticate cleanly), AND flip `phoenix` on Railway to `PHOENIX_ENABLE_AUTH: "true"` with `PHOENIX_SECRET: preserve()` (preserving Change 16's `image("arizephoenix/phoenix:version-22.0.1")`) so public browser access to traces containing customer prompts/PII requires login while local loopback Compose (`127.0.0.1:6006` with `PHOENIX_ENABLE_AUTH: "false"`) stays unaffected.
   - Add Railway `healthcheck` declarations in `.railway/railway.py`: `mcp-toolbox` (`healthcheck="/"`), `a2a-judge` (`healthcheck="/.well-known/agent.json"`), `a2a-masker` (`healthcheck="/.well-known/agent.json"`), and `phoenix` (`healthcheck="/"`).
   - In `src/api/web.py`, update `GET /architecture` to read `src/static/architecture.html` and substitute the `"Open Phoenix"` href placeholder (`http://localhost:6006` or `__PHOENIX_PUBLIC_URL__`) with `html.escape(resolve_service_settings().phoenix_public_url, quote=True)` (defaulting to `http://localhost:6006` when unset), returning `HTMLResponse`, and change hardcoded `"Toolbox :5000"` in `TOOLS[name]["path"]` (`web.py:189`) to `"MCP Toolbox"`.

3. **Idempotent, Neon-safe `mcp_toolbox/seed.sql` & synced `run.sh` heredoc:**
   - Replace `DROP TABLE IF EXISTS ...` + `CREATE TABLE` + `CREATE INDEX` with `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`.
   - Use `ON CONFLICT (email) DO NOTHING` for `users`.
   - For `customer_orders`, use explicit `order_id` `1..17` in `INSERT INTO customer_orders (...) VALUES (...) ON CONFLICT (order_id) DO NOTHING;` plus `SELECT setval(pg_get_serial_sequence('customer_orders', 'order_id'), COALESCE((SELECT MAX(order_id) FROM customer_orders), 1));` — keeps `VALUES (...)` syntax intact for `_sql_tuples()`, guarantees deterministic order IDs 1–17, and is 100% safe to re-run! Update `test_db_and_mcp.py` regex `CREATE TABLE (?:IF NOT EXISTS )?{table}\b`.
   - Wrap the `GRANT ... TO toolbox_user;` statements in `DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'toolbox_user') THEN ... END IF; END $$;` so Neon Postgres (`neondb_owner`) applies `seed.sql` cleanly while local Podman Postgres still grants privileges to `toolbox_user`.
   - Update `action-log`'s `action_type` description in both `mcp_toolbox/tools.yaml` and `run.sh`'s `.run/tools.yaml` heredoc (line 153) to `UPDATE_ORDER_STATUS, RETURN_ITEM, UPDATE_DELIVERY_ADDRESS, UPDATE_PROFILE_DETAILS`.

4. **Local Podman ops, architecture SVG labels & `theme.css` cleanup (`run.sh`, `compose.yaml`, `src/static/architecture.svg`, `src/static/theme.css`):**
   - Add a helper in `run.sh` (`compose_file()`) that returns `compose.runtime.yaml` when present, otherwise `compose.yaml`, and use it in `down` and `ps` so macOS port-5000 stacks tear down and inspect cleanly.
   - Make local Phoenix genuinely optional in `run.sh` (`compose_up`): omit `phoenix` from the `up` service list when `PHOENIX=false` or `--no-phoenix` is passed (defaulting to starting `phoenix` for backward compatibility).
   - Forward `VOICE_STT_LIVE_MODEL`, `VOICE_PRICE_STT_IN`, and `VOICE_PRICE_STT_OUT` (with `.env.example` defaults) in `compose.yaml`'s `web` service environment block while preserving Change 16's `phoenix:version-22.0.1` and `127.0.0.1:6006:6006`.
   - Update `src/static/architecture.svg` labels and add explicit `GUARDRAIL` badges/subtitles on all three guardrail nodes so reviewers immediately see them: STT `gemini-3.1-flash-lite` → `gemini-3.1-flash-live-preview`, Sanitizer (`GUARDRAIL` badge, `length & char whitelist`, `Guardrail L1 · in-process`), Security & Topic Judge (`GUARDRAIL · A2A`, `ADK agent · :10002`, `Guardrail L2 · security + scope`), and Data Masker (`GUARDRAIL · A2A`, `local regex · :10003`, `Guardrail L3 · PII scrub`), and add a matching `guardrail` legend entry in `src/static/architecture.html`.
   - Update `src/static/theme.css` line 4 comment `(light-only)` → `(light default)` and remove the unused `.ds-aurora-wrap` block.

5. **FDE docs, `README.md` & spec reconciliation (`README.md`, `docs/`, `openspec/specs/`):**
   - Update `README.md` to preserve Change 16's `-c constraints.txt` / standalone Phoenix notes while reflecting idempotent `seed.sql` (documenting the explicit reset command), authenticated Railway Phoenix (`PHOENIX_ENABLE_AUTH=true` + `PHOENIX_SECRET`), optional `PHOENIX=false ./run.sh`, defense-in-depth security + domain-scope guardrails (Change 13), and Railway packaging files (`.railway/railway.py`, `.railway/requirements.txt`, `Dockerfile.toolbox`, `scripts/start-toolbox.mjs`), while preserving all tokens asserted by `test_readme_documents_local_podman_launch` (including `08-railway-deploy` and local Podman instructions).
   - Update `web-and-cli-channels/spec.md` (`Shared Design System Stylesheet Delivery`) so it states light base tokens are adapted from `docs/DESIGN.md` while dark tokens (`:root[data-theme="dark"]`) are app-specific, and update `ops-and-deployment/spec.md` (`Container Image and CI`) to preserve Change 16's `-c constraints.txt` / no-`arize-phoenix` contract and `Local Full Cascade` PTT/Quick settle behavior.
   - Update each of the 5 audited docs in place (`ENGAGEMENT.md`, `01-discovery.md`, `02-problem-metrics.md`, `03-poc.md`, `DEVELOPMENT_STEPS.md`) to reflect the post-Change-16/13/14/15 system accurately: local regex security, defense-in-depth customer-support domain-scope guardrail (Layer 2 A2A Judge `OFF_TOPIC` + `SQL_PROMPT_INSTRUCTION` domain scope across Web, Voice, and CLI), 2-stage CLI (`src/api/cli.py`), Live STT (`gemini-3.1-flash-live-preview` `$3.00/$4.50`), `src/voice/cost.py`, Push-to-Talk (`BARGE_RMS = 0.12`, no Hold/Resume), sentence-level masked voice streaming, teal/coral `architecture.svg` colors + updated guardrail badges/labels, `POST /api/session`, actual `customer_orders` & `actions_log` FKs/DDL, static demo hints, plain-text ` · premium` header indicator, blocker flood bounds (`A{64,}`, `(?:%s){2,}`), actual `total_response` formula (`stt + answer_sec`), demo-only bare `user_id` auth scope note, accurate artifact paths, and Steps 21–25 (`12-design-system-ui` plus `16`, `13`, `14`, and `15`).

## Risks / Trade-offs

- **[Risk] `@toolbox-sdk/server@1.5.0` YAML key for Postgres SSL params might differ if Toolbox expects `queryParams` vs `sslmode`** → Mitigation: Verify the exact supported key against `@toolbox-sdk/server@1.5.0` schema/CLI help during `opsx apply` Task 1.1 before finalizing the test.
- **[Risk] Making `seed.sql` idempotent means re-running `seed.sql` no longer resets modified local demo data** → Mitigation: Document `psql ... -c "DROP TABLE IF EXISTS actions_log, customer_orders, users;"` in `seed.sql` comments / `README.md` for explicit local resets while keeping default `seed.sql` non-destructive for Neon.
- **[Risk] Enabling `PHOENIX_ENABLE_AUTH=true` on Railway requires `PHOENIX_SECRET` (and `PHOENIX_API_KEY` on `web-voice-app` OTLP header if Phoenix enforces ingest auth)** → Mitigation: Verify Phoenix v22 auth env requirements during apply (`PHOENIX_SECRET` + `PHOENIX_API_KEY` / `OTEL_EXPORTER_OTLP_HEADERS` if needed for authenticated OTLP export) and document the Railway secrets in `README.md`.
