# Spec Delta

## MODIFIED Requirements

### Requirement: Container Image and CI
`Dockerfile` SHALL install Python 3.12+ dependencies using `pip install --no-cache-dir -r requirements.txt -c constraints.txt` (including OTel/OpenInference exporters, without the `arize-phoenix` server package) and default to `python -m src.api.web`. Local builds SHALL use `podman build`. `.github/workflows/ci.yml` SHALL install dependencies using `pip install -r requirements.txt -c constraints.txt` and run `pytest` for `tests/unit`, `tests/integration`, and `tests/evals`.

#### Scenario: CI workflow exists
- **WHEN** `.github/workflows/ci.yml` is inspected
- **THEN** it installs from `requirements.txt` with `-c constraints.txt` and invokes `pytest` covering `tests/unit`, `tests/integration`, and `tests/evals`

#### Scenario: Dockerfile installs with constraints.txt
- **WHEN** `Dockerfile` is inspected
- **THEN** it copies `constraints.txt`, runs `pip install --no-cache-dir -r requirements.txt -c constraints.txt`, and defaults to `python -m src.api.web`

### Requirement: Local Phoenix opens without a login
The local Phoenix service in `compose.yaml` SHALL pin `docker.io/arizephoenix/phoenix:version-22.0.1` (MUST NOT use `:latest`), SHALL set `PHOENIX_ENABLE_AUTH` to false, and SHALL bind its host port to loopback (`127.0.0.1:6006:6006`). `run.sh` SHALL keep those settings when it writes `compose.runtime.yaml`. The local Phoenix page SHALL load without a username or password on `http://127.0.0.1:6006`.

#### Scenario: Compose disables Phoenix auth
- **WHEN** `compose.yaml` is inspected
- **THEN** the `phoenix` service uses `docker.io/arizephoenix/phoenix:version-22.0.1`, publishes `127.0.0.1:6006:6006`, and sets `PHOENIX_ENABLE_AUTH` to `"false"`

#### Scenario: Generated runtime file keeps auth off
- **WHEN** `run.sh` writes `compose.runtime.yaml` because host port 5000 is busy
- **THEN** the `phoenix` service in that file still uses `docker.io/arizephoenix/phoenix:version-22.0.1`, publishes `127.0.0.1:6006:6006`, and sets `PHOENIX_ENABLE_AUTH` to `"false"`
