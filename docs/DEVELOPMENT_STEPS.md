# Project Development Steps

This document outlines the end-to-end steps followed to develop the **Customer Support Voice Agent (Cascade Voice + A2A + MCP + ADK)** project using the **Forward Deployed Engineering (FDE) Lifecycle** combined with **Spec-Driven OpenSpec Engineering**.

---

## Phase 1: Repository & Workflow Setup

1. **Step 1 — Initialize Repository & Project Structure**
   - Created the project repository and configured `.gitignore` to exclude local virtual environments, runtime artifacts, and secret `.env` files.
   - Established the 9-Stage FDE Lifecycle + OpenSpec methodology and the target directory layout (`docs/` for FDE governance stages, `openspec/` for living specifications and change slices, `src/` for application packages, and `tests/` for unit, integration, and adversarial evaluations).

2. **Step 2 — Initialize OpenSpec**
   - Initialized OpenSpec (`openspec init`) using the `spec-driven` schema in `openspec/config.yaml`.
   - Installed stock OpenSpec workflows (`/opsx-explore`, `/opsx-propose`, `/opsx-apply`, `/opsx-sync`, `/opsx-update`, `/opsx-archive`) to manage specification-driven engineering from Stage 4 onward.

3. **Step 3 — Add FDE Lifecycle Slash Commands & Pre-Code Gate**
   - **Why these commands are needed:** Stock OpenSpec starts at Stage 4 (`/opsx-propose`), which assumes the engineering team already knows what to build. In a real client engagement, jumping straight into specifications or code without structured discovery, falsifiable metrics, and prototype validation risks building the wrong architecture or missing critical security/tenancy flaws.
   - **What was added:** Created four custom slash commands under `.cursor/commands/`—and gated `/opsx-propose` on their completion—so the AI assistant guides pre-code engineering one stage at a time with human sign-off between stages:
     - `/opsx-fde-stage-0` (`opsx-fde-stage-0.md` → writes `docs/ENGAGEMENT.md`): Structures the **Client Engagement Brief** from raw customer notes or stakeholder interviews (problem statement, personas, scope boundaries, database assets, and security mandates) without inventing product features.
     - `/opsx-fde-stage-1` (`opsx-fde-stage-1.md` → writes `docs/01-discovery.md`): Runs **Discovery & Scoping** by auditing the customer brief against the actual baseline repository, data schemas, workflows, and security/tenancy posture, concluding with an evidence-backed Go/No-Go decision.
     - `/opsx-fde-stage-2` (`opsx-fde-stage-2.md` → writes `docs/02-problem-metrics.md`): Produces the **Problem & Metrics Pack**, translating discovery findings into a scoped problem brief, measurable KPI targets (security, privacy, latency, cost, accuracy), and an evaluation rubric.
     - `/opsx-fde-stage-3` (`opsx-fde-stage-3.md` → writes `docs/03-poc.md`): Produces the **Proof of Concept (PoC) Pack**, defining testable hypotheses, sandbox topology, scripted validation scenarios, empirical defect logs, and the final Go/No-Go gate required before `/opsx-propose` is unlocked.

---

## Phase 2: FDE Discovery, Metrics & Proof of Concept (Stages 0–3)

4. **Step 4 — FDE Stage 0: Client Engagement Brief**
   - Ran `/opsx-fde-stage-0` to generate `docs/ENGAGEMENT.md`.
   - Documented the business objective (evaluating a Guardrailed Cascade Voice architecture against a sibling Speech-to-Speech prototype), stakeholder personas, in-scope customer workflows (authentication, order lookups, `Read → Confirm → Audit` order modifications, Mem0 cross-session recall, natural voice with barge-in), PostgreSQL schema (`users`, `customer_orders`, `actions_log`), and non-negotiable security and PII redaction rules.

5. **Step 5 — FDE Stage 1: Discovery & Scoping**
   - Ran `/opsx-fde-stage-1` to produce `docs/01-discovery.md`.
   - Audited the baseline prototype, mapped the multi-service architecture (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and optional `phoenix`), and identified baseline technical gaps:
     - Unnecessary GCP project lock-in (`GOOGLE_CLOUD_PROJECT` / Cloud DLP no-op when unset).
     - Hardcoded `127.0.0.1` / `localhost` URLs blocking multi-container cloud deployment.
     - Stateful WebSocket requirements (`WS /voice/ws`) favoring Railway over serverless platforms.
     - Pipeline behavior drift between Web (`web.py`) and Terminal CLI (`agent_cli.py`).

6. **Step 6 — FDE Stage 2: Problem & Metrics**
   - Ran `/opsx-fde-stage-2` to author `docs/02-problem-metrics.md`.
   - Defined measurable success criteria and evaluation rubrics across 5 pillars:
     - **Security & Guardrails:** `100%` (`61/61`) malicious attack block rate, `100%` (`39/39`) legitimate query pass rate, `0%` cross-tenant order leakage, and `0` calls to `update-order-status`.
     - **Privacy & DLP:** `100%` PII redaction recall across 16 PII categories and `0` unmasked audio frames sent to TTS when `MASK=true`.
     - **Voice Latency:** Streaming TTFA `< 2.0s` (p50), buffered masked TTFA `< 6.0s` (p50), and `< 200ms` barge-in cancellation.
     - **Cost & Observability:** `100%` per-turn `timing` and USD `cost` events plus OpenTelemetry trace export to Arize Phoenix.
     - **Functional Accuracy:** `100%` compliance with the `Read → Confirm → Audit` workflow and cross-session Mem0 recall.

7. **Step 7 — FDE Stage 3: Proof of Concept Validation**
   - Ran `/opsx-fde-stage-3` to produce `docs/03-poc.md`.
   - Validated 5 core technical hypotheses across 6 scripted customer and adversarial scenarios.
   - Logged 6 specific defects discovered during PoC testing to fix in Stage 4/5:
     1. Discarded `_preprocess_query()` return value in `blocker.py`.
     2. Over-aggressive character stripping and unanchored regexes in `sanitizer.py` / `blocker.py`.
     3. Unmasked passthrough in `masker.py` when `GOOGLE_CLOUD_PROJECT` is unset.
     4. UTF-8 byte-offset string slicing corruption in `masker.py`.
     5. Cross-tenant `tool_result` IDOR leak in the `"What happened"` UI panel when querying another customer's order ID.
     6. Channel parity issues (CLI dropping sanitized string, lowercasing responses, and `parameters_json` vs. `parameters` prompt mismatch).
   - Recorded a formal **GO** decision to proceed to Stage 4 OpenSpec Specification.

---

## Phase 3: OpenSpec Specification & Review Gate (Stage 4)

8. **Step 8 — FDE Stage 4: Propose OpenSpec Changes 01–08**
   - Ran `/opsx-propose` one slice at a time to decompose the platform into 8 vertically ordered, independently testable changes under `openspec/changes/`:
     1. `01-db-and-mcp-foundation` (`database-and-mcp-tools`)
     2. `02-core-auth-memory-telemetry` (`auth-memory-telemetry`)
     3. `03-security-guardrails-and-evals` (`security-guardrails`)
     4. `04-a2a-microservices` (`a2a-microservices`)
     5. `05-cascade-voice-engine` (`cascade-voice-engine`)
     6. `06-web-and-cli-channels` (`web-and-cli-channels`)
     7. `07-ops-docker-and-ci` (`ops-and-deployment`)
     8. `08-railway-deploy` (`railway-deploy`)
   - Generated 4 planning artifacts per change: `proposal.md` (PRD), `specs/<capability>/spec.md` (`SHALL`/`MUST` requirements + `WHEN`/`THEN` scenarios), `design.md` (TDD), and `tasks.md` (granular build checklist with verification commands).

9. **Step 9 — Specification Review & Sign-Off Gate**
   - Reviewed all 37 tasks across changes `01`–`08` one-by-one against `docs/ENGAGEMENT.md` and `docs/03-poc.md` to verify requirement mapping and file boundaries prior to writing application code.
   - Approved and locked the specification artifacts as the baseline for Stage 5 engineering.

---

## Phase 4: Iterative Engineering, Verification & Deployment (Stages 5–7)

Each OpenSpec change was implemented using a consistent iterative development loop:
1. **Apply (`/opsx-apply <change>`):** Implement tasks in `tasks.md` step-by-step under `src/` and `tests/`.
2. **Check:** Review implementation against the change's `spec.md` and `design.md`.
3. **Verify & Test:** Run the task-level `pytest` verification command until green before checking off the task.
4. **Validate:** Run the full test suite for the slice to confirm end-to-end compliance.
5. **Archive (`/opsx-archive`):** Merge delta specs into the living master specifications (`openspec/specs/`) and move the completed change to `openspec/changes/archive/`.

### Core Engineering Slices

10. **Step 10 — Build Slice `01-db-and-mcp-foundation`**
    - Created `mcp_toolbox/seed.sql` (schema + 10 shoppers + 17 orders) and `mcp_toolbox/tools.yaml` (with tenant-scoped SQL `WHERE order_id = $1 AND customer_email = $2`).
    - Added `requirements.txt`, `.env.example`, `pytest.ini`, local Podman PostgreSQL service in `compose.yaml`, and unit tests in `tests/unit/test_db_and_mcp.py`.

11. **Step 11 — Build Slice `02-core-auth-memory-telemetry`**
    - Implemented `src/core/greet.py` (env-driven PostgreSQL connection resolution, user authentication, and Premium/Standard tier greeting).
    - Implemented `src/core/memory.py` (lazy-initialized Mem0 `search_memory` and `save_memory` scoped by `user_id`).
    - Implemented `src/core/prompts.py` (`SQL_PROMPT_INSTRUCTION` enforcing `Read → Confirm → Audit` via `action-log` with `parameters` and authenticated `customer_email`).
    - Implemented `src/core/telemetry.py` (`_NoopTracer` when disabled; Arize Phoenix OTel exporter when enabled) and unit tests in `tests/unit/test_core.py`.

12. **Step 12 — Build Slice `03-security-guardrails-and-evals`**
    - Implemented `src/security/sanitizer.py` (`MAX_INPUT_LENGTH = 300` and character whitelist without GCP Model Armor lock-in).
    - Implemented `src/security/blocker.py` (evaluating both raw input and URL-decoded/leetspeak-normalized input with word-boundary regexes).
    - Implemented `src/security/masker.py` (self-contained, character-safe regex redaction across all 16 PII categories without requiring `GOOGLE_CLOUD_PROJECT`).
    - Added unit tests in `tests/unit/test_security.py` and the 100-scenario adversarial benchmark (`61` malicious + `39` legitimate) in `tests/evals/test_security_eval.py` achieving `100/100`.

13. **Step 13 — Build Slice `04-a2a-microservices`**
    - Built the Agent-to-Agent (A2A) JSON-RPC 2.0 protocol package under `src/a2a/` (`types.py`, `utils.py`, `task_manager.py`, `server.py`, `factories.py`, `client.py`, `run_servers.py`).
    - Built the isolated Security Judge (`:10002`) and Data Masker (`:10003`) microservices under `src/agents/` (`judge_agent.py`, `mask_agent.py`, `pipeline.py`) with env-configurable host/port bindings and integration tests in `tests/integration/test_a2a.py`.

14. **Step 14 — Build Slice `05-cascade-voice-engine`**
    - Implemented the voice modules under `src/voice/` (`stt.py`, `tts.py`, `cost.py`, `router.py`, `ui.js`).
    - Enforced the streaming vs. masking safety interlock (`STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`), multi-burst speech accumulation (`1500 ms` settle), barge-in cancellation, and per-stage token/USD cost accounting, tested via `tests/unit/test_voice.py`.

15. **Step 15 — Build Slice `06-web-and-cli-channels`**
    - Added the shopper Web Chat + Voice UI (`src/static/index.html`) and live SVG Architecture dashboard (`src/static/architecture.html`, `src/static/architecture.svg`).
    - Built the FastAPI server (`src/api/web.py`) with `_enforce_tenant_tool_callback` (overwriting tool identity args with the logged-in session and blocking `update-order-status`), NDJSON glass-box step streaming (`POST /api/chat/stream`), and `/voice/ws` mounting.
    - Built the operator Terminal CLI (`src/api/cli.py`) with unified sanitization, topical guardrail, and preserved response casing, verified in `tests/integration/test_api_and_tenant.py`.

16. **Step 16 — Build Slice `07-ops-docker-and-ci`**
    - Extended `compose.yaml` and created `run.sh` to orchestrate the full local stack with Podman (`postgres`, `mcp-toolbox`, `a2a`, `web`, and optional `phoenix`).
    - Added `Dockerfile`, `README.md`, GitHub Actions CI (`.github/workflows/ci.yml`), and full local stack integration tests (`tests/integration/test_local_cascade.py`).

### Iterative UX & Voice Latency Enhancements

17. **Step 17 — Build Slice `09-demo-response-mode`**
    - Added a live header toggle between **Explain** mode (full cascade with A2A Judge, A2A Masker, and open `"What happened"` inspector) and **Quick** mode (skipping Judge/Masker for low-latency streaming demos).

18. **Step 18 — Build Slice `10-session-survives-refresh`**
    - Added `GET /api/session` and browser session restoration so reloading a signed-in tab preserves the active shopper session and ADK conversation history while still flushing Mem0 on explicit sign-out or actual tab close.

19. **Step 19 — Build Slice `11-push-to-talk-fast-response`**
    - Upgraded voice input to stream 16 kHz PCM live to Gemini Live (`gemini-3.1-flash-live-preview`) for real-time interim transcription.
    - Added walkie-talkie Push-to-Talk (`#mic` button and `Tab` hotkey) with a `1.0 s` post-release tail window (`PTT_RELEASE_TAIL_MS = 1000`) to prevent last-word clipping and `0 ms` settle on release.
    - Added smart interrupt handling, clause-level TTS streaming (`[:;\n]`), header toggles (`#toggleJudge`, `#toggleMask`), and concurrent A2A Security Judge execution.

### Production Cloud Deployment

20. **Step 20 — Build Slice `08-railway-deploy`: Multi-Service Cloud Deployment**
    - Configured multi-service Railway deployment (`.railway/`, `Dockerfile.toolbox`, and single-role A2A entrypoints) while keeping `./run.sh` for local Podman execution.
    - Provisioned **Neon PostgreSQL** (`DATABASE_URL` with `sslmode=require`) and applied `mcp_toolbox/seed.sql` once.
    - Deployed `web-voice-app` (public HTTPS domain) alongside `mcp-toolbox`, `a2a-judge`, `a2a-masker`, and `phoenix` communicating over Railway private networking (`*.railway.internal`), and verified live health and UI behavior.
