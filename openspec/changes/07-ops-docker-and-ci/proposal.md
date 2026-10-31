# Proposal: Ops, Podman & CI (`07-ops-docker-and-ci`)

## Why

Groups 1–6 are application code. Operators still need Podman to boot Postgres, MCP Toolbox, A2A Judge, A2A Masker, Phoenix, and the web/voice app as separate containers; an OCI image and CI that run the full pytest suite; a README that matches the `src/` layout; and a local text plus STT/TTS pass before any cloud deploy.

## What Changes

- Extend Group 1 `compose.yaml` and add `run.sh` so `podman compose up` starts `postgres`, `mcp-toolbox` (`npx @toolbox-sdk/server@1.5.0`), one `a2a` process, `web`, and optional `phoenix`. Do not use the docker CLI.
- Keep generated `.env` / `tools.yaml` heredocs local (Group 1 localhost URLs). Do not emit unused PoC leftovers (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`).
- Keep tenant-scoped `get-order-status` SQL in `run.sh gen_config_files` matching committed `mcp_toolbox/tools.yaml`.
- Drop the extra Phoenix pip block; install only via Group 1 `requirements.txt`.
- Add `Dockerfile` (built with `podman build`) and `.github/workflows/ci.yml` that run `pytest` (`unit` + `integration` + `evals`).

## Capabilities

### New Capabilities
- `ops-and-deployment`: Local Podman compose orchestration, OCI image, GitHub Actions CI, and operator README.

### Modified Capabilities

## Impact

- `compose.yaml`
- `run.sh`
- `README.md`
- `Dockerfile`
- `.github/workflows/ci.yml`

## Channels

- **In scope:** container supervision for Web Chat, Voice, CLI, A2A Judge, A2A Masker, MCP Toolbox, Postgres, Phoenix
- **Out of scope:** cloud project provisioning (change `08-railway-deploy`), Neon, PSTN/SIP, Vercel

## Out of Scope

- Combining the 5–6 services into one process
- Committing `.env` or secrets
- Docker Desktop / `docker` CLI
