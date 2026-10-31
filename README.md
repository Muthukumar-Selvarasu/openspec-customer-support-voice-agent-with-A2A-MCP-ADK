# Customer support voice agent

Local cascade stack: Postgres, MCP Toolbox, one A2A process (Judge and Masker), the web and voice app, and optional Phoenix. Containers run with Podman. Cloud deploy is change `08-railway-deploy`. A local run does not need a cloud project.

## Requirements

- Podman, with the `podman compose` plugin (or `podman-compose`)
- Python 3.12 when you run pytest on the host
- `GOOGLE_API_KEY` and `MEM0_API_KEY` for a live text or voice turn

If `podman info` fails, start the machine and retry:

```bash
podman machine start
podman info
```

macOS Control Center listens on port 5000. `compose.yaml` still publishes `5000:5000`. When that port is already taken, `./run.sh` starts Toolbox on container port 5000 without a host publish so the web app can reach it as `http://mcp-toolbox:5000`.

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
- `HOST` defaults to `127.0.0.1`
- `PORT` defaults to `8000`
- `WEB_PORT` is an alias of `PORT` and is used only when `PORT` is unset

Inside compose, the web and CLI containers use the `postgres` service for `DATABASE_URL` and `mcp-toolbox` / `a2a` for tool and judge calls. Host pytest and the browser still use `127.0.0.1`.

Do not commit `.env`.

## Run

`./run.sh` writes `.run/tools.yaml` (Postgres host `postgres`, tenant filter `WHERE order_id = $1 AND customer_email = $2`) and starts the stack:

```bash
./run.sh
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

Shopper UI: `http://127.0.0.1:8000/`. Architecture view: `http://127.0.0.1:8000/architecture`.

Operator CLI, on the compose network:

```bash
podman compose run --rm cli python -m src.api.cli
```

Stop:

```bash
./run.sh down
```

Python dependencies install from `requirements.txt` only (`pip install -r requirements.txt` in the app image and on the host). There is no second pip list.

## Tests

```bash
pip install -r requirements.txt
pytest tests/unit tests/integration tests/evals
```

Live Gemini and Postgres checks skip when those services or API keys are unset.
