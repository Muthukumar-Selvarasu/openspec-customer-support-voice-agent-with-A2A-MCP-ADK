# Stage 1: Discovery & Scoping (`01-discovery.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 1 — Discovery & Scoping |
| **Input Reference** | [`docs/ENGAGEMENT.md`](ENGAGEMENT.md) |
| **Target Cloud Runtime** | 5 Independent Railway Services (`mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, optional `phoenix`) + Managed Neon PostgreSQL (`DATABASE_URL` with `sslmode=require`) & Local Podman (`./run.sh`) |
| **Database Engine** | PostgreSQL 16 (Local Podman `127.0.0.1:5432` / Managed Neon PostgreSQL via `DATABASE_URL`) |
| **External State Stores** | Mem0 Cloud API (Long-Term Memory), Standalone Arize Phoenix (`phoenix:version-22.0.1`, OpenTelemetry Trace Store) |
| **Security Posture** | Defense-in-Depth (Layer 1 Local Sanitizer & Blocker → Layer 2 A2A Security & Topic Judge → Prompt Scope & Tool Tenant Callback → Layer 3 Local-Regex A2A Data Masker) |
| **Channels Covered** | Web Chat (`POST /api/chat/stream`), Cascade Voice (`WS /voice/ws`), Operator Terminal CLI (`src/api/cli.py`) |
| **Sign-Off Owners** | Forward Deployed Engineering (FDE) Lead & Client Operations / Platform Lead |

---

## 1. Executive Summary

### 1.1 Discovery Overview

During Stage 1 Discovery, the Forward Deployed Engineering (FDE) team audited the Customer's e-commerce order operations, prototype baseline, database schemas, security mandates, and cloud deployment targets.

The Customer's primary objective is to automate high-frequency post-purchase support requests—**order status lookups, order history reviews, cancellations, item returns, and delivery address/profile updates**—across three interaction channels (**Real-Time Browser Voice**, **Web Chat**, and **Operator Terminal CLI** in `src/api/cli.py`) without exposing their PostgreSQL orders database to prompt/SQL injection or leaking Personally Identifiable Information (PII) over synthesized voice.

### 1.2 Stakeholder Interview Findings

| Stakeholder Group | Current Pain Points ("As-Is") | Discovery Requirements & Constraints ("To-Be") |
| :--- | :--- | :--- |
| **Customer Operations & Support Leadership** | • Support agents spend >65% of time on repetitive "Where is my order?" (WISMO) and address/cancellation requests.<br>• Customers must repeat communication preferences (e.g., *"email only"*) on every call.<br>• High-value **Premium** shoppers receive the same generic greeting as Standard shoppers. | • Recognize **Premium** vs. **Standard** tier status immediately upon login (` · premium` in Web header; item-count greeting in CLI).<br>• Persist and recall customer preferences across sessions via long-term memory (**Mem0**).<br>• Never allow an AI agent to directly mutate `customer_orders`; all confirmed changes must be logged to an immutable `actions_log` table for fulfillment review. |
| **InfoSec & Privacy Compliance Team** | • Native Speech-to-Speech (`S2S`) models stream audio directly from weights—once the model begins speaking a street address, credit card, or phone number, PII cannot be retracted.<br>• Giving LLMs database tools creates risks of SQL injection, obfuscated payloads (leetspeak, hex, SQL comments), off-topic misuse, and cross-tenant order enumeration. | • Enforce a **Pre-Execution Security & Scope Gate** (Layer 1 local sanitizer/blocker + Layer 2 isolated **A2A Security & Topic Judge** returning `ALLOW` / `BLOCKED` / `OFF_TOPIC`) before the support LLM or database tools are invoked.<br>• Enforce a **Post-Execution Privacy Gate** (Layer 3 isolated **A2A Data Masker** running deterministic local regexes across 16 PII categories) before TTS synthesis.<br>• Eliminate external GCP project lock-in (`GOOGLE_CLOUD_PROJECT`, Cloud DLP, Model Armor, Secret Manager) so PII redaction works out-of-the-box anywhere with zero cloud SDKs. |
| **AI / Cloud Platform Engineering Team** | • Multi-agent voice pipelines are typically "black boxes"—engineers cannot see which step added latency, what exact SQL ran, or how much each voice turn cost in tokens/USD.<br>• Need a clean **multi-service cloud deployment on Railway** backed by **Neon Postgres** while keeping local Podman `./run.sh` parity. | • Provide an inline **"What happened" step inspector** and a live **`/architecture` SVG topology** (synchronized via `BroadcastChannel`) with explicit Guardrail L1–L3 badges and env-driven `"Open Phoenix"` links.<br>• Deploy as independently scalable Railway microservices (`mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, authenticated `phoenix`) wired via `.railway/railway.py`, `.railway/requirements.txt`, `Dockerfile.toolbox`, and `scripts/start-toolbox.mjs`. |

### 1.3 Core Architectural Discovery: Why the Cascade Voice Pattern

A central finding of Discovery is the trade-off between **Native Speech-to-Speech (S2S)** and **Cascade Voice (`STT → Text Pipeline → TTS`)**:

```text
Speech In (16 kHz PCM, Push-to-Talk or VAD)
  → Live Speech-to-Text (gemini-3.1-flash-live-preview)
  → [ Layer 1 Local Sanitizer & Blocker → Layer 2 A2A Security & Topic Judge (:10002) → ADK Support Agent (+ MCP Toolbox :5000 & Mem0) → Layer 3 Local-Regex A2A Data Masker (:10003) ]
  → Text-to-Speech (gemini-3.8-flash-tts, 24 kHz PCM)
  → Speech Out
```

#### Key Advantages Confirmed in Discovery
1. **Deterministic Pre-Agent Gating:** Because user audio is transcribed to text *before* reaching the reasoning agent, Layer 1 local sanitization/blocking and Layer 2 A2A Security & Topic Judge can intercept malicious (`BLOCKED`) and out-of-scope (`OFF_TOPIC`) inputs with zero risk of triggering tool calls.
2. **Guaranteed PII Redaction Before Audio Synthesis:** When `MASK=true`, voice replies use **sentence-level masked streaming**—every completed sentence is scrubbed by the local-regex A2A Data Masker *before* `gemini-3.8-flash-tts` synthesizes an audio frame.
3. **True Microservice Isolation:** Each stage (`mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`) is a distinct network service that can be deployed, health-checked, and monitored independently on Railway while backed by Neon Postgres.
4. **Independent Stage Accounting:** Latency (`ms` / `s`) and token cost (`USD`) are measured independently for `stt`, `judge`, `agent`, `mask`, and `tts`.

### 1.4 Codebase Baseline Audit (Initial Prototype Findings & Resolution Status)

An audit of the initial prototype surfaced five foundational gaps—all subsequently resolved across OpenSpec changes `01`–`16`:

| Area | Prototype Finding (Historical) | Implemented Resolution in `src/` & Deployment |
| :--- | :--- | :--- |
| **1. Unnecessary GCP Dependencies** | Prototype referenced `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`, `google-cloud-dlp`, and unused `google-cloud-secret-manager`; `masker.py` was a no-op without a GCP project. | Removed all GCP SDKs and env vars. `src/security/sanitizer.py` and `src/security/masker.py` run 100% self-contained local regexes across all 16 PII types (no GCP project required). |
| **2. Hardcoded `127.0.0.1` / `localhost` URLs** | Prototype hardcoded Postgres credentials and `localhost` A2A/Toolbox/Phoenix hosts. | `src/core/greet.py`, `src/api/web.py`, `src/api/cli.py`, and `scripts/start-toolbox.mjs` read `DATABASE_URL` (preserving Neon `?sslmode=require`), `TOOLBOX_URL`, `A2A_*`, `PHOENIX_URL`, `PHOENIX_PUBLIC_URL`, `HOST`, and `PORT` (`WEB_PORT` alias). |
| **3. Persistent WebSockets & In-Memory State (Why Railway over Vercel)** | `/voice/ws` (`src/voice/router.py`) holds a persistent full-duplex WebSocket, and `src/api/web.py` holds in-memory ADK `_runners` and `_transcripts`. | Deployed as persistent Railway services (`.railway/railway.py`, `.railway/requirements.txt`) with Neon Postgres (`DATABASE_URL`), preserving stateful WebSockets and A2A streams natively. |
| **4. Channel Pipeline Drift (`web.py` vs. CLI)** | Prototype CLI (`agent_cli.py`) discarded sanitized input, lowercased replies, and had a separate CLI-only Layer 2b guardrail; `blocker.py` discarded `_preprocess_query()`. | Unified in `src/api/web.py` and `src/api/cli.py`: both pass sanitized `clean` text, preserve masked casing, enforce Layer 1 raw+normalized blocking, Layer 2 A2A Judge (`ALLOW`/`BLOCKED`/`OFF_TOPIC`) + `SQL_PROMPT_INSTRUCTION` scope, and `_enforce_tenant_tool_callback`. |
| **5. Embedded Phoenix Pop-Up & Unauthenticated Links** | Prototype launched Phoenix in-process (`px.launch_app()`) and hardcoded `http://localhost:6006`. | Dropped `arize-phoenix` from app image (standalone `phoenix:version-22.0.1` container); separated `PHOENIX_URL` (private OTLP export) from `PHOENIX_PUBLIC_URL` (injected into `/architecture` and trace links); enabled `PHOENIX_ENABLE_AUTH="true"` + `PHOENIX_SECRET` + `PHOENIX_API_KEY` on Railway. |

### 1.5 Technical & Operational Risks Identified During Discovery

| Risk ID | Risk Description | Severity | Implemented Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **RISK-01** | **Streaming TTS vs. PII Masking Conflict:** Raw token streaming cannot scrub PII once audio frames have been emitted to the browser. | **High** | When `MASK=true` (default), voice uses **sentence-level masked streaming** (masking each completed sentence via A2A `:10003` before TTS) and text disables raw streaming (`STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`). |
| **RISK-02** | **Natural Pause Fragmentation & End-of-Utterance Clipping in Voice:** Callers pause mid-thought or release Push-to-Talk right after their last syllable. | **Medium** | Push-to-Talk (`#mic` / `Tab`) streams live audio to `gemini-3.1-flash-live-preview` with a `1000 ms` release tail (`PTT_RELEASE_TAIL_MS`) and `0 ms` commit settle; non-PTT modes accumulate bursts with `400 ms` (Quick) / `1500 ms` (Explain) settle and echo-resistant barge-in (`BARGE_RMS = 0.12`). |
| **RISK-03** | **Legacy Toolset Over-Permission (`update-order-status`):** The MCP catalog keeps `update-order-status` for compliance testing. | **High** | Enforced by both `SQL_PROMPT_INSTRUCTION` and deterministic `_enforce_tenant_tool_callback` in `src/api/web.py` (hard-blocking `update-order-status`, forcing session identity, and validating `action-log` types/JSON). |
| **RISK-04** | **Regex False Positives on Natural Language:** Aggressive SQL/command regexes (e.g., matching `rm`) can block legitimate phrases like *"Please confirm my order"*. | **Medium** | Word-boundary matching (`\brm\b`) and targeted flood bounds (`A{64,}`, `%x{100,}`, `(?:%s){2,}`), verified by `tests/evals/test_security_eval.py` (`100/100`: `61` malicious + `39` legitimate). |

### 1.6 Stage 1 Discovery Sign-Off Decision

- **Verdict:** **Approved to proceed to Stage 2 (`02-problem-metrics.md`)**
- **Agreed Deployment & Service Model:** Multi-service architecture running locally via Podman (`./run.sh` with optional `PHOENIX=false` / `--no-phoenix`) and on **Railway** (`.railway/railway.py`, `.railway/requirements.txt`, `Dockerfile.toolbox`, `scripts/start-toolbox.mjs`) backed by **Neon PostgreSQL** (`DATABASE_URL` with `sslmode=require`)—requiring only `GOOGLE_API_KEY`, `MEM0_API_KEY`, `DATABASE_URL`, and (on Railway with auth-enabled Phoenix) `PHOENIX_SECRET` / `PHOENIX_API_KEY`.

---

## 2. Topology & Security

### 2.1 Multi-Service Topology (Local Podman & Railway Cloud Deployment)

The platform runs as **5 services on Railway + external Neon PostgreSQL** (and locally via Podman Compose in `compose.yaml` + `./run.sh`, where Postgres runs in a container and A2A Judge/Masker share one `a2a` process):

```text
Startup Order:
[1. postgres (local) / Neon (Railway)] ──► [2. mcp-toolbox :5000] ──► [3. a2a-judge :10002 & 4. a2a-masker :10003] ──► [5. web-voice-app :8000 (+ 6. phoenix :6006)]
```

| # | Service Name | Localhost Binding | Railway Internal / Public Address | Protocol | Health Check | Responsibility |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **`postgres` / Neon** | `127.0.0.1:5432` | Neon pooled `DATABASE_URL` (`?sslmode=require`, no Railway Postgres plugin) | TCP / TLS (`postgres`) | `pg_isready` (local) | Relational database (`toolbox_db` / `neondb`) storing `users`, `customer_orders`, and `actions_log`. |
| **2** | **`mcp-toolbox`** | `127.0.0.1:5000` (or internal-only on macOS port-5000 conflict) | `http://${{mcp-toolbox.RAILWAY_PRIVATE_DOMAIN}}:${{mcp-toolbox.PORT}}` (private) | HTTP / MCP | `GET /` | Runs `@toolbox-sdk/server@1.5.0` (`Dockerfile.toolbox` + `scripts/start-toolbox.mjs` preserving `queryParams` like `sslmode=require`). |
| **3** | **`a2a-judge`** | `localhost:10002` | `http://${{a2a-judge.RAILWAY_PRIVATE_DOMAIN}}:${{a2a-judge.PORT}}` (private) | HTTP JSON-RPC 2.0 / SSE | `GET /.well-known/agent.json` | Isolated pre-execution Security & Topic Judge microservice (`POST /rpc`). |
| **4** | **`a2a-masker`** | `localhost:10003` | `http://${{a2a-masker.RAILWAY_PRIVATE_DOMAIN}}:${{a2a-masker.PORT}}` (private) | HTTP JSON-RPC 2.0 / SSE | `GET /.well-known/agent.json` | Isolated post-execution local-regex PII redaction microservice (`POST /rpc`). |
| **5** | **`web-voice-app`** | `127.0.0.1:8000` | **Public HTTPS Domain** (`0.0.0.0:$PORT`) | HTTP / NDJSON / WS | `GET /` | FastAPI app serving Chat UI (`/`), Architecture UI (`/architecture`), REST/NDJSON APIs, and `/voice/ws`. |
| **6** | **`phoenix`** *(Optional)* | `127.0.0.1:6006` (unauthenticated loopback; skip via `PHOENIX=false ./run.sh`) | Internal OTLP `http://${{phoenix.RAILWAY_PRIVATE_DOMAIN}}:${{phoenix.PORT}}` + **Authenticated Public HTTPS** (`PHOENIX_ENABLE_AUTH="true"`, `PHOENIX_SECRET`) | HTTP / OTLP | `GET /` | Standalone `arizephoenix/phoenix:version-22.0.1` OpenTelemetry collector (`/v1/traces`) and trace inspection UI. |

> **Why Railway Multi-Service over Vercel Serverless:**
> 1. `/voice/ws` requires a persistent full-duplex WebSocket connection with live Gemini STT streaming and voice settle/barge-in task management.
> 2. ADK's `InMemorySessionService` and the A2A `InMemoryTaskManager` maintain active session state across turns.
> 3. Running `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and `phoenix` as separate Railway services preserves true microservice isolation while keeping `mcp-toolbox`, `a2a-judge`, and `a2a-masker` private on `*.railway.internal` and protecting public Phoenix traces behind authentication.

### 2.2 Multi-Layer Security & Guardrail Scoping (Zero GCP Project Lock-In)

#### Layer 1: In-Process Input Sanitizer & Local Blocker (`src/security/sanitizer.py`, `src/security/blocker.py`)
- **Length Enforcement:** Rejects any user input exceeding `MAX_INPUT_LENGTH = 300` characters before any network or LLM call occurs.
- **Character Whitelisting:** Strips characters outside `a-zA-Z0-9 .,!?-'` and validates the sanitized string against `^[a-zA-Z0-9\s.,!?()\'-]*$`.
- **Pre-Sanitize Local Pattern Screen:** Evaluates both raw and sanitized/normalized text against `SecurityBlocker` before passing to the agent (catching payloads like `'; DROP TABLE` or `<script>` even if characters are stripped).
- **Self-Contained Operation:** Runs 100% in-process with zero external cloud dependencies (no GCP Model Armor).

#### Layer 2: Isolated A2A Security & Topic Judge (`a2a-judge` on `:10002`) + Prompt Domain Scope
- **Protocol:** Standardized A2A JSON-RPC 2.0 server (`POST /rpc` supporting `tasks/send`, `tasks/sendSubscribe`, `tasks/get`, `tasks/cancel`).
- **100+ Threat Pattern Blocker (`src/security/blocker.py`):** Evaluates both raw input and URL-decoded / leetspeak-normalized input against compiled case-insensitive, multiline regular expressions across 10 threat categories:
  1. **Database Destruction:** `DROP DATABASE/SCHEMA/TABLE/INDEX/TRIGGER/FUNCTION/VIEW/SEQUENCE/USER/TABLESPACE`, `TRUNCATE TABLE`, `ALTER TABLE ... DROP COLUMN`, `ALTER SYSTEM SET`, `REVOKE ALL PRIVILEGES`, `EXEC xp_cmdshell / sp_configure / sp_MSforeachtable`.
  2. **Logical & Auth-Bypass SQLi:** `' OR 1=1`, `' OR '1'='1'`, SQL comments (`--`, `#`, `/* */`), `UNION SELECT`, `information_schema`.
  3. **Blind & Time-Based SQLi:** `WAITFOR DELAY`, `SLEEP()`, `pg_sleep`, `BENCHMARK()`, `DBMS_PIPE.RECEIVE_MESSAGE`, `SUBSTRING(SELECT ...)`.
  4. **Stacked Queries & File Exfiltration:** `; DROP/DELETE/UPDATE/INSERT/CREATE/TRUNCATE`, `LOAD_FILE`, `INTO OUTFILE`, `GROUP_CONCAT`, `UTL_INADDR`, `UTL_HTTP`.
  5. **NoSQL Injection:** `$ne`, `$gt`, `$where`.
  6. **XSS & HTML Injection:** `<script>`, `javascript:`, `onload=`, `onclick=`, `onerror=`, `onmouseover=`, `onsubmit=`, fullwidth Unicode `<script>`.
  7. **OS Command Injection & DoS:** `\brm\b` (word-boundary matched), `sudo`, `wget`, `curl`, `nc`, `ping -l/-s 65...`, `fork bomb`, `slowloris`, `synflood`, `tcpkill`, command chaining (`&&`, `||`, backticks).
  8. **Path Traversal, Log4j & Overflows:** `../`, `..\`, `/etc/passwd`, `c:\windows\system32`, `${jndi:...}`, `${env:...}`, `${ctx:...}`, flood patterns (`A{64,}`, `%x{100,}`, `(?:%s){2,}`).
  9. **Prompt Injection & Jailbreaks:** `ignore ... instructions`, `harmful ... assistant`, `execute ... command`.
  10. **Obfuscation & Evasion:** Leetspeak SQL keywords (`s3l3ct`, `dr0p`, `un10n`, `adm1n`, `p@ssw0rd`), typo variants (`sleect`, `dropp`, `unoin`, `whre`/`wheer`), inline comment splitting (`S/*...*/E/*...*/L...`), hex/URL-encoded keywords, MySQL versioned comments (`/*!50000select*/`), `concat()`, `char()`.
- **Unified Security + Domain-Scope Verdict (Change `13`):** The Judge (`src/agents/judge_agent.py`, `gemini-3.8-flash`) returns one of three strict verdicts—`ALLOW`, `BLOCKED`, or `OFF_TOPIC`—across **Web, Voice, and CLI** (replacing any separate CLI-only Layer 2b service). `OFF_TOPIC` redirects polite out-of-scope requests (politics, trivia, homework, general coding) back to customer support (`OFF_TOPIC_REDIRECT`). Defense-in-depth is reinforced in `SQL_PROMPT_INSTRUCTION` (`src/core/prompts.py`) so the core agent also stays inside customer-support scope even in Quick mode when Judge is toggled off.

#### Layer 3: Isolated A2A Data Masker (`a2a-masker` on `:10003`)
- Inspects agent responses across **16 PII categories** using **deterministic, character-safe local regexes** in `src/security/masker.py` (`src/agents/mask_agent.py` invokes `mask_sensitive_data` directly—zero GCP Cloud DLP SDK and zero LLM calls):
  1. `EMAIL_ADDRESS`
  2. `PHONE_NUMBER`
  3. `CREDIT_CARD_NUMBER`
  4. `US_SOCIAL_SECURITY_NUMBER`
  5. `PERSON_NAME`
  6. `IP_ADDRESS`
  7. `DATE_OF_BIRTH`
  8. `STREET_ADDRESS`
  9. `PASSWORD`
  10. `URL`
  11. `AGE`
  12. `VEHICLE_IDENTIFICATION_NUMBER`
  13. `IBAN_CODE`
  14. `MAC_ADDRESS`
  15. `US_EMPLOYER_IDENTIFICATION_NUMBER`
  16. `LOCATION_COORDINATES`
- **Cloud-Agnostic Redaction & Fail-Safe Fallback:** Replaces detected spans with length-preserving asterisks (`*`) with zero external API keys required; if the A2A Masker process is temporarily unreachable, both `src/api/web.py` and `src/api/cli.py` fall back to local `mask_sensitive_data()` so unmasked PII is never returned.
- **Voice Safety Interlock:** When `MASK=true`, Explain voice turns mask each finished sentence via A2A `:10003` *before* TTS synthesis, while raw unmasked streaming applies only when `MASK=false` and `AGENT_RESPONSE_STREAM=true`.

### 2.3 Access Control & Database Permission Boundaries

| Actor / Service | Target Resource | Permitted Operations | Implemented Mechanism |
| :--- | :--- | :--- | :--- |
| **Authenticated Shopper (`USER_ID`)** | Own Orders & Preferences | Read own orders; request cancel/return/address updates via `actions_log`; recall/save own Mem0 memories. | Login check against `users` (`src/core/greet.py`), SQL-level `WHERE order_id = $1 AND customer_email = $2`, and `_enforce_tenant_tool_callback` binding tool identity args to the session. *(Note: Demo API endpoints accept bare `user_id` for session lookup; signed session cookies/JWTs are deferred to production auth hardening.)* |
| **ADK Support Agent** | MCP Toolset (`cs_agent_tools`) | Call `get-order-status`, `find-customer-orders`, `action-log`, `search_memory`. **Forbidden:** `update-order-status`. | `SQL_PROMPT_INSTRUCTION` + `_enforce_tenant_tool_callback` (hard-blocks `update-order-status` and validates `action-log` `action_type` and JSON object `parameters`). |
| **MCP Toolbox (`toolbox_user` / Neon role)** | PostgreSQL `toolbox_db` / `neondb` | Parameterized SQL queries defined in `mcp_toolbox/tools.yaml` / `.run/tools.yaml`. | Connects via `postgres:5432` in local Podman compose, `127.0.0.1:5432` on host, and Neon pooled `DATABASE_URL` (`?sslmode=require` via `scripts/start-toolbox.mjs` `queryParams`) on Railway. |

### 2.4 Streamlined Environment & Secrets Matrix (Local & Railway)

All GCP project variables (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`) and unused SDKs are removed. Railway packaging lives in `.railway/railway.py`, `.railway/requirements.txt`, `Dockerfile.toolbox`, and `scripts/start-toolbox.mjs`:

| Variable | Classification | Required | Local Default | Railway Multi-Service Value | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | **Secret** | **Yes** | — | `preserve()` secret | Authenticates Gemini Live STT, Support Agent, A2A Judge, and TTS. |
| `MEM0_API_KEY` | **Secret** | **Yes** | — | `preserve()` secret | Authenticates Mem0 Cloud API for customer memory recall and persistence. |
| `DATABASE_URL` | **Secret / Conn** | Local default in `.env.example` | `postgresql://toolbox_user:mysecretpassword@127.0.0.1:5432/toolbox_db` | Neon pooled `DATABASE_URL` (`?sslmode=require`) via `preserve()` | PostgreSQL connection string for `src/core/greet.py` and `scripts/start-toolbox.mjs`. |
| `TOOLBOX_URL` | Service URL | No | `http://127.0.0.1:5000` | `http://${{mcp-toolbox.RAILWAY_PRIVATE_DOMAIN}}:${{mcp-toolbox.PORT}}` | Internal URL for MCP Toolbox server. |
| `A2A_JUDGE_HOST` / `A2A_JUDGE_PORT` | Service Address | No | `localhost` / `10002` | `${{a2a-judge.RAILWAY_PRIVATE_DOMAIN}}` / `${{a2a-judge.PORT}}` | Internal address for A2A Security & Topic Judge microservice. |
| `A2A_MASK_HOST` / `A2A_MASK_PORT` | Service Address | No | `localhost` / `10003` | `${{a2a-masker.RAILWAY_PRIVATE_DOMAIN}}` / `${{a2a-masker.PORT}}` | Internal address for A2A Data Masker microservice. |
| `PHOENIX_URL` | Service URL | No | `http://localhost:6006` | `http://${{phoenix.RAILWAY_PRIVATE_DOMAIN}}:${{phoenix.PORT}}` | Internal OTLP HTTP collector endpoint (`/v1/traces`) and `/v1/projects` lookup. |
| `PHOENIX_PUBLIC_URL` | Public URL | No | `http://localhost:6006` | `https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}` | Browser-accessible URL for `"Open Phoenix"` on `/architecture` and trace deep links. |
| `PHOENIX_ENABLE_AUTH` / `PHOENIX_SECRET` / `PHOENIX_API_KEY` | Auth Config & Secrets | Railway Phoenix only | `PHOENIX_ENABLE_AUTH=false` on loopback `127.0.0.1:6006` | `PHOENIX_ENABLE_AUTH=true`, `PHOENIX_SECRET=preserve()` on `phoenix`; `PHOENIX_API_KEY=preserve()` on `web-voice-app` | Protects public Railway Phoenix traces from unauthenticated access while authorizing OTLP export and `/v1/projects` queries. |
| `VOICE_STT_LIVE_MODEL` / `VOICE_PRICE_STT_IN` / `VOICE_PRICE_STT_OUT` | Voice Config | No | `gemini-3.1-flash-live-preview` / `3.00` / `4.50` | Same defaults (forwarded in `compose.yaml`) | Live STT model and USD per 1M token pricing overrides. |
| `MASK` / `AGENT_RESPONSE_STREAM` / `TELEMETRY` | Runtime Flags | No | `true` / `false` / `true` | `true` / `false` / `true` | Controls PII masking, raw streaming (when `MASK=false`), and OTLP tracing. |
| `RAILWAY_TOKEN` | Deploy Secret | Railway CLI only | Empty in `.env.example` | Set in local `.env` (never committed) | Non-interactive Railway CLI deploys (ignored by `./run.sh`). |

---

## 3. Data Audit & Gaps

### 3.1 Data Source Inventory & Ownership

| Data Store | Technology | Access Mechanism | Owner | Purpose & Lifecycle |
| :--- | :--- | :--- | :--- | :--- |
| **Customer & Order Relational DB** | PostgreSQL 16 (`toolbox_db` local / Neon `neondb` cloud) | Direct `psycopg2` (`src/core/greet.py` auth/context via `DATABASE_URL`) + Declarative **MCP Toolbox** (`@toolbox-sdk/server@1.5.0` on `:5000`) | Client Order Ops / DB Admin | Stores customer credentials, tier metadata, order records, and the immutable `actions_log` audit table. |
| **Cross-Session Customer Memory** | Mem0 Platform (`mem0ai`) | Python SDK (`MemoryClient` via `MEM0_API_KEY`) | AI Platform Team | Stores semantic user preferences and conversation summaries keyed by `user_id = <email>`. Flushed once at session end. |
| **In-Process Session & Task State** | Google ADK `InMemorySessionService` & A2A `InMemoryTaskManager` | In-memory Python dictionaries (`_runners`, `_transcripts`, `tasks`) | Application Runtime | Ephemeral session history (`session_<email>`) and A2A JSON-RPC task state (`submitted → working → completed`). |
| **Telemetry & Span Store** | Standalone Arize Phoenix (`phoenix:version-22.0.1`) + OpenTelemetry | OTLP HTTP (`${PHOENIX_URL}/v1/traces`) with optional `Bearer ${PHOENIX_API_KEY}` | AI / Observability Team | Captures per-turn traces (`agent.turn`, `voice.turn`), LLM token usage, tool arguments/results, and guardrail verdicts. |

### 3.2 Relational Database Schema Audit (`mcp_toolbox/seed.sql`)

#### `users` Table
Stores shopper authentication credentials, display names, and loyalty tier metrics.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `user_id` | `SERIAL` | `PRIMARY KEY` | Internal Identifier | Numeric PK; downstream session/memory APIs use `email` as canonical `user_id`. |
| `email` | `VARCHAR(255)` | `UNIQUE NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Primary lookup key across `customer_orders`, `actions_log`, ADK sessions, and Mem0. |
| `full_name` | `VARCHAR(100)` | Nullable | **Direct PII (`PERSON_NAME`)** | Used in personalized greetings (`Hi {full_name}!`). |
| `is_premium_customer` | `BOOLEAN` | `DEFAULT FALSE` | Business Metadata | Controls Premium tier recognition in CLI greeting and Web plain-text ` · premium` header indicator. |
| `total_items_purchased` | `INTEGER` | `DEFAULT 0` | Business Metadata | Displayed in CLI greeting for Premium customers. |
| `password` | `VARCHAR(255)` | `NOT NULL` | **Credential (`PASSWORD`)** | Demo plaintext passwords (tracked for password hashing in production auth hardening). |

#### `customer_orders` Table
Stores historical and active e-commerce orders.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `order_id` | `SERIAL` | `PRIMARY KEY` | Business Identifier | Queried by integer ID + `customer_email` via `get-order-status`. Seeded explicitly with IDs `1..17` and sequence synced via `setval`. |
| `customer_email` | `VARCHAR(255)` | `NOT NULL REFERENCES users (email)` | **Direct PII (`EMAIL_ADDRESS`)** | Formal FK constraint to `users(email)` plus index `customer_orders_customer_email_idx`. |
| `delivery_address` | `VARCHAR(255)` | Nullable | **Direct PII (`STREET_ADDRESS`)** | High-risk PII field; redacted by A2A Data Masker when `MASK=true`. |
| `status` | `VARCHAR(20)` | `NOT NULL CHECK (status IN ('PROCESSING','SHIPPED','DELIVERED','CANCELLED','RETURNED'))` | Business State | 5 valid lifecycle states. |
| `items` | `JSONB` | `NOT NULL` | Transactional Data | JSON array of `{"product": str, "qty": int, "price": float}`. Agent formats into natural prose. |
| `order_date` | `TIMESTAMPTZ` | `DEFAULT NOW()` | Temporal Metadata | Used for `ORDER BY order_date DESC` in `find-customer-orders`. |
| `total_amount` | `DECIMAL(10, 2)` | `NOT NULL` | Financial Data | Order total in USD. |

#### `actions_log` Table
Immutable audit log recording confirmed customer modification intents without mutating `customer_orders`.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PRIMARY KEY` | Internal Identifier | Returned upon insert (`RETURNING id, timestamp, action_type`). |
| `timestamp` | `TIMESTAMPTZ` | `DEFAULT NOW()` | Temporal Metadata | Audit timestamp. |
| `user_email` | `VARCHAR(255)` | `NOT NULL REFERENCES users (email)` | **Direct PII (`EMAIL_ADDRESS`)** | Formal FK constraint to `users(email)`. |
| `action_type` | `VARCHAR(50)` | `NOT NULL` | Audit Category | Canonical values: `UPDATE_ORDER_STATUS`, `RETURN_ITEM`, `UPDATE_DELIVERY_ADDRESS`, `UPDATE_PROFILE_DETAILS`. |
| `parameters` | `JSONB` | `NOT NULL` | **Mixed / Potential PII** | Validated JSON object payload (e.g., new delivery address, `order_id`, reason). |

### 3.3 Seeded Reference Dataset Profile (`mcp_toolbox/seed.sql`)

`mcp_toolbox/seed.sql` is idempotent and Neon-role-safe (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, sequence `setval`, and `pg_roles`-guarded `toolbox_user` grants) and seeds **10 users** and **17 orders**:

#### Customer Population (10 Accounts)
- **Premium Tier (4 users, `is_premium_customer = TRUE`):**
  1. `hannah.m@school.edu` (`Hannah M`, 94 items, password: `hannah`) — 1 order (`DELIVERED`, Order #14)
  2. `charlie.d@webmail.com` (`Charlie D`, 88 items, password: `charlie`) — 1 order (`DELIVERED`, Order #8)
  3. `julia.child@kitchen.com` (`Julia Child`, 75 items, password: `julia`) — 2 orders (`DELIVERED` #16, `PROCESSING` #17)
  4. `evan.g@bizcorp.com` (`Evan G`, 56 items, password: `evan`) — 1 order (`SHIPPED`, Order #11)
- **Standard Tier (6 users, `is_premium_customer = FALSE`):**
  5. `alice.jones@example.com` (`Alice Jones`, 42 items, password: `alice`) — 4 orders (`DELIVERED` #1 & #2, `SHIPPED` #3, `PROCESSING` #4)
  6. `ian.malcolm@chaos.com` (`Ian Malcolm`, 31 items, password: `ian`) — 1 order (`DELIVERED`, Order #15)
  7. `diana.prince@hero.net` (`Diana Prince`, 23 items, password: `diana`) — 2 orders (`DELIVERED` #9, `RETURNED` #10)
  8. `george.j@jungle.com` (`George J`, 19 items, password: `george`) — 1 order (`PROCESSING`, Order #13)
  9. `bob.smith@techmail.com` (`Bob Smith`, 15 items, password: `bob`) — 3 orders (`DELIVERED` #5, `CANCELLED` #6, `PROCESSING` #7)
  10. `fiona.shrek@swamp.com` (`Fiona Shrek`, 12 items, password: `fiona`) — 1 order (`CANCELLED`, Order #12)

#### Order Status Distribution (17 Orders)
- `DELIVERED`: 8 orders
- `PROCESSING`: 4 orders
- `SHIPPED`: 2 orders
- `CANCELLED`: 2 orders
- `RETURNED`: 1 order

### 3.4 Data Quality, Connection & Schema Gaps Identified & Resolved

| Gap ID | Prototype Finding | Resolution Implemented |
| :--- | :--- | :--- |
| **DATA-GAP-01** | Hardcoded localhost DB connection in `greet.py` and `tools.yaml`. | **Resolved:** `src/core/greet.py` reads `DATABASE_URL` / `PG*`; `scripts/start-toolbox.mjs` rewrites `/tmp/tools.yaml` from `DATABASE_URL` and preserves Neon `?sslmode=require` via `queryParams`. |
| **DATA-GAP-02** | Unscoped `get-order-status` SQL query (`WHERE order_id = $1`). | **Resolved:** `mcp_toolbox/tools.yaml` and `.run/tools.yaml` filter `WHERE order_id = $1 AND customer_email = $2`, backed by `_enforce_tenant_tool_callback`. |
| **DATA-GAP-03** | Tool parameter naming drift (`parameters` vs. `parameters_json`) and `action_type` example drift. | **Resolved:** `src/core/prompts.py`, `mcp_toolbox/tools.yaml`, and `run.sh` all align on `parameters` and canonical `UPDATE_ORDER_STATUS`, `RETURN_ITEM`, `UPDATE_DELIVERY_ADDRESS`, `UPDATE_PROFILE_DETAILS`. |
| **DATA-GAP-04** | UTF-8 byte-offset slicing bug in prototype DLP masker. | **Resolved:** `src/security/masker.py` uses character-safe Python regex substitution across all 16 PII types. |
| **DATA-GAP-05** | Destructive `DROP TABLE IF EXISTS` and unguarded `GRANT ... TO toolbox_user` in `seed.sql`. | **Resolved:** `mcp_toolbox/seed.sql` uses `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, `setval`, and a `pg_roles` guard for `toolbox_user`. |

---

## 4. Workflow Maps

### 4.1 End-to-End Multi-Service Cascade Architecture Flow

All user interactions—whether spoken into a browser microphone, typed in the Web UI, or entered in the Terminal CLI (`src/api/cli.py`)—converge on a single guardrailed reasoning pipeline orchestrated across independent services:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERACTION CHANNELS                                  │
│  [1. Browser Mic (16 kHz PCM)]      [2. Web Chat UI (HTTP)]   [3. CLI: src/api/cli.py]  │
└───────────────┬────────────────────────────────┬─────────────────────────┬──────────────┘
                │ (Voice Only)                   │                         │
                ▼                                │                         │
     ┌─────────────────────────────┐             │                         │
     │   Live Speech-to-Text (STT) │             │                         │
     │ gemini-3.1-flash-live-preview│            │                         │
     │ (PTT 0ms / Quick 400ms /    │             │                         │
     │  Explain 1500ms Settle)     │             │                         │
     └──────────┬──────────────────┘             │                         │
                │                                ▼                         ▼
                └───────────────────► ┌──────────────────────────────────────────┐
                                      │ GUARDRAIL L1: LOCAL SANITIZER & BLOCKER  │
                                      │ • Max 300 chars + char whitelist         │
                                      │ • Raw + normalized 100+ regex blocker    │
                                      └────────────────────┬─────────────────────┘
                                                           │ (A2A JSON-RPC 2.0)
                                                           ▼
                                      ┌──────────────────────────────────────────┐
                                      │ GUARDRAIL L2: A2A SECURITY & TOPIC JUDGE │
                                      │ • Service :10002 (ADK gemini-3.8-flash)  │
                                      │ • Verdicts: ALLOW | BLOCKED | OFF_TOPIC  │
                                      │ • Enforces security + CS domain scope    │
                                      └────────────────────┬─────────────────────┘
                                                           ▼
                                      ┌──────────────────────────────────────────┐
                                      │     CORE ADK SUPPORT AGENT (LlmAgent)    │
                                      │ • Model: gemini-3.8-flash                │
                                      │ • SQL_PROMPT_INSTRUCTION (domain scope)  │
                                      │ • _enforce_tenant_tool_callback          │
                                      ├────────────────────┬─────────────────────┤
                                      │ SERVICE: MCP       │ Python Function     │
                                      │ Toolbox (:5000)    │ • search_memory     │
                                      │ • get-order-status │   (Mem0 Cloud API,  │
                                      │ • find-customer-   │    session-bound)   │
                                      │   orders           │                     │
                                      │ • action-log       │                     │
                                      └─────────┬──────────┴─────────────────────┘
                                                │ (A2A JSON-RPC 2.0, local regex fallback)
                                                ▼
                                      ┌──────────────────────────────────────────┐
                                      │ GUARDRAIL L3: A2A DATA MASKER (:10003)   │
                                      │ • Enabled when MASK=true (default)       │
                                      │ • Deterministic local regex (16 PII)     │
                                      │ • Sentence-level masked voice streaming  │
                                      └─────────┬──────────────────────┬─────────┘
                                                │ (Voice Only)         │ (Text UI / CLI)
                                                ▼                      ▼
                                      ┌────────────────────┐ ┌───────────────────┐
                                      │ Text-to-Speech(TTS)│ │ Render Masked Text│
                                      │gemini-3.8-flash-tts│ │ + "What happened" │
                                      │ (24 kHz PCM Stream)│ │   Step Inspector  │
                                      └────────────────────┘ └───────────────────┘
```

### 4.2 Core Workflow Sequence Maps

#### Workflow 1: Authentication, Context Hydration & Session Lifecycle
1. **Login Request:**
   - **Web UI:** User submits `email` and `password` (`POST /api/login`) with static demo account login hints (`alice.jones@example.com / alice`, `bob.smith@techmail.com / bob`, `julia.child@kitchen.com / julia`).
   - **Terminal CLI (`src/api/cli.py`):** User views the registered user table and enters `email` and masked `password` (`getpass`).
2. **Database Verification (`src/core/greet.py`):**
   - Queries `SELECT user_id, full_name, email, is_premium_customer, total_items_purchased FROM users WHERE email = %s AND password = %s;`.
3. **Idempotent Session Initialization & Refresh Resilience:**
   - If a prior in-memory ADK session (`session_<email>`) exists, it is reset cleanly on login. Reloading a signed-in tab calls `POST /api/session` to cancel the `3000 ms` grace flush (`POST /api/page-leave`) and preserve conversation history.
   - A fresh ADK `Runner` is initialized with `SQL_PROMPT_INSTRUCTION.format(USER_ID=email)`, MCP toolset `cs_agent_tools`, session-bound `make_memory_search_tool(user_id)`, and `before_tool_callback=_enforce_tenant_tool_callback`.
   - *Demo Session Scope Note:* Post-login endpoints identify the active runner by bare `user_id` (email) for demo simplicity; signed session cookies/tokens are reserved for production hardening.
4. **Tier-Aware Greeting:**
   - **Web UI:** Displays `Hi {full_name}!` in the first chat bubble and renders a plain-text ` · premium` indicator next to the shopper name in the header when `is_premium_customer = True`.
   - **Terminal CLI (`src/api/cli.py`):** Runs a 2-stage loader (`[1/2] Authenticating user`, `[2/2] Loading previous actions` from `actions_log`), then prints a Premium greeting (including `total_items_purchased`) or Standard greeting.
5. **Session Termination & Memory Persistence:**
   - Triggered by CLI `quit`/`exit`/`bye`/`q`, Web **Sign out** button (`POST /api/logout`), or browser tab close (`pagehide` via `navigator.sendBeacon` to `/api/page-leave` after the `3000 ms` grace period).
   - Flushes the session transcript (`[{role, content}, ...]`) to **Mem0** (`save_memory(messages, user_id)`) once and removes the session.

#### Workflow 2: Order Status & Order History Lookup
1. **User Utterance:** e.g., *"What's the status of Order #3?"* or *"Show me all my orders"*.
2. **Pre-Agent Security & Scope Gate:** Passes Layer 1 Sanitizer/Blocker and Layer 2 A2A Security & Topic Judge (`:10002`).
3. **Order ID Normalization & Tool Selection:**
   - For a specific order (*"Order #3"* → integer `3`), the agent invokes `get-order-status(order_id=3, customer_email=USER_ID)` (identity enforced by `_enforce_tenant_tool_callback`).
   - For full history, the agent invokes `find-customer-orders(email=USER_ID)`.
4. **Tenant Isolation Check:**
   - Because `get-order-status` runs `WHERE order_id = $1 AND customer_email = $2`, querying another customer's order returns `0 rows` (never leaking into `tool_result`), and the agent responds neutrally:
     > *"I can't find this order in your account. Would you like to check the status of one of your other orders?"*
5. **Natural Language Synthesis & PII Masking:**
   - The agent formats JSON `items` (e.g., `[{"product": "Mechanical Keyboard", "qty": 1, "price": 120.00}]`) into natural prose.
   - If `MASK=true`, the response passes through the local-regex A2A Data Masker (`:10003`, with local fallback) before display/speech.

#### Workflow 3: Read-Confirm-Audit Workflow for Order Mutations
When a customer requests a cancellation, return, status update, or delivery address/profile change:

```text
Customer: "Cancel my processing order"
   │
   ├─► Turn 1 (Read & Verify):
   │     1. Agent calls `find-customer-orders` or `get-order-status` to find the processing order (e.g., Order #4, USB-C Hub).
   │     2. Agent summarizes Order #4 details and asks: "Please confirm if you would like me to cancel Order #4 (USB-C Hub for $45.00)."
   │     3. NO write tool is called on Turn 1.
   │
Customer: "Yes, please confirm"
   │
   └─► Turn 2 (Audit Log Write):
         1. Input passes Sanitizer + Blocker + Judge (note: `\brm\b` word boundary ensures "confirm" is not false-positively blocked).
         2. Agent calls `action-log(user_email=USER_ID, action_type="UPDATE_ORDER_STATUS", parameters='{"order_id": 4, "new_status": "CANCELLED"}')`.
         3. `_enforce_tenant_tool_callback` blocks `update-order-status` and validates `action_type` and JSON object `parameters`.
         4. `actions_log` table records the immutable audit row and returns `id`, `timestamp`, `action_type`.
```

#### Workflow 4: Cascade Voice Turn-Taking, Push-to-Talk & Barge-In (`/voice/ws`)
1. **Client-Side Push-to-Talk & Energy VAD (`src/voice/ui.js`):**
   - Captures mono mic audio at `16,000 Hz` (`2048`-sample frames = `128 ms`), retaining `PREROLL_FRAMES = 3` (`~384 ms`) prior to speech onset (`VAD_RMS = 0.02` over `2` frames).
   - **Push-to-Talk:** Holding the `#mic` button or `Tab` key streams PCM directly to Gemini Live STT (`gemini-3.1-flash-live-preview`); releasing waits `PTT_RELEASE_TAIL_MS = 1000 ms` so final syllables are not clipped, then commits immediately (`0 ms` settle). There are no Hold/Resume buttons.
2. **Server-Side Live STT & Settle Modes (`src/voice/router.py`, `src/voice/stt.py`):**
   - Streams 16 kHz PCM into a Live STT session (`gemini-3.1-flash-live-preview`), emitting interim `partial_transcript` frames.
   - Dispatches immediately on Push-to-Talk `commit: true` (`0 ms`), or after `400 ms` settle (Quick non-PTT) / `1500 ms` settle (Explain non-PTT).
3. **Echo-Resistant Barge-In:**
   - While TTS audio is playing, the browser applies a `400 ms` grace window (`PLAYBACK_GRACE_MS`) and a stricter threshold (`BARGE_RMS = 0.12` over `3` frames).
   - If the caller speaks over the agent (or presses Push-to-Talk), the client stops Web Audio playback and sends `{"type": "interrupt"}`, cancelling the server's running agent/TTS task (`turn_end` with `reason="interrupted"`).
4. **TTS Synthesis & Sentence-Level Masked Streaming:**
   - **Default Safe Mode (`MASK=true`):** Streams LLM output sentence-by-sentence, scrubs **each completed sentence** through A2A Data Masker (`:10003`) *before* synthesizing `24,000 Hz` PCM audio via `gemini-3.8-flash-tts`, ensuring zero unmasked PII is ever spoken aloud while keeping time-to-first-audio responsive.
   - **Unmasked Streaming Mode (`MASK=false` & `AGENT_RESPONSE_STREAM=true` or Quick mode):** Streams clauses directly to TTS without the Masker hop.
