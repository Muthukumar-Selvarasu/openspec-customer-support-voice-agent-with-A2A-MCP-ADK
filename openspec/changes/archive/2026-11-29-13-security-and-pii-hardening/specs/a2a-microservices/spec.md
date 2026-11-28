# Spec Delta

## ADDED Requirements

### Requirement: Deterministic Judge Blocker Enforcement
`call_judge_agent(query)` (`src/agents/judge_agent.py`) SHALL short-circuit `"BLOCKED"` in Python via `evaluate_prompt(query)` before calling `judge_agent` (with no redundant `judge_tool`), wrap untrusted input in `<user_input>` delimiters, return a closed 1-token enum (`ALLOW` | `BLOCKED` | `OFF_TOPIC`) parsed fail-closed by clients, enforce bounded A2A client timeouts, and delete ephemeral `judge_<uuid>` sessions in `finally:`.

#### Scenario: Flagged prompt returns BLOCKED without relying on LLM compliance
- **WHEN** `call_judge_agent` receives a prompt that `evaluate_prompt` flags as `"BLOCKED"`
- **THEN** it immediately returns `"BLOCKED"` without invoking the Judge LLM

#### Scenario: Off-topic benign prompt returns OFF_TOPIC and empty verdicts fail closed
- **WHEN** `call_judge_agent` evaluates `"write me a poem"` vs. `"My card was blocked on order 5"` vs. an empty LLM response
- **THEN** Judge returns `"OFF_TOPIC"` for the poem, returns `"ALLOW"` for the card-blocked support query without echo collision, and client parsing fails closed on empty or unparseable verdicts

#### Scenario: Ephemeral judge session is cleaned up after evaluation
- **WHEN** `call_judge_agent` invokes the Judge LLM
- **THEN** `judge_agent` performs a single tool-free classification call and deletes the temporary `judge_<uuid>` session from `judge_session_service` once the call completes or errors

## MODIFIED Requirements

### Requirement: Configurable Judge and Masker Bind Addresses
The A2A stack (`src/a2a/`, `src/agents/`) SHALL start Judge on `A2A_JUDGE_HOST`:`A2A_JUDGE_PORT` (default `localhost:10002`) and Masker on `A2A_MASK_HOST`:`A2A_MASK_PORT` (default `localhost:10003`). When `A2A_ONLY=judge|masker`, `src/a2a/run_servers.py` SHALL serve that role on `HOST` (default `0.0.0.0`) and `PORT` (falling back to the role's default port instead of raising `KeyError`).

#### Scenario: Defaults match the cascade profile
- **WHEN** A2A host/port env vars and `A2A_ONLY` are unset
- **THEN** Judge listens on `localhost:10002` and Masker on `localhost:10003`

#### Scenario: Single-role A2A_ONLY mode handles missing PORT safely
- **WHEN** `A2A_ONLY=judge` is set with `PORT` unset
- **THEN** `serve_one("judge")` falls back to `A2A_JUDGE_PORT` (default `10002`) and binds `HOST` (default `0.0.0.0`) without raising `KeyError`

### Requirement: Agent Discovery Cards
Each service (`src/a2a/factories.py`) SHALL serve `GET /.well-known/agent.json` describing its name, endpoint, capabilities (`streaming: true`, `pushNotifications: false`, `stateTransitionHistory: true`), and skills. When bound to wildcard `0.0.0.0`, the card's `url` SHALL advertise a routable hostname (`A2A_PUBLIC_HOST`, `RAILWAY_PRIVATE_DOMAIN`, or `localhost` fallback) rather than `http://0.0.0.0:<port>/`.

#### Scenario: Judge card is discoverable
- **WHEN** a client GETs `/.well-known/agent.json` on the Judge
- **THEN** the card identifies the security-judge agent

#### Scenario: Wildcard bind does not advertise 0.0.0.0 in agent card
- **WHEN** an A2A server binds `0.0.0.0:10002` with `RAILWAY_PRIVATE_DOMAIN=a2a-judge.railway.internal`
- **THEN** `GET /.well-known/agent.json` advertises `http://a2a-judge.railway.internal:10002/` (and falls back to `http://localhost:10002/` when no advertised host env var is set)

### Requirement: JSON-RPC 2.0 Task Methods
`POST /rpc` (`src/a2a/`) SHALL implement `tasks/send`, `tasks/sendSubscribe` (SSE), `tasks/get`, `tasks/cancel`, and in-memory `tasks/pushNotification/{set,get}` (keeping `capabilities.pushNotifications = false`), accept `int | str` JSON-RPC IDs, evict stored tasks FIFO at capacity, set CORS `allow_credentials=False`, and return `-32601` / `-32000` errors.

#### Scenario: tasks/send round-trip
- **WHEN** a client sends `tasks/send` with an integer or string JSON-RPC `id` and a user query
- **THEN** the response is a JSON-RPC 2.0 result echoing that `id` with a task id and agent output

#### Scenario: Unknown method is rejected
- **WHEN** `POST /rpc` receives an unknown method
- **THEN** the error code is `-32601`

#### Scenario: Push notification configuration methods succeed
- **WHEN** a client calls `tasks/pushNotification/set` followed by `tasks/pushNotification/get` for a task id
- **THEN** `POST /rpc` returns valid JSON-RPC 2.0 responses

#### Scenario: In-memory task store stays bounded
- **WHEN** more than `max_tasks` distinct tasks are submitted to `InMemoryTaskManager`
- **THEN** the oldest stored tasks are evicted FIFO so memory usage stays bounded
