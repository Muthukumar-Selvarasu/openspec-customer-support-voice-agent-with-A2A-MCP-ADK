# Tasks: `04-a2a-microservices`

Implement A2A services under `src/a2a/` and `src/agents/` with `src.*` imports. Do not require ports `10002`/`10003` to be free; use FastAPI `TestClient` / `httpx.AsyncClient`. Stub Judge/Masker LLM calls in RPC tests.

## 1. A2A protocol package

- [x] 1.1 Implement `src/a2a/` (`types.py`, `utils.py`, `task_manager.py`, `server.py`, `factories.py`, `client.py`, `run_servers.py`) as JSON-RPC 2.0 Judge/Masker servers; bind from `A2A_JUDGE_HOST`/`A2A_JUDGE_PORT` and `A2A_MASK_HOST`/`A2A_MASK_PORT` (defaults `localhost:10002` / `localhost:10003`); add bind-env assertions in `tests/integration/test_a2a.py`; verify with `pytest tests/integration/test_a2a.py -k bind`

## 2. Security agents and RPC

- [x] 2.1 Implement `src/agents/judge_agent.py`, `src/agents/mask_agent.py`, and `src/agents/pipeline.py`; `call_mask_agent` MUST call `src.security.masker.mask_sensitive_data(text)` (local Group 3 masker, no extra cloud SDK); verify with `pytest tests/integration/test_a2a.py -k mask`
- [x] 2.2 Expand `tests/integration/test_a2a.py` to mount `A2AServer.app` in-process, stub `call_judge_agent` / `call_mask_agent`, and cover discovery cards plus `tasks/send`, `tasks/sendSubscribe`, `tasks/get`, `tasks/cancel`, unknown method `-32601`, and task error `-32000`; skip any live Gemini case unless `GOOGLE_API_KEY` is set; verify with `pytest tests/integration/test_a2a.py`
