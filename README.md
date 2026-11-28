# Customer support voice agent

Local cascade stack: Postgres, MCP Toolbox, one A2A process (Judge and Masker), the web and voice app, and optional Phoenix. Containers run with Podman. Cloud deploy was introduced in archived change `08-railway-deploy` and reconciled in `15-railway-and-docs-reconciliation`. A local run does not need a cloud project.

## Requirements

- Podman, with the `podman compose` plugin (or `podman-compose`)
- Python 3.12 when you run pytest on the host
- `GOOGLE_API_KEY` and `MEM0_API_KEY` for a live text or voice turn

If `podman info` fails, start the machine and retry:

```bash
podman machine start
podman info
```

macOS Control Center listens on port 5000. `compose.yaml` still publishes `5000:5000`. When that port is already taken, `./run.sh` writes `compose.runtime.yaml` to start Toolbox on container port 5000 without a host publish so the web app can reach it as `http://mcp-toolbox:5000`, and `./run.sh down` / `./run.sh ps` honor `compose.runtime.yaml` when present.

`./run.sh` points the compose provider at an empty Docker config under `.run/`. That avoids a host `credsStore` of `desktop` calling `docker-credential-desktop` for public image pulls. The same override works for a direct compose command:

```bash
DOCKER_CONFIG="$PWD/.run/docker-config" podman compose up -d
```

## Configure

```bash
cp .env.example .env
```

Required for live turns:

- `GOOGLE_API_KEY`
- `MEM0_API_KEY`

Optional. Defaults are enough for the host browser and host pytest:

- `DATABASE_URL` defaults to `postgresql://toolbox_user:mysecretpassword@127.0.0.1:5432/toolbox_db`
- `VOICE_STT_LIVE_MODEL` defaults to `gemini-3.1-flash-live-preview` (`VOICE_PRICE_STT_IN=3.00`, `VOICE_PRICE_STT_OUT=4.50` USD per 1M tokens)
- `HOST` defaults to `127.0.0.1`
- `PORT` defaults to `8000`
- `WEB_PORT` is an alias of `PORT` and is used only when `PORT` is unset

Inside compose, the web and CLI containers use the `postgres` service for `DATABASE_URL` and `mcp-toolbox` / `a2a` for tool and judge calls. Host pytest and the browser still use `127.0.0.1`.

Security guardrails run with zero GCP DLP / Model Armor dependencies: Layer 1 local input sanitizer & regex blocker (`src/security/sanitizer.py`, `src/security/blocker.py`), Layer 2 A2A Security & Topic Judge (`:10002`, returning `ALLOW` / `BLOCKED` / `OFF_TOPIC`) paired with `SQL_PROMPT_INSTRUCTION` customer-support domain scope across Web, Voice, and CLI (`src/api/cli.py`), and Layer 3 local-regex A2A Data Masker (`:10003`, 16 PII categories in `src/security/masker.py`).

Do not commit `.env`.

## Run

`./run.sh` writes `.run/tools.yaml` (Postgres host `postgres`, tenant filter `WHERE order_id = $1 AND customer_email = $2`, canonical `action-log` types) and starts the stack:

```bash
./run.sh
```

To skip the optional local Phoenix container:

```bash
PHOENIX=false ./run.sh
# or
./run.sh --no-phoenix
```

The same services come up with Podman Compose after setup:

```bash
./run.sh setup
podman compose up -d
```

Published ports:

| Service | Host URL |
| --- | --- |
| Postgres | `127.0.0.1:5432` |
| MCP Toolbox | `http://127.0.0.1:5000` |
| A2A Judge | `http://localhost:10002` |
| A2A Masker | `http://localhost:10003` |
| Web and voice | `http://127.0.0.1:8000` |
| Phoenix (optional) | `http://127.0.0.1:6006` |

Shopper UI: `http://127.0.0.1:8000/` (static demo login hints; plain-text ` · premium` header indicator; Push-to-Talk mic/Tab voice with sentence-level masked streaming when `MASK=true`). Architecture view: `http://127.0.0.1:8000/architecture` (resolves `"Open Phoenix"` from `PHOENIX_PUBLIC_URL`).

Operator CLI, on the compose network:

```bash
podman compose run --rm cli python -m src.api.cli
```

Stop:

```bash
./run.sh down
```

`mcp_toolbox/seed.sql` is non-destructive and idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, and `pg_roles`-guarded `toolbox_user` grants). To explicitly reset local demo tables back to a clean slate:

```bash
psql "$DATABASE_URL" -c "DROP TABLE IF EXISTS actions_log, customer_orders, users;"
psql "$DATABASE_URL" -f mcp_toolbox/seed.sql
```

Direct Python dependencies live in `requirements.txt` with deterministic versions locked in `constraints.txt` (`pip install -r requirements.txt -c constraints.txt` in the app image, CI, and on the host). When updating `requirements.txt`, regenerate `constraints.txt` with `uv pip compile --universal --python-version 3.12 requirements.txt -o constraints.txt`. For host runs with `TELEMETRY=true`, start the standalone Phoenix container (`podman compose up -d phoenix`) or set `TELEMETRY=false` (the app exports OTLP traces without launching an embedded Phoenix server).

## Tests

```bash
pip install -r requirements.txt -c constraints.txt
pytest tests/unit tests/integration tests/evals
```

Live Gemini and Postgres checks skip when those services or API keys are unset. `pytest.ini` sets `addopts = -p no:phoenix` so host test runs never auto-load a third-party Phoenix pytest plugin.

## Railway

Local `./run.sh` stays the local path. It does not read `RAILWAY_TOKEN` and does not need a cloud project.

Railway is the hosted path, defined by `.railway/railway.py`, `.railway/requirements.txt` (`railway-sdk` isolated outside `requirements.txt`), `Dockerfile`, `Dockerfile.toolbox`, and `scripts/start-toolbox.mjs`. It uses Neon for Postgres, not a Railway Postgres plugin. Create a Neon project, copy the pooled `DATABASE_URL` (`sslmode=require`) into the Railway secrets for `web-voice-app` and `mcp-toolbox` (`scripts/start-toolbox.mjs` preserves `DATABASE_URL` query parameters such as `sslmode=require` in `/tmp/tools.yaml` via `queryParams`), and apply `mcp_toolbox/seed.sql` to the Neon direct URL (safe to re-run without dropping tables or failing on missing `toolbox_user`).

Put `RAILWAY_TOKEN` in `.env` when you want the CLI to deploy without a browser login. `.env.example` has an empty `RAILWAY_TOKEN=` line. The real token stays in `.env` and is never committed. Deploy when that token is set or `railway whoami` already succeeds.

The public app is `web-voice-app` at `https://customer-support-voice-agent.up.railway.app`. `mcp-toolbox`, `a2a-judge`, and `a2a-masker` stay on the private network (`*.railway.internal`), and every Railway service declares an explicit healthcheck (`/` on `mcp-toolbox`, `phoenix`, `web-voice-app`; `/.well-known/agent.json` on `a2a-judge`, `a2a-masker`). On Railway, `phoenix` runs `arizephoenix/phoenix:version-22.0.1` with authentication enabled (`PHOENIX_ENABLE_AUTH=true` and `PHOENIX_SECRET` secret) so customer traces are never publicly unauthenticated, while `web-voice-app` exports OTLP traces over private `PHOENIX_URL` using `PHOENIX_API_KEY` and renders browser-reachable `"Open Phoenix"` / trace links from `PHOENIX_PUBLIC_URL=https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}`. `GOOGLE_API_KEY`, `MEM0_API_KEY`, `PHOENIX_SECRET`, and `PHOENIX_API_KEY` are Railway secrets, not files in git.
