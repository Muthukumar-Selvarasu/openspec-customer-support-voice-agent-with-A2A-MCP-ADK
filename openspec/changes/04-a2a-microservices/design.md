# Design: A2A JSON-RPC Microservices

## Context

See `proposal.md`. Depends on `03-security-guardrails-and-evals`. Implement the A2A protocol under `src/a2a/` and Judge/Masker agents under `src/agents/`. Judge and Masker remain separate processes.

## Goals / Non-Goals

**Goals:**
- In-process testable A2A protocol (discovery + RPC).
- Env-driven bind addresses with localhost defaults.

**Non-Goals:**
- Combining Judge and Masker into the web process.
- Podman compose / `run.sh` (Group 7 starts these processes).

## Decisions

### Decision 1: Keep two A2A servers
`run_servers.py` starts Judge and Masker in daemon threads in **one process**. Group 7 runs that one process as a single `a2a` compose service. Change `08` can run the same factories as two Railway services.

### Decision 2: Env overrides for host/port
Replace hardcoded `localhost`/`10002`/`10003` in `main()` with `A2A_JUDGE_HOST`, `A2A_JUDGE_PORT`, `A2A_MASK_HOST`, `A2A_MASK_PORT`. Defaults stay `localhost` for host pytest. Compose sets bind host `0.0.0.0` so other containers can connect.

### Decision 3: Mask agent calls Group 3 directly
`call_mask_agent` calls `src.security.masker.mask_sensitive_data(text)` only. It MUST NOT call an extra cloud SDK.

### Decision 4: Integration tests use TestClient
Do not require ports 10002/10003 to be free. Mount `A2AServer.app` in FastAPI `TestClient` / `httpx.AsyncClient`. Stub `call_judge_agent` / `call_mask_agent` in RPC tests.

### Decision 5: Package names are `src.a2a` and `src.agents`
Imports are `from src.a2a...` and `from src.agents...`.

## Risks / Trade-offs

- **[Risk] Judge LLM calls make tests slow/flaky** → Mitigation: stub `call_judge_agent` / `call_mask_agent` in RPC tests; keep one optional live test skipped without `GOOGLE_API_KEY`.
