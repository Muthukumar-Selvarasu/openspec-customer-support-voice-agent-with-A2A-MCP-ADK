# Spec Delta: `railway-deploy`

## Purpose

Deploys the cascade voice and chat platform to Railway as independent services on a private network, with public HTTPS only on the web/voice app and Neon as Postgres, after the stack has already been proven locally on Podman.

## ADDED Requirements

### Requirement: Independent Railway Services
The system SHALL be deployable as separate Railway services `mcp-toolbox`, `a2a-judge`, `a2a-masker`, and `web-voice-app`, with optional `phoenix`. Judge, Masker, and Toolbox MUST NOT be public. Postgres SHALL be Neon, not a Railway Postgres plugin.

#### Scenario: Private services stay internal
- **WHEN** the Railway project is inspected
- **THEN** `mcp-toolbox`, `a2a-judge`, and `a2a-masker` have no public domain and `web-voice-app` does

#### Scenario: No Railway Postgres plugin
- **WHEN** Railway services are listed
- **THEN** there is no Railway-managed Postgres service

### Requirement: Neon DATABASE_URL
On Railway, `web-voice-app` and `mcp-toolbox` SHALL use a Neon pooled `DATABASE_URL` with `sslmode=require`. `TOOLBOX_URL`, `A2A_JUDGE_HOST`, `A2A_MASK_HOST`, and `PHOENIX_URL` SHALL use Railway private hostnames, not `127.0.0.1`. `web-voice-app` SHALL bind `0.0.0.0` and `$PORT`.

#### Scenario: Web binds the platform port
- **WHEN** `web-voice-app` starts on Railway
- **THEN** it listens on `0.0.0.0` and the `PORT` provided by the platform

#### Scenario: Database is Neon
- **WHEN** `DATABASE_URL` is inspected on Railway
- **THEN** it is a Neon host (pooled) and is not committed to git

### Requirement: Secrets Are Not Committed
`GOOGLE_API_KEY`, `MEM0_API_KEY`, Neon `DATABASE_URL`, and `RAILWAY_TOKEN` MUST NOT be committed to git. Deploy using CLI login or `RAILWAY_TOKEN` MAY be skipped until the operator supplies auth.

#### Scenario: Token is optional until deploy
- **WHEN** Railway CLI is not authenticated and `RAILWAY_TOKEN` is unset
- **THEN** config files still exist and the deploy step is skipped rather than failing the change

### Requirement: Post-Deploy Public Smoke Check
After a successful deploy, `GET` on the public `web-voice-app` origin SHALL return 200 for `/`.

#### Scenario: Public root is healthy
- **WHEN** `web-voice-app` has deployed and a public URL exists
- **THEN** `GET /` returns 200
