# Tasks: `08-railway-deploy`

Do this only after Group 7 local cascade (Podman, text + STT/TTS) has passed. Config tasks do not need Railway auth. Deploy tasks skip until `railway whoami` succeeds or `RAILWAY_TOKEN` is set in `.env`. Local Podman Postgres stays; Railway Postgres is Neon. `./run.sh` stays the local run path and does not read `RAILWAY_TOKEN`.

## 1. Railway config (no token)

- [x] 1.1 Add `railway.toml` (or equivalent) defining services `mcp-toolbox`, `a2a-judge`, `a2a-masker`, and `web-voice-app` (optional `phoenix`); do **not** add a Railway Postgres plugin; web uses Group 7 Dockerfile `CMD python -m src.api.web`; Judge/Masker/Toolbox have no public domain; verify the file lists those four required services and does not list `postgres`
- [x] 1.2 Wire env: `DATABASE_URL` is a Neon pooled URL (`sslmode=require`) set as a Railway secret on `web-voice-app` and `mcp-toolbox`; `TOOLBOX_URL` / `A2A_JUDGE_HOST` / `A2A_MASK_HOST` / `PHOENIX_URL` from private hostnames; `web-voice-app` binds `0.0.0.0` and `$PORT`; document `GOOGLE_API_KEY` and `MEM0_API_KEY` as runtime secrets not in git; verify with `pytest tests/unit/test_db_and_mcp.py -k railway_config` or a file inspection that no secret values are committed
- [x] 1.3 Add a README deploy section for Neon (create project, copy pooled `DATABASE_URL`, apply Group 1 schema/seed once with `CREATE TABLE IF NOT EXISTS` / idempotent inserts) and the two run paths: `./run.sh` for local, and Railway when `RAILWAY_TOKEN` is set in `.env` or `railway whoami` succeeds; verify the README names both paths and Neon, and does not embed a connection string password or a token value
- [x] 1.4 Add an empty `RAILWAY_TOKEN=` line to `.env.example`. Do not write a token value. The real token stays in `.env`, which remains gitignored. Verify `.env.example` contains `RAILWAY_TOKEN=` with nothing after the equals sign, and `.gitignore` ignores `.env`

## 2. Deploy when auth exists (skip until then)

- [x] 2.1 When `railway whoami` works or `RAILWAY_TOKEN` is set in `.env`, create/link the project, set Neon `DATABASE_URL` and API key secrets, apply schema/seed to Neon once, and deploy the services; skip this task until auth is provided; do not commit the token; verify `railway status` shows the app services and no Railway Postgres plugin
- [x] 2.2 After deploy, `GET` the public `web-voice-app` origin `/` and confirm HTTP 200; skip until 2.1 has run; verify with `curl -sf -o /dev/null -w "%{http_code}" "$PUBLIC_WEB_URL/"`
