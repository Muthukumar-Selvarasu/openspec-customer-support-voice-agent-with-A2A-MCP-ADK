# Design: Railway Multi-Service Deploy

## Context

See `proposal.md`. Depends on Groups 1–7: local `podman compose` / `./run.sh`, `Dockerfile`, env-driven hosts, Podman Postgres, and a proven local STT/TTS path. Discovery topology is Postgres → `mcp-toolbox` → `a2a-judge` / `a2a-masker` → `web-voice-app` (+ optional `phoenix`). Local Postgres stays Podman; Railway Postgres is Neon.

## Goals / Non-Goals

**Goals:**
- One Railway project, many services, one image (Group 7 Dockerfile), different start commands.
- Neon as the managed database (`DATABASE_URL` secret).
- Private DNS for Toolbox and A2A; public HTTPS only for web/voice.
- Config that can be committed before the operator logs in.

**Non-Goals:**
- Changing cascade behavior.
- Replacing local Podman compose.
- Storing tokens or Neon passwords in git.
- Railway Postgres plugin.

## Decisions

### Decision 1: Config first, auth later
Commit `railway.toml` (and README deploy steps) without calling `railway up`. Deploy tasks run only when `railway whoami` succeeds or `RAILWAY_TOKEN` is set. Until then, skip those checkboxes.

### Decision 2: One Dockerfile, four-plus start commands
Reuse Group 7's image.

- `web-voice-app`: `python -m src.api.web` (listen `0.0.0.0:$PORT`)
- `a2a-judge` / `a2a-masker`: same factories as Group 4, **one factory per Railway service** (local Group 7 still runs both in one `run_servers` process)
- `mcp-toolbox`: Toolbox server with generated `tools.yaml` pointed at Neon `DATABASE_URL`
- `phoenix`: optional, same image extra CMD or official image

Judge and Masker as two Railway services (not one process with two threads) so they scale independently.

### Decision 3: Neon is the Railway database
Do not add a Railway Postgres plugin. Create (or reuse) a Neon project, copy the **pooled** connection string (`-pooler` host, `sslmode=require`) into Railway as `DATABASE_URL` on `web-voice-app` and `mcp-toolbox`. Use the **direct** Neon URL for one-shot schema/seed. Local Podman Postgres is unchanged.

### Decision 4: Private networking for app services
`TOOLBOX_URL=http://${{mcp-toolbox.RAILWAY_PRIVATE_DOMAIN}}:5000`, `A2A_JUDGE_HOST=${{a2a-judge.RAILWAY_PRIVATE_DOMAIN}}`, same pattern for masker and Phoenix. `DATABASE_URL` is the Neon secret, not `${{Postgres.DATABASE_URL}}`.

### Decision 5: Seed on first deploy only
Do not run destructive `DROP TABLE` seed on every Railway restart. Apply Group 1 schema to Neon with `CREATE TABLE IF NOT EXISTS` / idempotent inserts, or a one-shot setup job.

### Decision 6: Auth methods
Prefer `railway login` (browser or device code) when an operator is present. Prefer `RAILWAY_TOKEN` in CI. Neither is required to finish config tasks.

## Risks / Trade-offs

- **[Risk] Token not available yet** → Mitigation: skip deploy tasks; config remains reviewable.
- **[Risk] tools.yaml still hardcodes 127.0.0.1 Postgres** → Mitigation: generate or template Toolbox source host from `DATABASE_URL` / `PG*` at container start.
- **[Risk] Two A2A processes vs one `run_servers` binary** → Mitigation: each Railway service sets only its own `A2A_*_HOST/PORT` and starts that factory.
- **[Risk] Neon pooler vs session features** → Mitigation: app/Toolbox use pooled URL; DDL/seed uses the direct URL.

## Migration Plan

1. Finish Group 7 local cascade on Podman (text + voice).
2. Commit Railway config (no Postgres plugin).
3. When the operator supplies login or `RAILWAY_TOKEN`, create the project, set Neon `DATABASE_URL` + API keys, deploy.
4. Smoke `GET /`. Rollback is undeploy / previous Railway deployment.

## Open Questions

- Whether Judge and Masker share one image process or two services is decided as two services (Decision 2). Phoenix on/off can stay an operator flag without changing specs.
