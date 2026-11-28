# ops-and-deployment Specification

## Purpose

Defines local Podman orchestration, containerization, CI, and operator docs for the multi-service cascade stack.

## Requirements

### Requirement: Podman Compose Local Orchestration
`compose.yaml` and `run.sh` SHALL run Postgres, MCP Toolbox (`npx @toolbox-sdk/server@1.5.0` on `0.0.0.0`), one A2A process (`python -m src.a2a.run_servers`), optional Phoenix (skippable via `PHOENIX=false` or `--no-phoenix`), and web (`python -m src.api.web`) with `podman compose` (never `docker`), forwarding `VOICE_STT_LIVE_MODEL`/`VOICE_PRICE_STT_*` to `web`, honoring `compose.runtime.yaml` in `down`/`ps`, and keeping one app `requirements.txt`.

#### Scenario: Script parses
- **WHEN** `bash -n run.sh` runs
- **THEN** it exits `0`

#### Scenario: Compose uses Podman, not docker
- **WHEN** `run.sh` and `compose.yaml` are inspected
- **THEN** they contain `podman compose` or `podman-compose` and do not call `docker`

#### Scenario: Entrypoints use src modules
- **WHEN** `compose.yaml` and `run.sh` are inspected
- **THEN** web uses `python -m src.api.web`, forwards `VOICE_STT_LIVE_MODEL`/`VOICE_PRICE_STT_IN`/`VOICE_PRICE_STT_OUT`, there is a single `a2a` service using `python -m src.a2a.run_servers`, `run.sh` allows skipping Phoenix via `PHOENIX=false` or `--no-phoenix`, and `run.sh down`/`ps` respect `compose.runtime.yaml`

### Requirement: Generated Config Matches Local Group 1
`run.sh` generated `.run/tools.yaml` MUST keep tenant-scoped `get-order-status` SQL, canonical `action-log` `action_type` names (`UPDATE_ORDER_STATUS`, `RETURN_ITEM`, `UPDATE_DELIVERY_ADDRESS`, `UPDATE_PROFILE_DETAILS`), and Postgres host `postgres` (not `127.0.0.1`), omitting unused GCP keys while keeping host `DATABASE_URL` at `127.0.0.1:5432`.

#### Scenario: Heredoc matches local Group 1 SQL on the compose network
- **WHEN** `run.sh` config templates are inspected
- **THEN** `get-order-status` includes `customer_email`, `action-log` lists the canonical `action_type` names, the Postgres host is `postgres`, and unused PoC leftover keys are absent

### Requirement: Container Image and CI
`Dockerfile` SHALL install Python 3.12+ dependencies via `pip install --no-cache-dir -r requirements.txt -c constraints.txt` (OTel/OpenInference exporters, no `arize-phoenix`) and default to `python -m src.api.web`. Local builds SHALL use `podman build`. Railway files (`Dockerfile.toolbox`, `scripts/start-toolbox.mjs`, `.railway/`) SHALL stay isolated from local Podman. `.github/workflows/ci.yml` SHALL install with `-c constraints.txt` and run `pytest` on unit, integration, and evals.

#### Scenario: CI workflow exists
- **WHEN** `.github/workflows/ci.yml` is loaded
- **THEN** it installs from `requirements.txt` with `-c constraints.txt` and contains a `pytest` step covering unit, integration, and evals

#### Scenario: Dockerfile installs with constraints.txt
- **WHEN** `Dockerfile` is inspected
- **THEN** it copies `constraints.txt`, runs `pip install --no-cache-dir -r requirements.txt -c constraints.txt`, and defaults to `python -m src.api.web`

#### Scenario: Railway container files stay isolated from local Podman run
- **WHEN** `Dockerfile.toolbox`, `scripts/start-toolbox.mjs`, and `.railway/railway.py` are present in the repository
- **THEN** `./run.sh` and `compose.yaml` continue to run locally with Podman without requiring Railway files or `RAILWAY_TOKEN`

### Requirement: README Matches the Repo
`README.md` SHALL document `podman compose` / `./run.sh` (including optional `PHOENIX=false` and `pip install -r requirements.txt -c constraints.txt`), required `GOOGLE_API_KEY` / `MEM0_API_KEY` / `DATABASE_URL` for local runs, idempotent `mcp_toolbox/seed.sql`, and the Railway packaging files (`.railway/railway.py`, `.railway/requirements.txt`, `Dockerfile.toolbox`, `scripts/start-toolbox.mjs`) and authenticated Railway Phoenix configuration aligned with archived `08-railway-deploy`.

#### Scenario: README is local-first
- **WHEN** `README.md` is read
- **THEN** setup steps list `GOOGLE_API_KEY`, `podman compose` / `./run.sh`, do not require an extra cloud project, and accurately describe idempotent Neon seeding, `-c constraints.txt`, and Railway services

### Requirement: Local Full Cascade
After `podman compose up` / `./run.sh` is up, `GET /` and `GET /architecture` SHALL return 200. When `GOOGLE_API_KEY` and `MEM0_API_KEY` are set, one text chat turn and one voice WebSocket turn (STT → pipeline → TTS, committing immediately on Push-to-Talk release `0 ms`, after `400 ms` in Quick mode, or after `1500 ms` settle in Explain non-PTT mode) SHALL complete.

#### Scenario: Local web stack is reachable
- **WHEN** `podman compose up` / `./run.sh` has started
- **THEN** `GET http://127.0.0.1:8000/` returns 200 and the `postgres` container is running

#### Scenario: Local voice turn speaks a reply
- **WHEN** a logged-in client sends PCM over `/voice/ws` and either releases Push-to-Talk (`commit: true`) or stays quiet for the active mode settle window (`400 ms` Quick / `1500 ms` Explain)
- **THEN** the server transcribes, runs the text pipeline, and streams TTS PCM back

### Requirement: Local Phoenix opens without a login
The local Phoenix service in `compose.yaml` SHALL pin `docker.io/arizephoenix/phoenix:version-22.0.1` (MUST NOT use `:latest`), SHALL set `PHOENIX_ENABLE_AUTH` to false, and SHALL bind its host port to loopback (`127.0.0.1:6006:6006`). `run.sh` SHALL keep those settings when it writes `compose.runtime.yaml`. The local Phoenix page SHALL load without a username or password on `http://127.0.0.1:6006`.

#### Scenario: Compose disables Phoenix auth
- **WHEN** `compose.yaml` is inspected
- **THEN** the `phoenix` service uses `docker.io/arizephoenix/phoenix:version-22.0.1`, publishes `127.0.0.1:6006:6006`, and sets `PHOENIX_ENABLE_AUTH` to `"false"`

#### Scenario: Generated runtime file keeps auth off
- **WHEN** `run.sh` writes `compose.runtime.yaml` because host port 5000 is busy
- **THEN** the `phoenix` service in that file still uses `docker.io/arizephoenix/phoenix:version-22.0.1`, publishes `127.0.0.1:6006:6006`, and sets `PHOENIX_ENABLE_AUTH` to `"false"`
