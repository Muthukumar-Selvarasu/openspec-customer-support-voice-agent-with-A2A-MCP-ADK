# Proposal

## Why

An Elephant-Goldfish Model (EGM) multi-lens audit of the project's Python dependencies and container runtimes (validated against the 2026-11-26 drift report and `.venv`) surfaced four concrete dependency and telemetry risks across local Podman (`./run.sh`), CI, and Railway deployments:

1. **Manifest-to-runtime skew and missing direct bounds (`requirements.txt`):**
   - `requirements.txt` declares `google-adk>=1.19.0`, whereas `.venv` and fresh installs already resolve ADK 2 (`2.13.0` / `2.15.0`) with no `<3` upper cap. Five more direct packages have similar major-version skew (`toolbox-core>=0.5.3` running `1.4.0`, `mem0ai>=0.1.118` running `2.2.1`, `openinference-instrumentation-google-genai>=0.1.5` running `1.5.0`, `pytest>=8.3.0` running `9.2.0`, and `pytest-asyncio>=0.24.0` running `1.4.1`) with no upper major caps.
   - Six modules (`src/voice/stt.py`, `src/voice/tts.py`, `src/api/web.py`, `src/api/cli.py`, `src/agents/judge_agent.py`, `tests/unit/test_voice.py`) import `google.genai` directly while relying on it transitively; PyPI now serves `google-genai 3.6.1`, which conflicts with `google-adk 2.15.0`'s `google-genai<3,>=2.34` constraint.
   - `requests>=2.31.0` is listed in `requirements.txt` despite never being imported anywhere in `src/`, `tests/`, `scripts/`, or `.railway/`.
2. **Embedded shadow Phoenix server inside containerized app processes & authenticated OTLP export (`src/core/telemetry.py`, `requirements.txt`):**
   - Both `compose.yaml` and `.railway/railway.py` already run a dedicated standalone Phoenix container, while `src/core/telemetry.py` exports spans over standard OTLP/HTTP (`opentelemetry-exporter-otlp-proto-http` + `openinference-instrumentation-google-genai`) and `src/api/web.py` reads project IDs via stdlib `urllib.request`.
   - Keeping the full `arize-phoenix` server package in `requirements.txt` solely for `px.launch_app()` bloats all four shared Python containers (`web`, `cli`, `a2a-judge`, `a2a-masker`), ties app `fastapi` and `opentelemetry-sdk` versions to Phoenix server releases, and causes `web` / `web-voice-app` to boot an unused shadow Phoenix server inside their own container on port `6006` because the standalone Phoenix lives in a separate container namespace.
   - Additionally, `init_telemetry()` does not forward an optional `PHOENIX_API_KEY` Bearer header to `OTLPSpanExporter`, which is needed once Railway Phoenix enables `PHOENIX_ENABLE_AUTH=true` in Change `15`.
3. **Unpinned Phoenix container image & LAN exposure (`compose.yaml`, `.railway/railway.py`):**
   - Both `compose.yaml` and `.railway/railway.py` pull `arizephoenix/phoenix:latest`, exposing local and Railway deployments to silent major-version breaking changes (such as Phoenix 21+'s auth-by-default shift and v22 SQLite migrations). Local `compose.yaml` also publishes `6006:6006` on all interfaces rather than loopback (`127.0.0.1:6006:6006`).
4. **Non-reproducible dependency resolution across environments (`Dockerfile`, `.github/workflows/ci.yml`):**
   - `.venv`, local Podman builds, GitHub Actions CI, and Railway's three Python services each run bare `pip install -r requirements.txt` independently. Without a compiled constraints lockfile (`constraints.txt`), `git revert` does not restore the prior wheel set, and CI currently mocks out all telemetry packages (`test_core.py`) without verifying real OTel/OpenInference imports.

This aligns with the observability, zero-bloat, and local/Railway parity goals in `docs/ENGAGEMENT.md` and `docs/01-discovery.md`–`docs/03-poc.md`.

## What Changes

- **Upgrade & tighten direct Python dependencies (`requirements.txt`):**
  - Bump `google-adk` to `google-adk>=2.15.0,<3` (and upgrade `.venv` to `2.15.0`).
  - Explicitly declare `google-genai>=2.34.0,<3`.
  - Close the remaining 5 major-version manifest-to-runtime skews without changing running majors (`toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`).
  - Remove unused `requests>=2.31.0` and the `arize-phoenix` server package from `requirements.txt` (adding both to `FORBIDDEN_PACKAGES` in `tests/unit/test_db_and_mcp.py`) while retaining lightweight OTLP/OpenInference packages (`openinference-instrumentation-google-genai`, `openinference-semantic-conventions`, and the pinned `opentelemetry-*` `1.42.1` / `0.63b1` suite that already satisfies `google-adk 2.15.0`).
- **Remove embedded `px.launch_app()` & support optional `PHOENIX_API_KEY` (`src/core/telemetry.py`):**
  - Export spans directly to `${PHOENIX_URL}/v1/traces` via `OTLPSpanExporter` + `GoogleGenAIInstrumentor` without importing `phoenix` or launching an in-process Phoenix server, and remove the now-dead `_port_from_url()` helper and unused `urlparse` import.
  - Pass `headers={"Authorization": f"Bearer {api_key}"}` to `OTLPSpanExporter` when `PHOENIX_API_KEY` is set (no-op locally when unset) so authenticated Railway Phoenix v22 ingestion works seamlessly.
  - Add an unmocked telemetry import test and `PHOENIX_API_KEY` header tests in `tests/unit/test_core.py`.
- **Pin the standalone Phoenix container image (`compose.yaml`, `.railway/railway.py`):**
  - Pin `docker.io/arizephoenix/phoenix:version-22.0.1` in `compose.yaml` (keeping `PHOENIX_ENABLE_AUTH: "false"` and binding `"127.0.0.1:6006:6006"`) and `arizephoenix/phoenix:version-22.0.1` in `.railway/railway.py`.
- **Add reproducible dependency locking (`constraints.txt`, `Dockerfile`, `.github/workflows/ci.yml`, `README.md`, `run.sh`):**
  - Commit a Linux/universal Python 3.12 `constraints.txt` lockfile alongside `requirements.txt` (verified via `pip install --dry-run -r requirements.txt -c constraints.txt`, keeping `requirements.txt` as the clean direct dependency list so `FORBIDDEN_PACKAGES` checks in `tests/unit/test_db_and_mcp.py` remain green).
  - Install with `pip install --no-cache-dir -r requirements.txt -c constraints.txt` in `Dockerfile` and `pip install -r requirements.txt -c constraints.txt` in `.github/workflows/ci.yml`, and align `README.md` (including line 88) and `run.sh` comment line 5.

## Capabilities

### New Capabilities
<!-- None; all updates refine existing dependency, telemetry, local ops, and Railway deployment requirements. -->

### Modified Capabilities
- `database-and-mcp-tools`: Require `google-adk>=2.15.0,<3`, explicit `google-genai>=2.34.0,<3`, tightened major bounds on `toolbox-core`, `mem0ai`, `openinference-instrumentation-google-genai`, `pytest`, and `pytest-asyncio`, OTel/OpenInference exporters without `arize-phoenix` or unused `requests` in `requirements.txt`, and a compiled `constraints.txt` lockfile keeping transitive dependencies (such as `google-auth`) out of `requirements.txt`.
- `auth-memory-telemetry`: Require `init_telemetry()` when `TELEMETRY=true` to export OTLP/HTTP spans to `PHOENIX_URL` (passing `Authorization: Bearer <PHOENIX_API_KEY>` when set) and instrument Google GenAI without importing `phoenix` or calling `px.launch_app()`.
- `ops-and-deployment`: Require `Dockerfile` and `.github/workflows/ci.yml` to install `requirements.txt` with `-c constraints.txt` (OTel/OpenInference exporters, no embedded `arize-phoenix`), pin local Compose Phoenix to `docker.io/arizephoenix/phoenix:version-22.0.1` (never `:latest`), and publish local Phoenix on `127.0.0.1:6006:6006`.
- `railway-deploy`: Require `.railway/railway.py` to pin the optional `phoenix` service to `arizephoenix/phoenix:version-22.0.1` matching `compose.yaml` (never `:latest`).

## Impact

- **Dependencies & Lockfile:** `requirements.txt`, `constraints.txt` (new).
- **Application Code:** `src/core/telemetry.py`.
- **Containers, CI & Railway:** `Dockerfile`, `compose.yaml`, `.railway/railway.py`, `.github/workflows/ci.yml`, `README.md`, `run.sh` (header comment).
- **Tests:** `tests/unit/test_db_and_mcp.py`, `tests/unit/test_core.py`.
- **Specs:** `openspec/specs/database-and-mcp-tools/spec.md`, `openspec/specs/auth-memory-telemetry/spec.md`, `openspec/specs/ops-and-deployment/spec.md`, `openspec/specs/railway-deploy/spec.md`.
- **Out of Scope (explicitly skipped per EGM audit):** Upgrading `google-genai` to `3.x` (blocked by ADK 2), upgrading `opentelemetry-*` to `1.45.2` or `fastapi` to `0.165.0`, upgrading `@toolbox-sdk/server` beyond `1.5.0`, migrating `src/agents/pipeline.py` or `src/a2a/` to ADK 2 `Workflow`/`google.adk.a2a`, and bumping base container OS/runtime majors (`python:3.12-slim`, `postgres:16`, `node:22-bookworm-slim`).
