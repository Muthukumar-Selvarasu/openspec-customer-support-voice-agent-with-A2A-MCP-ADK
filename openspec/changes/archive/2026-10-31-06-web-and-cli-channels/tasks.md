# Tasks: `06-web-and-cli-channels`

Implement the shopper app under `src/api/` and `src/static/` with `src.core`, `src.security`, `src.a2a`, and `src.voice` imports. Mock Toolbox/A2A/Gemini. Skip live paths unless `DATABASE_URL` and Toolbox are available.

## 1. Static UI

- [x] 1.1 Add `src/static/index.html`, `src/static/architecture.html`, `src/static/architecture.svg`, repo-root `diagram.png`, and `src/api/__init__.py`; verify the files exist with `pytest tests/integration/test_api_and_tenant.py -k static_files`

## 2. FastAPI app

- [x] 2.1 Implement `src/api/web.py`: resolve `_REPO_ROOT = Path(__file__).resolve().parents[2]` and `_STATIC = Path(__file__).resolve().parents[1] / "static"`; load `mcp_toolbox/tools.yaml` from `_REPO_ROOT`; lazy-init `ToolboxSyncClient` so `from src.api.web import app` does not need Toolbox on import; read `TOOLBOX_URL`, `A2A_JUDGE_HOST`, `A2A_JUDGE_PORT`, `A2A_MASK_HOST`, `A2A_MASK_PORT`, `PHOENIX_URL`, `PHOENIX_PUBLIC_URL`, `HOST`, and `PORT` from env with localhost defaults `127.0.0.1:5000`, `:10002`/`:10003`, `:6006`, `:8000`; treat `WEB_PORT` as an alias of `PORT`; verify `python -c "from src.api.web import app"` and `pytest tests/integration/test_api_and_tenant.py -k import_app`
- [x] 2.2 Add `_enforce_tenant_tool_callback` on the support `LlmAgent`: overwrite tool args `user_id`, `email`, `customer_email`, and `user_email` with the logged-in session identity; block `update-order-status` by returning an error payload without calling the tool; unit-test the callback with a fake tool context (no Gemini); verify with `pytest tests/integration/test_api_and_tenant.py -k tenant`
- [x] 2.3 Mount `src.voice.router.make_voice_router` at `/voice/ws` using the shared runners and `text_pipeline`; serve `GET /`, `GET /architecture`, and `GET /architecture.svg` as 200 from `src/static`; verify with `pytest tests/integration/test_api_and_tenant.py -k pages`
- [x] 2.4 Implement `POST /api/login`, `/api/logout` (single Mem0 flush), `/api/chat`, and `/api/chat/stream` with mocked Toolbox/A2A; verify with `pytest tests/integration/test_api_and_tenant.py -k chat`

## 3. Operator CLI

- [x] 3.1 Implement `src/api/cli.py` using the same Toolbox/A2A env vars as web; `validate_input` MUST return the sanitized string and that string MUST be what `runner.run()` receives; do not lowercase masked output; verify with `pytest tests/integration/test_api_and_tenant.py`
