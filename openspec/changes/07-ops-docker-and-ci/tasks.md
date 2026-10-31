# Tasks: `07-ops-docker-and-ci`

Orchestrate local services with Podman. `requirements.txt` from Group 1 is the single dependency list. Do not write `docker` CLI commands.

## 1. Local orchestration and docs

- [ ] 1.1 Extend Group 1 `compose.yaml` and write `run.sh` so `podman compose up` starts `postgres`, `mcp-toolbox`, **one** `a2a` service (`python -m src.a2a.run_servers` — Judge+Masker threads), `web` (`python -m src.api.web`), and optional `phoenix`; Toolbox is `npx -y @toolbox-sdk/server@1.5.0` (Node image) with `--address 0.0.0.0`; A2A/web bind `0.0.0.0`; publish `5432`, `5000`, `10002`, `10003`, `8000` to the host; generated `tools.yaml` MUST keep Group 1 SQL (`WHERE order_id = $1 AND customer_email = $2`) and MUST set the Postgres host to compose service `postgres` (not `127.0.0.1`); CLI is `podman compose run --rm cli python -m src.api.cli`; install Python deps only with `pip install -r requirements.txt` inside the app image; verify with `bash -n run.sh`, `podman compose config`, and `pytest tests/unit/test_db_and_mcp.py -k run_sh`
- [ ] 1.2 Write `README.md` for `podman compose` / `./run.sh`, required `GOOGLE_API_KEY` / `MEM0_API_KEY`, optional `DATABASE_URL` / `HOST` / `PORT` / `WEB_PORT`; document `podman machine start` if `podman info` fails; cloud deploy notes belong in change `08`; verify with `pytest tests/unit/test_db_and_mcp.py -k readme`

## 2. Image and CI

- [ ] 2.1 Add `Dockerfile` (Python 3.12, `pip install -r requirements.txt`, default `CMD python -m src.api.web`) and `.github/workflows/ci.yml` that runs `pytest tests/unit tests/integration tests/evals`; verify `podman build -t cs-voice-app .` succeeds and the workflow file contains those three pytest paths (live Gemini/Postgres tests may skip via markers)

## 3. Local full cascade

- [ ] 3.1 Boot the local stack with `./run.sh` / `podman compose up -d`; verify `GET http://127.0.0.1:8000/` and `GET http://127.0.0.1:8000/architecture` return 200, Judge `GET http://localhost:10002/.well-known/agent.json` is 200, Masker `:10003` is 200, and `podman compose ps` shows `postgres` healthy
- [ ] 3.2 Sign in as a seeded shopper and complete one text turn (`POST /api/chat` or the UI): sanitizer → Judge → agent → Masker → reply; skip unless `GOOGLE_API_KEY` and `MEM0_API_KEY` are set; verify with `pytest tests/integration/test_local_cascade.py -k text` or a recorded UI pass
- [ ] 3.3 Complete one voice turn on `/voice/ws` the same way the product works today: browser PCM in, STT, 1500 ms settle, pipeline, TTS PCM out; optional barge-in `interrupt` → `turn_end` `reason: "interrupted"`; skip unless keys and a mic/browser are available; verify with `pytest tests/integration/test_local_cascade.py -k voice` or a recorded UI pass
