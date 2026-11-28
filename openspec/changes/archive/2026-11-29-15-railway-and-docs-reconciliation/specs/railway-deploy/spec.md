# Spec Delta

## MODIFIED Requirements

### Requirement: Independent Railway Services
The system SHALL deploy separate Railway services `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and optional `phoenix` via `.railway/railway.py` (`.railway/requirements.txt`), `Dockerfile`, and `Dockerfile.toolbox` + `scripts/start-toolbox.mjs`. Each service SHALL declare a `healthcheck` (`/` or `/.well-known/agent.json`). Judge, Masker, and Toolbox MUST NOT be public; Postgres SHALL be Neon.

#### Scenario: Private services stay internal
- **WHEN** the Railway project is inspected
- **THEN** `mcp-toolbox`, `a2a-judge`, and `a2a-masker` have no public domain and `web-voice-app` does

#### Scenario: No Railway Postgres plugin
- **WHEN** Railway services are listed
- **THEN** there is no Railway-managed Postgres service

#### Scenario: Railway definition, healthchecks, and Toolbox container files are present
- **WHEN** `.railway/railway.py`, `.railway/requirements.txt`, `Dockerfile.toolbox`, and `scripts/start-toolbox.mjs` are inspected
- **THEN** `mcp-toolbox` builds from `Dockerfile.toolbox` and starts `scripts/start-toolbox.mjs`, `a2a-judge`, `a2a-masker`, and `web-voice-app` build from `Dockerfile`, and all services declare their respective `healthcheck` paths

### Requirement: Neon DATABASE_URL
On Railway, `web-voice-app` and `mcp-toolbox` SHALL use a Neon pooled `DATABASE_URL` (`sslmode=require`) preserved in `/tmp/tools.yaml` by `scripts/start-toolbox.mjs`. Internal service URLs SHALL use Railway private hostnames; `PHOENIX_PUBLIC_URL` SHALL use a public HTTPS URL with `PHOENIX_ENABLE_AUTH="true"` and `PHOENIX_SECRET` on Railway `phoenix`; `web-voice-app` SHALL bind `0.0.0.0:$PORT`.

#### Scenario: Web binds the platform port
- **WHEN** `web-voice-app` starts on Railway
- **THEN** it listens on `0.0.0.0` and the `PORT` provided by the platform

#### Scenario: Database is Neon
- **WHEN** `DATABASE_URL` is inspected on Railway
- **THEN** it is a Neon host (pooled) and is not committed to git

#### Scenario: Toolbox entrypoint preserves Neon sslmode=require
- **WHEN** `scripts/start-toolbox.mjs` parses a Neon `DATABASE_URL` containing `?sslmode=require`
- **THEN** the generated `/tmp/tools.yaml` includes the SSL query parameters rather than dropping them

#### Scenario: PHOENIX_PUBLIC_URL is browser-reachable and Railway Phoenix requires auth
- **WHEN** `.railway/railway.py` is inspected
- **THEN** `web-voice-app` sets `PHOENIX_PUBLIC_URL` to a public HTTPS URL (`https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}`), not `RAILWAY_PRIVATE_DOMAIN`, and preserves `PHOENIX_API_KEY`, while the Railway `phoenix` service sets `PHOENIX_ENABLE_AUTH="true"` with `PHOENIX_SECRET` via `preserve()`
