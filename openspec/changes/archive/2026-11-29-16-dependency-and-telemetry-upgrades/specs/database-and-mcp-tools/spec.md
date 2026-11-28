# Spec Delta

## MODIFIED Requirements

### Requirement: Local PoC Dependencies, Env Template, and Pytest Layout
`requirements.txt` SHALL list direct PoC packages with upper major bounds aligned to the running stack (`google-adk>=2.15.0,<3`, `google-genai>=2.34.0,<3`, `toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`, FastAPI/Uvicorn, Postgres, OTel exporters) and MUST NOT include `requests`, `arize-phoenix`, or unused GCP leftovers. `.env.example` SHALL document localhost defaults without GCP vars; `pytest.ini` SHALL set `pythonpath = .`.

#### Scenario: Requirements and env templates match local PoC
- **WHEN** `requirements.txt`, `.env.example`, and `pytest.ini` are inspected
- **THEN** `requirements.txt` declares `google-adk>=2.15.0,<3`, `google-genai>=2.34.0,<3`, `toolbox-core>=1.4.0,<2`, `mem0ai>=2.2.0,<3`, `openinference-instrumentation-google-genai>=1.5.0,<2`, `pytest>=9.0.0,<10`, `pytest-asyncio>=1.4.0,<2`, `openinference-semantic-conventions`, `opentelemetry-sdk==1.42.1`, `opentelemetry-api==1.42.1`, `opentelemetry-exporter-otlp-proto-http==1.42.1`, and `opentelemetry-semantic-conventions==0.63b1`, omits `arize-phoenix`, `requests`, `google-cloud-dlp`, `google-cloud-secret-manager`, and `google-auth`, `.env.example` documents localhost defaults with `WEB_PORT` as an alias of `PORT` (without `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, or `MODEL_ARMOR_TEMPLATE_ID`), and `pytest.ini` sets `pythonpath = .`

## ADDED Requirements

### Requirement: Reproducible Dependency Constraints Lockfile
The repository SHALL commit a Linux/universal Python 3.12 `constraints.txt` file alongside `requirements.txt` so `pip install -r requirements.txt -c constraints.txt` resolves deterministic package versions across host `.venv`, container builds, CI, and Railway without adding transitive dependencies (such as `google-auth`) into `requirements.txt`.

#### Scenario: Constraints file locks transitive versions without polluting requirements.txt
- **WHEN** `constraints.txt` and `requirements.txt` are inspected
- **THEN** `constraints.txt` exists with exact `==` version pins compatible with Python 3.12 on Linux and macOS, passes `pip install --dry-run -r requirements.txt -c constraints.txt`, and `requirements.txt` stays free of `google-auth`, `requests`, and `arize-phoenix`
