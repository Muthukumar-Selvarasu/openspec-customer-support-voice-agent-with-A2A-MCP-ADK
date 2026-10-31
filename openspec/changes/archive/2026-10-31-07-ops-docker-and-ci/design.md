# Design: Ops, Podman & CI

## Context

See `proposal.md`. Depends on Groups 1–6. Implement `compose.yaml`, `run.sh`, `README.md`, `Dockerfile`, and `.github/workflows/ci.yml` against `src.*` modules. Group 1 `requirements.txt` is the only dependency list. Local engine is Podman.

## Goals / Non-Goals

**Goals:**
- One local command (`./run.sh` / `podman compose up`) to boot the 5–6 services as containers.
- CI that reruns every group's pytest.
- An OCI image whose default CMD is the web/voice app (`podman build` locally; Railway reuses it in 08).

**Non-Goals:**
- Cloud project provisioning or `railway up` (change `08-railway-deploy`).
- Neon (change `08`).
- Shipping secrets in git.
- Docker Desktop / `docker` CLI.

## Decisions

### Decision 1: Podman compose is the local orchestrator
Extend Group 1 `compose.yaml`. Services: `postgres`, `mcp-toolbox`, **one** `a2a` (`python -m src.a2a.run_servers`), `web`, optional `phoenix`. Do not run two A2A containers that each call `run_servers` (that process already binds both ports). `run.sh` wraps `podman compose` (fallback `podman-compose`). Do not call `docker`. CLI is `podman compose run --rm cli python -m src.api.cli`.

### Decision 1b: Compose network vs host ports
Inside the compose network, Toolbox `tools.yaml` Postgres host is `postgres`. Toolbox listens `0.0.0.0:5000`; A2A/web bind `0.0.0.0`. Publish `5432`/`5000`/`10002`/`10003`/`8000` so the host browser and host pytest still use `127.0.0.1`. Host `DATABASE_URL` stays `127.0.0.1:5432`.

### Decision 1c: Toolbox is the same npx server, in a Node image
`mcp-toolbox` runs `npx -y @toolbox-sdk/server@1.5.0 --config /config/tools.yaml --enable-api --address 0.0.0.0 --port 5000`. Do not invent a different Toolbox binary.

### Decision 2: gen_config_files stays in lockstep with Group 1
`tools.yaml` SQL in Group 1 is the committed contract. `run.sh` heredoc must match the tenant-scoped `get-order-status` statement so `./run.sh setup` cannot overwrite the fix. The generated **host** field is `postgres` (compose DNS), not `127.0.0.1`. Add a pytest grep that the generated statement includes `customer_email` and the compose host is `postgres`.

### Decision 3: Single OCI image, built with Podman
One Python 3.12 image from `requirements.txt`. Default CMD is `python -m src.api.web`. Verify with `podman build`. Change `08` decides how that image is split across Railway services.

### Decision 4: CI runs the full suite
Unit tests always run. Integration/evals may skip live Gemini/Postgres via pytest markers, but the workflow still invokes `tests/unit`, `tests/integration`, and `tests/evals`.

### Decision 5: No second pip list
Group 1 put Phoenix/OTel/`pyyaml` in `requirements.txt`. Install Python deps only with `pip install -r requirements.txt` so the image, CI, and local setup cannot drift.

### Decision 6: README matches Podman launch
README launch commands are `podman compose` / `./run.sh`. Document `podman machine start` on macOS. Document `WEB_PORT` as an alias of `PORT`. Cloud deploy steps belong in change `08`.

### Decision 7: Local full cascade before cloud
After compose is up, prove the live product locally: HTTP pages, one text chat turn, and one STT→TTS voice turn (1500 ms settle, optional barge-in). Skip live Gemini steps when `GOOGLE_API_KEY` is unset.

## Risks / Trade-offs

- **[Risk] run.sh setup overwrites tools.yaml** → Mitigation: keep heredoc in lockstep with Group 1 SQL; add a CI grep that the generated statement includes `customer_email`.
- **[Risk] `podman compose` plugin missing** → Mitigation: fall back to `podman-compose` against the same `compose.yaml`.
