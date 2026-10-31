# Spec Delta: `ops-and-deployment`

## Purpose

Defines local Podman orchestration, containerization, CI, and operator docs for the multi-service cascade stack.

## ADDED Requirements

### Requirement: Podman Compose Local Orchestration
`compose.yaml` and `run.sh` SHALL start Postgres, MCP Toolbox, **one** A2A process (Judge+Masker threads via `python -m src.a2a.run_servers`), optional Phoenix, and the web/voice app as Podman containers. Commands SHALL be `podman compose` (or `podman-compose`), not `docker`. Web CMD is `python -m src.api.web`. Toolbox SHALL run `npx @toolbox-sdk/server@1.5.0` bound to `0.0.0.0`. It MUST NOT keep a second pip install list besides `requirements.txt`.

#### Scenario: Script parses
- **WHEN** `bash -n run.sh` runs
- **THEN** it exits `0`

#### Scenario: Compose uses Podman, not docker
- **WHEN** `run.sh` and `compose.yaml` are inspected
- **THEN** they contain `podman compose` or `podman-compose` and do not call `docker`

#### Scenario: Entrypoints use src modules
- **WHEN** `compose.yaml` is inspected
- **THEN** web uses `python -m src.api.web` and there is a single `a2a` service using `python -m src.a2a.run_servers`

### Requirement: Generated Config Matches Local Group 1
`run.sh` generated `tools.yaml` MUST keep Group 1 tenant-scoped `get-order-status` SQL and MUST set the Postgres source host to the compose service name `postgres` (not `127.0.0.1`). Do not emit unused PoC leftovers (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`). Host-published `DATABASE_URL` remains `127.0.0.1:5432`.

#### Scenario: Heredoc matches local Group 1 SQL on the compose network
- **WHEN** `run.sh` config templates are inspected
- **THEN** `get-order-status` includes `customer_email`, the Postgres host is `postgres`, and unused PoC leftover keys are absent

### Requirement: Container Image and CI
`Dockerfile` SHALL install Python 3.12+ dependencies from `requirements.txt` (including Phoenix/OTel) and default to `python -m src.api.web`. Local builds SHALL use `podman build`. `.github/workflows/ci.yml` SHALL run `pytest` for `tests/unit`, `tests/integration`, and `tests/evals`.

#### Scenario: CI workflow exists
- **WHEN** `.github/workflows/ci.yml` is loaded
- **THEN** it contains a `pytest` step covering unit, integration, and evals

### Requirement: README Matches the Repo
`README.md` SHALL document `podman compose` / `./run.sh` and required `GOOGLE_API_KEY` / `MEM0_API_KEY` / `DATABASE_URL` for local runs. Cloud deploy steps belong in change `08-railway-deploy`.

#### Scenario: README is local-first
- **WHEN** `README.md` is read
- **THEN** setup steps list `GOOGLE_API_KEY`, `podman compose` / `./run.sh`, and do not require an extra cloud project

### Requirement: Local Full Cascade
After `podman compose up` / `./run.sh` is up, `GET /` and `GET /architecture` SHALL return 200. When `GOOGLE_API_KEY` and `MEM0_API_KEY` are set, one text chat turn and one voice WebSocket turn (STT → pipeline → TTS, 1500 ms settle) SHALL complete.

#### Scenario: Local web stack is reachable
- **WHEN** `podman compose up` / `./run.sh` has started
- **THEN** `GET http://127.0.0.1:8000/` returns 200 and the `postgres` container is running

#### Scenario: Local voice turn speaks a reply
- **WHEN** a logged-in client sends PCM over `/voice/ws` and stays quiet for 1500 ms
- **THEN** the server transcribes, runs the text pipeline, and streams TTS PCM back
