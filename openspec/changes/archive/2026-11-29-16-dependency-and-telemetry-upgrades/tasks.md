# Tasks

## 1. Python Dependencies & Constraints Lockfile

- [x] 1.1 Update `requirements.txt` to set `google-adk>=2.15.0,<3`, add explicit `google-genai>=2.34.0,<3`, tighten major-skewed floors (`toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`), remove unused `requests>=2.31.0`, and remove the `arize-phoenix` server package (keeping `openinference-semantic-conventions` and the pinned `opentelemetry-*` `1.42.1` / `0.63b1` exporters); update `LOCAL_PACKAGES` and add `"arize-phoenix"` and `"requests"` to `FORBIDDEN_PACKAGES` in `tests/unit/test_db_and_mcp.py`, asserting the tightened bounds in `requirements.txt`, then verify via `.venv/bin/pytest tests/unit/test_db_and_mcp.py -k requirements`.
- [x] 1.2 Generate a Python 3.12 universal/Linux `constraints.txt` lockfile from `requirements.txt` via `uv pip compile --universal --python-version 3.12 requirements.txt -o constraints.txt`, verify pip compatibility via `.venv/bin/pip install --dry-run -r requirements.txt -c constraints.txt`, install into `.venv` via `.venv/bin/pip install --upgrade -r requirements.txt -c constraints.txt` (and uninstall `arize-phoenix` from `.venv` so host tests match the container), and verify `google-adk==2.15.0` is installed and `requirements.txt` contains no `google-auth`, `requests`, or `arize-phoenix` via `.venv/bin/python -c "import importlib.metadata as m; print(m.version('google-adk'), m.version('google-genai'))"` and `.venv/bin/pytest tests/unit/test_db_and_mcp.py -k requirements`.

## 2. Container-Only Phoenix Telemetry, Optional `PHOENIX_API_KEY` & Unmocked OTel Test

- [x] 2.1 Remove `import phoenix as px`, `PHOENIX_PORT`/`PHOENIX_GRPC_PORT` mutations, `px.launch_app()`, dead `_port_from_url()`, and unused `urlparse` from `src/core/telemetry.py` so `init_telemetry()` configures only `OTLPSpanExporter(endpoint=f"{export_url}/v1/traces", headers=...)` (sending `{"Authorization": f"Bearer {api_key}"}` when `PHOENIX_API_KEY` is set, or `headers=None` when unset) + `GoogleGenAIInstrumentor` (and respects `PHOENIX_OPEN_BROWSER`); update `test_telemetry_skips_browser_open_when_disabled` in `tests/unit/test_core.py` to assert `phoenix` is not imported or launched, add tests covering unset vs. set `PHOENIX_API_KEY`, and add an unmocked telemetry import test in `tests/unit/test_core.py` verifying real `TracerProvider`, `BatchSpanProcessor`, `OTLPSpanExporter`, `GoogleGenAIInstrumentor`, and `SpanAttributes` import cleanly; verify via `.venv/bin/pytest tests/unit/test_core.py`.

## 3. Pin Phoenix Container Tag, Wire Lockfile in Image/CI & Update Docs

- [x] 3.1 Pin `docker.io/arizephoenix/phoenix:version-22.0.1` and bind `"127.0.0.1:6006:6006"` (keeping `PHOENIX_ENABLE_AUTH: "false"` and preserving the literal `ports:\n      - "5000:5000"` block on `mcp-toolbox`) in `compose.yaml`, pin `image("arizephoenix/phoenix:version-22.0.1")` in `.railway/railway.py`, and add unit tests in `tests/unit/test_db_and_mcp.py` verifying neither file uses `:latest`, both tags match `version-22.0.1`, and `compose.yaml` binds `127.0.0.1:6006:6006`; verify via `.venv/bin/pytest tests/unit/test_db_and_mcp.py`.
- [x] 3.2 Update `Dockerfile` (`COPY constraints.txt .` and `RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt`), update `.github/workflows/ci.yml` (`pip install -r requirements.txt -c constraints.txt`), update `run.sh` header comment line 5 to reflect `-r requirements.txt -c constraints.txt`, update `README.md` (including line 88 *"no second pip list"*) to document `pip install -r requirements.txt -c constraints.txt` and running the standalone Phoenix container for host `TELEMETRY=true` runs, and add assertions in `tests/unit/test_db_and_mcp.py` covering `constraints.txt` in `Dockerfile` and `.github/workflows/ci.yml`; verify via `.venv/bin/pytest tests/unit/test_db_and_mcp.py`.

## 4. Full Integration & Container Verification

- [x] 4.1 Run `.venv/bin/pytest tests/unit tests/integration tests/evals` and `podman build -t cs-voice-app-check .` (when Podman is running) plus `openspec validate "16-dependency-and-telemetry-upgrades"` and confirm zero failures.

## Workflow follow-up

- Archive `16-dependency-and-telemetry-upgrades` after verification to sync delta specs into `openspec/specs/`.
- Proceed to `13-security-and-pii-hardening` → `14-voice-and-session-fixes` → `15-railway-and-docs-reconciliation`, then run a final `openspec validate --specs` and confirm local `./run.sh` and Railway Phoenix/OTLP trace ingestion end-to-end.
