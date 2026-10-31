# Proposal: Railway Multi-Service Deploy (`08-railway-deploy`)

## Why

Groups 1–7 build and prove the cascade locally (`podman compose` / `./run.sh`, pytest, one live text turn, one live STT→TTS turn, Podman Postgres). The customer still needs the same topology on Railway as independent services over private DNS, with `GOOGLE_API_KEY`, `MEM0_API_KEY`, and Neon `DATABASE_URL`. Auth/token for the Railway CLI can be added later; this slice must still commit deploy config that does not require a token to write.

## What Changes

- Add Railway service definitions for `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and optional `phoenix`. Postgres is **Neon**, not a Railway Postgres plugin.
- Wire `DATABASE_URL` to the Neon pooled connection string (`sslmode=require`) as a Railway secret. Wire `TOOLBOX_URL` / `A2A_*` / `PHOENIX_URL` to Railway private hostnames. Public HTTPS only on `web-voice-app` (`0.0.0.0:$PORT`).
- Apply Group 1 schema/seed to Neon once with `CREATE TABLE IF NOT EXISTS` / idempotent inserts.
- Document CLI login / `RAILWAY_TOKEN` as a later, skippable step.
- When auth is present, deploy and smoke-test `GET /` on the public web URL.

## Capabilities

### New Capabilities
- `railway-deploy`: Multi-service Railway topology, Neon Postgres, private networking, env wiring, optional CLI/token auth, and post-deploy smoke checks.

### Modified Capabilities

## Impact

- `railway.toml` (or equivalent Railway config)
- README Railway + Neon deploy section
- Optional `RAILWAY_TOKEN` in operator docs only (never committed)

## Channels

- **In scope:** Web Chat and Voice as the public `web-voice-app`; A2A Judge/Masker and MCP Toolbox private; Neon as the database
- **Out of scope:** PSTN/SIP, Vercel, Railway Postgres plugin, local Podman path (Group 7)

## Out of Scope

- Replacing the local `podman compose` / `./run.sh` path
- Committing Railway tokens, Neon URLs with passwords, or API keys
- Combining Judge, Masker, and web into one process
