# railway-deploy Specification

## Purpose

Deploys the cascade voice and chat platform to Railway as independent services on a private network, with public HTTPS only on the web/voice app and Neon as Postgres, after the stack has already been proven locally on Podman.

## Requirements

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

### Requirement: Secrets Are Not Committed
`GOOGLE_API_KEY`, `MEM0_API_KEY`, Neon `DATABASE_URL`, and `RAILWAY_TOKEN` MUST NOT be committed to git. Deploy using CLI login or `RAILWAY_TOKEN` MAY be skipped until the operator supplies auth.

#### Scenario: Token is optional until deploy
- **WHEN** Railway CLI is not authenticated and `RAILWAY_TOKEN` is unset
- **THEN** config files still exist and the deploy step is skipped rather than failing the change

#### Scenario: Example env names the token and has no value
- **WHEN** `.env.example` is inspected
- **THEN** it contains `RAILWAY_TOKEN=` and that line has no token value

### Requirement: Local run stays available
The local stack SHALL still start with `./run.sh` and SHALL NOT require `RAILWAY_TOKEN`. A Railway deploy SHALL use `RAILWAY_TOKEN` from `.env` or an existing CLI login.

#### Scenario: Local start does not need Railway
- **WHEN** the operator runs the local stack
- **THEN** `./run.sh` starts it without `RAILWAY_TOKEN`

### Requirement: Post-Deploy Public Smoke Check
After a successful deploy, `GET` on the public `web-voice-app` origin SHALL return 200 for `/`.

#### Scenario: Public root is healthy
- **WHEN** `web-voice-app` has deployed and a public URL exists
- **THEN** `GET /` returns 200

### Requirement: Pinned Phoenix Container Image on Railway
The optional `phoenix` service in `.railway/railway.py` SHALL pin the explicit container image tag `arizephoenix/phoenix:version-22.0.1` matching `compose.yaml` and MUST NOT use the floating `:latest` tag.

#### Scenario: Railway Phoenix service uses pinned version tag
- **WHEN** `.railway/railway.py` and `compose.yaml` are inspected
- **THEN** `.railway/railway.py` uses `image("arizephoenix/phoenix:version-22.0.1")` (not `:latest`), matching the `version-22.0.1` tag in `compose.yaml`
