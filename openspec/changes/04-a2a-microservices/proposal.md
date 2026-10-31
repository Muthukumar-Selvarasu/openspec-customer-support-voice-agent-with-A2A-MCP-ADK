# Proposal: A2A JSON-RPC Microservices (`04-a2a-microservices`)

## Why

Sanitizer, blocker, and masker from Group 3 must run as separate Judge (`:10002`) and Masker (`:10003`) processes over A2A JSON-RPC 2.0 so the cascade stays a multi-service topology locally, not one combined process.

This slice is independently testable with FastAPI `TestClient` / `httpx` against in-process A2A servers. It does not start web chat, voice, or Postgres.

## What Changes

- Add `src/a2a/` protocol package: types, utils, task manager, server, factories, client, `run_servers.py`.
- Add `src/agents/` Judge and Masker agents plus the sequential `security_pipeline`.
- Bind Judge/Masker hosts and ports from `A2A_JUDGE_HOST`/`A2A_JUDGE_PORT` and `A2A_MASK_HOST`/`A2A_MASK_PORT` (defaults `localhost:10002` / `localhost:10003`).
- Call `mask_sensitive_data(text)` from Group 3 (local regex masker).
- Cover discovery + RPC in-process with stubbed LLM calls.

## Capabilities

### New Capabilities
- `a2a-microservices`: A2A JSON-RPC 2.0 Judge and Masker services, discovery cards, and task methods.

### Modified Capabilities

## Impact

- `src/a2a/{__init__.py, types.py, utils.py, task_manager.py, server.py, factories.py, client.py, run_servers.py}`
- `src/agents/{__init__.py, judge_agent.py, mask_agent.py, pipeline.py}`
- `tests/integration/test_a2a.py`

## Channels

- **In scope:** A2A JSON-RPC `GET /.well-known/agent.json` and `POST /rpc` on Judge `:10002` and Masker `:10003`
- **Out of scope:** Web Chat, Voice WebSocket, Terminal CLI

## Out of Scope

- Voice STT/TTS (Group 5)
- FastAPI shopper app (Group 6)
- Podman compose / `run.sh` process supervision (Group 7)
