# Design

## Context

See `proposal.md` for motivation. The app currently builds four Python services (`web`, `cli`, `a2a-judge`, `a2a-masker`) from one shared `Dockerfile` running `pip install --no-cache-dir -r requirements.txt`, while running Arize Phoenix as a separate container in both `compose.yaml` and `.railway/railway.py`. All service URLs (`DATABASE_URL`, `TOOLBOX_URL`, `A2A_*`, `PHOENIX_URL`, `PHOENIX_PUBLIC_URL`, `HOST`, `PORT`) remain environment-configurable with localhost defaults (`http://localhost:6006` for Phoenix).

## Goals / Non-Goals

**Goals:**
- Align `requirements.txt` with ADK 2 (`google-adk>=2.15.0,<3`), explicitly bound direct `google-genai` imports (`google-genai>=2.34.0,<3`), and close the remaining 5 major-version manifest skews (`toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`) without changing their running majors.
- Eliminate the shadow in-process Phoenix server inside containerized `web`/`cli`/`web-voice-app` processes by removing `arize-phoenix` from `requirements.txt` and `px.launch_app()`, `_port_from_url()`, and unused `urlparse` from `src/core/telemetry.py`, while forwarding an optional `PHOENIX_API_KEY` Bearer header to `OTLPSpanExporter` for authenticated Railway Phoenix v22.
- Pin the standalone Phoenix container image (`version-22.0.1`) consistently in `compose.yaml` and `.railway/railway.py`, and restrict local Compose port publishing to loopback (`127.0.0.1:6006:6006`).
- Guarantee reproducible dependency resolution across `.venv`, Podman, CI, and Railway via a committed `constraints.txt` (verified with `pip install --dry-run`) without tripping `FORBIDDEN_PACKAGES` (`google-auth`, plus newly forbidden `arize-phoenix` and `requests`) in `tests/unit/test_db_and_mcp.py`.
- Close the CI telemetry blind spot with an unmocked import verification test.

**Non-Goals:**
- Upgrading `google-genai` to `3.x` (blocked by `google-adk 2.15.0`'s `<3` constraint).
- Upgrading `opentelemetry-*` (`1.42.1` → `1.45.2`) or `fastapi` (`0.141.1` → `0.165.0`), which were only needed by `arize-phoenix 22.x` and would introduce FastAPI `0.143+` native OTel healthcheck noise.
- Upgrading `@toolbox-sdk/server` (`1.5.0` → `1.18.0`) or migrating `mcp_toolbox/tools.yaml` to flat multi-document YAML.
- Rewriting `src/agents/pipeline.py` or `src/a2a/` to ADK 2 `Workflow` / `google.adk.a2a`.
- Changing container base majors (`python:3.12-slim`, `postgres:16`, `node:22-bookworm-slim`).

## Decisions

1. **Remove `arize-phoenix` from `requirements.txt`, remove `px.launch_app()` / dead helpers, and support optional `PHOENIX_API_KEY` (`src/core/telemetry.py`)**
   - *Rationale:* `src/core/telemetry.py` exports spans over OTLP/HTTP (`OTLPSpanExporter`) and `src/api/web.py` queries `/v1/projects` with stdlib `urllib.request`. Neither uses any Phoenix Python client SDK. Removing `px.launch_app()` (along with dead `_port_from_url()` and unused `urlparse`) stops `web`/`web-voice-app` from starting a redundant embedded Phoenix server on container port `6006`, shrinks the shared image for all 4 Python services, and decouples `fastapi` and `opentelemetry-sdk` from Phoenix server releases. Adding optional `headers={"Authorization": f"Bearer {api_key}"}` when `PHOENIX_API_KEY` is non-empty enables authenticated OTLP export to Railway Phoenix v22 (`PHOENIX_ENABLE_AUTH=true` in Change `15`) while leaving local unauthenticated Compose untouched (`headers=None`). Note `openinference.semconv.trace.SpanAttributes` stays a lightweight constants-only import at module load time (`ATTR`), while heavy OTel SDK/exporter/instrumentor imports remain lazy inside `init_telemetry()`.
   - *Alternative considered:* Guarding `px.launch_app()` to loopback `PHOENIX_URL` hosts and upgrading `arize-phoenix` to `>=22.0.0,<23`. Rejected because it forces bumping `opentelemetry-*` to `1.45.2` (creating a 3-patch overlap `1.45.0..1.45.2` with `google-adk 2.15.0`), forces `fastapi>=0.142.0` (triggering FastAPI native OTel auto-tracing), and keeps a heavy server package in all 4 app containers.

2. **Pin `google-adk>=2.15.0,<3`, add explicit `google-genai>=2.34.0,<3`, and close remaining major skews while keeping OTel at `1.42.1` / `0.63b1`**
   - *Rationale:* `google-adk 2.15.0` supports `opentelemetry-api/sdk<=1.45.2,>=1.39` and `fastapi<1,>=0.133`, so the existing `1.42.1` / `0.63b1` pins and `fastapi 0.141.1` continue to work with zero code churn. Declaring `google-genai>=2.34.0,<3` explicitly documents a direct dependency used in 6 files and prevents accidental `3.x` resolution. Tightening `toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, and `pytest-asyncio>=1.4.0,<2` aligns `requirements.txt` with the majors already running in `.venv` so future lockfile refreshes cannot silently jump major versions.
   - *Alternative considered:* Leaving `google-adk>=1.19.0`, `0.x` floors, and transitive `google-genai`. Rejected because fresh installs silently jump majors and mask real direct imports.

3. **Keep `requirements.txt` direct-only and add a separate universal `constraints.txt`**
   - *Rationale:* `tests/unit/test_db_and_mcp.py` enforces `FORBIDDEN_PACKAGES` (`google-auth`, `google-cloud-dlp`, `google-cloud-secret-manager`, plus newly added `arize-phoenix` and `requests`) against `requirements.txt`, while `google-adk` and `google-genai` pull `google-auth` and `requests` transitively. A separate `constraints.txt` (generated via `uv pip compile --universal --python-version 3.12 requirements.txt -o constraints.txt` and validated with `pip install --dry-run -r requirements.txt -c constraints.txt`) lets `Dockerfile` and `.github/workflows/ci.yml` install deterministically without polluting `requirements.txt`. Update `README.md` line 88 (*"no second pip list"*) and `run.sh` header comment line 5 to accurately reflect `requirements.txt` + `constraints.txt`.
   - *Alternative considered:* Replacing `requirements.txt` with full `pip freeze` output. Rejected because macOS-specific wheels break Linux containers/CI and transitive `google-auth` fails `test_db_and_mcp.py`.

4. **Pin `arizephoenix/phoenix:version-22.0.1` and bind local Compose to `127.0.0.1:6006:6006`**
   - *Rationale:* Docker Hub tags for Arize Phoenix require the `version-` prefix (`version-22.0.1`, not `22.0.1`). Pinning the exact tag in both `compose.yaml` and `.railway/railway.py` prevents floating `:latest` breakage. Binding `"127.0.0.1:6006:6006"` in `compose.yaml` keeps `PHOENIX_ENABLE_AUTH: "false"` accessible on `http://127.0.0.1:6006` without exposing unauthenticated shopper traces on the local LAN. Note that `compose.yaml`'s exact `'    ports:\n      - "5000:5000"\n'` block on `mcp-toolbox` must remain untouched because `run.sh` and `test_db_and_mcp.py` match it literally.
   - *Alternative considered:* Using `:latest` or enabling Phoenix auth locally. Rejected because `:latest` causes drift and `ops-and-deployment/spec.md` requires unauthenticated local Phoenix.

## Risks / Trade-offs

- **[Risk] Host-only runs with `TELEMETRY=true` and no Phoenix container** → Mitigation: OTLP `BatchSpanProcessor` handles unreachable endpoints without crashing app turns; document starting the Phoenix container (`podman compose up -d phoenix`) or setting `TELEMETRY=false` when running on the host in `README.md`.
- **[Risk] Platform-specific packages or pip-incompatible syntax leaking into `constraints.txt`** → Mitigation: Generate `constraints.txt` with `uv pip compile --universal --python-version 3.12 requirements.txt -o constraints.txt`, verify via `pip install --dry-run -r requirements.txt -c constraints.txt`, and verify clean install in both `.venv` and `podman build`.
- **[Risk] Phoenix v22 SQLite migration rollback** → Mitigation: Phoenix 22 applies forward Alembic SQLite migrations; if ever rolling back to an older Phoenix container tag, recreate the local Phoenix container/volume rather than reusing a v22 `/mnt/data` directory.
- **[Risk] `constraints.txt` staleness when dependencies change** → Mitigation: Document regenerating `constraints.txt` in `README.md` alongside `requirements.txt` edits and keep CI installing with `-c constraints.txt`.

## Migration Plan

1. Update `requirements.txt` (`google-adk>=2.15.0,<3`, `google-genai>=2.34.0,<3`, tightened major bounds on `toolbox-core`, `mem0ai`, `openinference-instrumentation-google-genai`, `pytest`, and `pytest-asyncio`, removing `requests` and `arize-phoenix`), generate `constraints.txt` with `uv pip compile --universal`, verify via `pip install --dry-run`, and sync `.venv`.
2. Remove `px.launch_app()`, `import phoenix`, `_port_from_url()`, and unused `urlparse` from `src/core/telemetry.py`, add optional `PHOENIX_API_KEY` Bearer header support on `OTLPSpanExporter`, and update `tests/unit/test_core.py` (including unmocked OTel/OpenInference import and `PHOENIX_API_KEY` tests) and `tests/unit/test_db_and_mcp.py`.
3. Update `Dockerfile`, `.github/workflows/ci.yml`, `compose.yaml`, `.railway/railway.py`, `run.sh` header comment, and `README.md`.
4. Run full `pytest tests/unit tests/integration tests/evals` and verify `podman build .`. Rollback is `git revert` + redeploy (with Phoenix container recreation if downgrading container major).
