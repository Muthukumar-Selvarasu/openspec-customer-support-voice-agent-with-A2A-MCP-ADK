# Stage 1: Discovery & Scoping (`01-discovery.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 1 — Discovery & Scoping |
| **Input Reference** | [`docs/ENGAGEMENT.md`](ENGAGEMENT.md) |
| **Target Cloud Runtime** | 5–6 Independent Microservices (Localhost `./run.sh` & Railway Private Network `*.railway.internal` + Managed PostgreSQL via Railway / Neon) |
| **Database Engine** | PostgreSQL 15+ (Local `127.0.0.1:5432` / Cloud Managed PostgreSQL on Railway or Neon via `DATABASE_URL`) |
| **External State Stores** | Mem0 Cloud API (Long-Term Memory), Arize Phoenix (OpenTelemetry Trace Store) |
| **Security Posture** | Defense-in-Depth (Local Sanitizer → A2A Security Judge → Prompt/Tool Isolation → A2A PII Masker) |
| **Channels Covered** | Web Chat (`POST /api/chat/stream`), Cascade Voice (`WS /voice/ws`), Terminal CLI (`agent_cli.py`) |
| **Sign-Off Owners** | Forward Deployed Engineering (FDE) Lead & Client Operations / Platform Lead |

---

## 1. Executive Summary

### 1.1 Discovery Overview

During Stage 1 Discovery, the Forward Deployed Engineering (FDE) team audited the Customer's e-commerce order operations, existing codebase baseline, database schemas, security mandates, and cloud deployment targets.

The Customer's primary objective is to automate high-frequency post-purchase support requests—**order status lookups, order history reviews, cancellations, item returns, and delivery address/profile updates**—across three interaction channels (**Real-Time Browser Voice**, **Web Chat**, and **Operator Terminal CLI**) without exposing their PostgreSQL orders database to prompt/SQL injection or leaking Personally Identifiable Information (PII) over synthesized voice.

### 1.2 Stakeholder Interview Findings

| Stakeholder Group | Current Pain Points ("As-Is") | Discovery Requirements & Constraints ("To-Be") |
| :--- | :--- | :--- |
| **Customer Operations & Support Leadership** | • Support agents spend >65% of time on repetitive "Where is my order?" (WISMO) and address/cancellation requests.<br>• Customers must repeat communication preferences (e.g., *"email only"*) on every call.<br>• High-value **Premium** shoppers receive the same generic greeting as Standard shoppers. | • Recognize **Premium** vs. **Standard** tier status immediately upon login.<br>• Persist and recall customer preferences across sessions via long-term memory (**Mem0**).<br>• Never allow an AI agent to directly mutate `customer_orders`; all confirmed changes must be logged to an immutable `actions_log` table for fulfillment review. |
| **InfoSec & Privacy Compliance Team** | • Native Speech-to-Speech (`S2S`) models stream audio directly from weights—once the model begins speaking a street address, credit card, or phone number, PII cannot be retracted.<br>• Giving LLMs database tools creates risks of SQL injection, obfuscated payloads (leetspeak, hex, SQL comments), and cross-tenant order enumeration. | • Enforce a **Pre-Execution Security Gate** (deterministic character/length sanitizer + isolated **A2A Security Judge** microservice) before the support LLM or database tools are invoked.<br>• Enforce a **Post-Execution Privacy Gate** (isolated **A2A Data Masker** microservice scrubbing 16 PII categories) before TTS synthesis.<br>• Eliminate external GCP project lock-in (`GOOGLE_CLOUD_PROJECT`) so PII redaction works out-of-the-box in any cloud environment using deterministic + LLM redaction. |
| **AI / Cloud Platform Engineering Team** | • Multi-agent voice pipelines are typically "black boxes"—engineers cannot see which step added latency, what exact SQL ran, or how much each voice turn cost in tokens/USD.<br>• Need a clean **multi-service cloud deployment on Railway** while keeping local `./run.sh` parity for side-by-side S2S benchmarking. | • Provide an inline **"What happened" step inspector** and a live **`/architecture` SVG topology** (synchronized via `BroadcastChannel`) showing real-time stage execution.<br>• Deploy as independently scalable microservices (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`) communicating over internal service discovery. |

### 1.3 Core Architectural Discovery: Why the Cascade Voice Pattern

A central finding of Discovery is the trade-off between **Native Speech-to-Speech (S2S)** and **Cascade Voice (`STT → Text Pipeline → TTS`)**:

```text
Speech In (16 kHz PCM)
  → Speech-to-Text (gemini-3.1-flash-lite)
  → [ Layer 1 Sanitizer → Layer 2 A2A Security Judge (:10002) → ADK Support Agent (+ MCP Toolbox :5000 & Mem0) → Layer 3 A2A Data Masker (:10003) ]
  → Text-to-Speech (gemini-3.8-flash-tts, 24 kHz PCM)
  → Speech Out
```

#### Key Advantages Confirmed in Discovery
1. **Deterministic Pre-Agent Gating:** Because user audio is transcribed to text *before* reaching the reasoning agent, deterministic sanitizers and the A2A Security Judge can inspect and halt malicious inputs (`BLOCKED`) with zero risk of triggering tool calls.
2. **Guaranteed PII Redaction Before Audio Synthesis:** In buffered masking mode (`MASK=true`), the entire text response is scrubbed by the A2A Data Masker *before* `gemini-3.8-flash-tts` synthesizes a single audio frame.
3. **True Microservice Isolation:** Each stage (`mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`) is a distinct network service that can be deployed, scaled, and monitored independently on Railway.
4. **Independent Stage Accounting:** Latency (`ms`) and token cost (`USD`) are measured independently for `stt`, `judge`, `agent`, `mask`, and `tts`.

### 1.4 Codebase Baseline Audit (What Exists in the Supplied Prototype)

A line-by-line audit of the supplied reference codebase revealed several critical findings that must be addressed during our OpenSpec engineering stages:

| Area | What Exists in Current Codebase | Impact on Cloud (Railway) & Production |
| :--- | :--- | :--- |
| **1. Unnecessary GCP Dependencies (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`)** | • `sanitizer.py` only uses `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `MODEL_ARMOR_TEMPLATE_ID` for an optional REST call to GCP Model Armor.<br>• `masker.py` imports `google.cloud.dlp_v2`. When `GOOGLE_CLOUD_PROJECT` is unset, `masker.py` logs `"No GOOGLE_CLOUD_PROJECT set; returning text unmasked"` and returns raw text—meaning `MASK=true` adds ~3–5s of A2A LLM latency while **redacting nothing**!<br>• `requirements.txt` includes `google-cloud-secret-manager>=2.23.2`, which is **never imported anywhere** in the codebase. | **Remove `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`, `google-cloud-dlp`, and `google-cloud-secret-manager`.** Replace `masker.py` with built-in deterministic regex/pattern redaction across all 16 PII types + Gemini verification so `MASK=true` works 100% self-contained on Railway with only `GOOGLE_API_KEY`. |
| **2. Hardcoded `127.0.0.1` / `localhost` Service URLs** | • `greet.py` hardcodes `host="127.0.0.1"`, `port="5432"`, `dbname="toolbox_db"`, `user="toolbox_user"`, `password="mysecretpassword"`.<br>• `web.py` (lines 66–71) and `agent_cli.py` (lines 51–54, 70) hardcode `A2A_JUDGE_HOST = "localhost"`, `A2A_MASK_HOST = "localhost"`, `TOOLBOX_URL = "http://127.0.0.1:5000"`, `PHOENIX_URL = "http://localhost:6006"`, and bind Uvicorn to `127.0.0.1:8000`. | On Railway, services run in separate containers and communicate over `*.railway.internal` (or `DATABASE_URL`) while binding to `0.0.0.0:$PORT`. All service hosts/ports and DB credentials must read from environment variables with `127.0.0.1` as the local default. |
| **3. Persistent WebSockets & In-Memory State (Why Railway over Vercel)** | • `/voice/ws` (`voice/router.py`) is a stateful, full-duplex WebSocket holding binary PCM buffers, a `1500 ms` async settle timer, and active cancellation handles.<br>• `web.py` stores `_runners` (`InMemorySessionService`) and `_transcripts` in process memory between `/api/login`, `/api/chat/stream`, `/voice/ws`, and `/api/logout`. | **Vercel Serverless Functions cannot host `/voice/ws` or in-memory session state.** Deploying as persistent services on **Railway** (backed by Railway Postgres or Neon Postgres) preserves stateful WebSockets and A2A JSON-RPC/SSE streams natively. |
| **4. Channel Pipeline Drift (`web.py` vs. `agent_cli.py`)** | • `web.py` passes the sanitized string (`clean`) to the ADK agent, whereas `agent_cli.py` sanitizes a local copy, discards it, and passes raw `user_input` to the agent.<br>• `agent_cli.py` runs a 3rd topical guardrail (`guardrail_agent`) and lowercases masked replies (`masked.lower()`), neither of which happens in `web.py`.<br>• `security/blocker.py` computes `self._preprocess_query(query)` (URL-decode + leetspeak normalization) and discards the return value on line 316. | Unify pipeline behavior via OpenSpec domain specifications (`openspec/specs/`) during Stage 4 engineering. |
| **5. Telemetry Browser Pop-Up & Trace Links (`telemetry.py`)** | • `telemetry.py` launches Arize Phoenix in-process (`px.launch_app()`), calls `webbrowser.open("http://localhost:6006")`, and emits `http://localhost:6006/...` links to the browser UI. | Separate `PHOENIX_OTLP_URL` (internal trace ingestion) from `PHOENIX_PUBLIC_URL` (clickable UI deep link) and disable `webbrowser.open()` in headless/cloud containers. |

### 1.5 Technical & Operational Risks Identified During Discovery

| Risk ID | Risk Description | Severity | Discovery Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **RISK-01** | **Streaming TTS vs. PII Masking Conflict:** Sentence-by-sentence TTS streaming cannot scrub PII that spans across tokens or appears mid-sentence before audio is already sent to the browser. | **High** | Enforce a hard configuration interlock: `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`. When `MASK=true` (default), buffer the full reply and run the Data Masker before TTS. |
| **RISK-02** | **Natural Pause Fragmentation in Voice:** Callers pause mid-thought (e.g., *"Can you check my order... um... order number 3?"*), causing naive VAD to fire multiple incomplete turns. | **Medium** | Implement an **Accumulate-and-Combine** turn model: transcribe each speech burst, display a growing `partial_transcript`, and wait `SETTLE_MS = 1500 ms` of quiet before dispatching to the pipeline. Allow **barge-in** cancellation if the user speaks while the agent is responding. |
| **RISK-03** | **Legacy Toolset Over-Permission (`update-order-status`):** The Customer's MCP Toolbox configuration includes a direct `update-order-status` write tool and broad `toolbox_user` table grants. | **High** | Enforce strict system-prompt prohibition on `update-order-status` (requiring `action-log` after user confirmation), and track deterministic tool callbacks + SQL-level tenant scoping in OpenSpec. |
| **RISK-04** | **Regex False Positives on Natural Language:** Aggressive SQL/command injection regexes (e.g., matching `rm` or `select`) can accidentally block legitimate customer sentences like *"Please confirm my order"*. | **Medium** | Use word-boundary matching (`\brm\b`) and exclude valid English words (`"where"`) from typo-evasion patterns; evaluate against a 100-scenario test suite (61 malicious + 39 legitimate). |

### 1.6 Stage 1 Discovery Sign-Off Decision

- **Verdict:** **Approved to proceed to Stage 2 (`02-problem-metrics/`)**
- **Agreed Deployment & Service Model:** Multi-service architecture (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and optional `phoenix`) running identically via `./run.sh` locally and via **Railway** in production—requiring only `GOOGLE_API_KEY`, `MEM0_API_KEY`, and `DATABASE_URL` (zero GCP Cloud Project / DLP / Secret Manager lock-in).

---

## 2. Topology & Security

### 2.1 Multi-Service Topology (Localhost & Railway Cloud Deployment)

The platform is architected as **5 core services (+1 optional observability service)** that run in strict dependency order both locally (`./run.sh`) and as independent services inside a **Railway Project** over Railway Private Networking (`*.railway.internal`):

```text
Startup Order:
[1. postgres :5432] ──► [2. mcp-toolbox :5000] ──► [3. a2a-judge :10002 & 4. a2a-masker :10003] ──► [5. web-voice-app :8000 (+ 6. phoenix :6006)]
```

| # | Service Name | Localhost Binding | Railway Internal / Public Address | Protocol | Health Check | Responsibility |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **`postgres`** | `127.0.0.1:5432` | `postgres.railway.internal:5432` (or Neon `DATABASE_URL`) | TCP (`postgres`) | `pg_isready` | Relational database (`toolbox_db`) storing `users`, `customer_orders`, and `actions_log`. |
| **2** | **`mcp-toolbox`** | `127.0.0.1:5000` | `http://mcp-toolbox.railway.internal:5000` | HTTP / MCP | `GET /` | Runs `@toolbox-sdk/server@1.5.0` exposing parameterized PostgreSQL queries as MCP tools. |
| **3** | **`a2a-judge`** | `localhost:10002` | `http://a2a-judge.railway.internal:10002` | HTTP JSON-RPC 2.0 / SSE | `GET /.well-known/agent.json` | Isolated pre-execution threat evaluation microservice (`POST /rpc`). |
| **4** | **`a2a-masker`** | `localhost:10003` | `http://a2a-masker.railway.internal:10003` | HTTP JSON-RPC 2.0 / SSE | `GET /.well-known/agent.json` | Isolated post-execution PII redaction microservice (`POST /rpc`). |
| **5** | **`web-voice-app`** | `127.0.0.1:8000` | **Public HTTPS Domain** (`0.0.0.0:$PORT`) | HTTP / NDJSON / WS | `GET /` | FastAPI app serving Chat UI (`/`), Architecture UI (`/architecture`), REST/NDJSON APIs, and `/voice/ws`. |
| **6** | **`phoenix`** *(Optional)* | `localhost:6006` (HTTP)<br>`localhost:4317` (gRPC) | `http://phoenix.railway.internal:6006` (+ optional Public Domain) | HTTP / OTLP | `GET /` | Arize Phoenix OpenTelemetry collector (`/v1/traces`) and trace inspection UI. |

> **Why Railway Multi-Service over Vercel Serverless:**
> 1. `/voice/ws` requires a persistent full-duplex WebSocket connection with server-side audio burst accumulation and a `1500 ms` silence settle timer.
> 2. ADK's `InMemorySessionService` and the A2A `InMemoryTaskManager` maintain active session state across turns.
> 3. Running `postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and `phoenix` as separate Railway services preserves true microservice isolation while keeping `mcp-toolbox` and A2A services private on `*.railway.internal` (never exposed to the public internet).

### 2.2 Multi-Layer Security & Guardrail Scoping (Zero GCP Project Lock-In)

#### Layer 1: In-Process Input Sanitizer (`sanitizer.py`)
- **Length Enforcement:** Rejects any user input exceeding `MAX_INPUT_LENGTH = 300` characters before any network or LLM call occurs.
- **Character Whitelisting:** Strips characters outside `a-zA-Z0-9 .,!?-'` and validates the sanitized string against `^[a-zA-Z0-9\s.,!?()\'-]*$`.
- **Self-Contained Operation:** Runs 100% in-process with zero external cloud dependencies (`GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `MODEL_ARMOR_TEMPLATE_ID` are not required).

#### Layer 2: Isolated A2A Security Judge (`a2a-judge` on `:10002`)
- **Protocol:** Standardized A2A JSON-RPC 2.0 server (`POST /rpc` supporting `tasks/send`, `tasks/sendSubscribe`, `tasks/get`, `tasks/cancel`).
- **100+ Threat Pattern Blocker (`blocker.py`):** Evaluates input (with URL-decoding and leetspeak normalization applied) against compiled case-insensitive, multiline regular expressions across 10 threat categories:
  1. **Database Destruction:** `DROP DATABASE/SCHEMA/TABLE/INDEX/TRIGGER/FUNCTION/VIEW/SEQUENCE/USER/TABLESPACE`, `TRUNCATE TABLE`, `ALTER TABLE ... DROP COLUMN`, `ALTER SYSTEM SET`, `REVOKE ALL PRIVILEGES`, `EXEC xp_cmdshell / sp_configure / sp_MSforeachtable`.
  2. **Logical & Auth-Bypass SQLi:** `' OR 1=1`, `' OR '1'='1'`, SQL comments (`--`, `#`, `/* */`), `UNION SELECT`, `information_schema`.
  3. **Blind & Time-Based SQLi:** `WAITFOR DELAY`, `SLEEP()`, `pg_sleep`, `BENCHMARK()`, `DBMS_PIPE.RECEIVE_MESSAGE`, `SUBSTRING(SELECT ...)`.
  4. **Stacked Queries & File Exfiltration:** `; DROP/DELETE/UPDATE/INSERT/CREATE/TRUNCATE`, `LOAD_FILE`, `INTO OUTFILE`, `GROUP_CONCAT`, `UTL_INADDR`, `UTL_HTTP`.
  5. **NoSQL Injection:** `$ne`, `$gt`, `$where`.
  6. **XSS & HTML Injection:** `<script>`, `javascript:`, `onload=`, `onclick=`, `onerror=`, `onmouseover=`, `onsubmit=`, fullwidth Unicode `<script>`.
  7. **OS Command Injection & DoS:** `\brm\b` (word-boundary matched), `sudo`, `wget`, `curl`, `nc`, `ping -l/-s 65...`, `fork bomb`, `slowloris`, `synflood`, `tcpkill`, command chaining (`&&`, `||`, backticks).
  8. **Path Traversal, Log4j & Overflows:** `../`, `..\`, `/etc/passwd`, `c:\windows\system32`, `${jndi:...}`, `${env:...}`, `${ctx:...}`, flood patterns (`A{1000,}`, `%x{100,}`, `%s{100,}`).
  9. **Prompt Injection & Jailbreaks:** `ignore ... instructions`, `harmful ... assistant`, `execute ... command`.
  10. **Obfuscation & Evasion:** Leetspeak SQL keywords (`s3l3ct`, `dr0p`, `un10n`, `adm1n`, `p@ssw0rd`), typo variants (`sleect`, `dropp`, `unoin`, `whre`/`wheer`), inline comment splitting (`S/*...*/E/*...*/L...`), hex/URL-encoded keywords, MySQL versioned comments (`/*!50000select*/`), `concat()`, `char()`.
- **Verdict Enforcement:** If the pattern tool or Judge LLM (`gemini-3.8-flash`) flags the input, it returns `"BLOCKED"`, halting the pipeline immediately before the support agent is called.

#### Layer 2b: Topical & Harmful Content Guardrail (CLI Mode)
- Evaluates CLI turns via a dedicated Guardrail LLM (`gemini-3.8-flash`) returning structured JSON `{"decision": "safe" | "unsafe", "reasoning": "..."}`.
- Blocks hate speech, dangerous content, sexual content, toxic language, and off-topic queries (politics, religion, sports, homework/cheating). Fails open to `"safe"` on JSON parse errors.

#### Layer 3: Isolated A2A Data Masker (`a2a-masker` on `:10003`)
- Inspects agent responses across **16 PII categories**:
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
- **Cloud-Agnostic Redaction:** Replaces detected spans with length-preserving asterisks (`*`) using deterministic pattern redaction + `gemini-3.8-flash` verification—requiring only `GOOGLE_API_KEY` (no `GOOGLE_CLOUD_PROJECT` or GCP Service Account required).
- **Voice Safety Interlock:** When `MASK=true`, token/sentence streaming is disabled (`STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`) so no unmasked syllable is ever synthesized by TTS.

> **Discovery Finding on `masker.py`:** In the supplied codebase, `masker.py` relied on `google.cloud.dlp_v2` and `GOOGLE_CLOUD_PROJECT`—meaning without a GCP project and service account, it silently returned unmasked text while still incurring a 3–5 second A2A LLM round-trip. In our target build on Railway, `masker.py` will execute **self-contained deterministic PII redaction + Gemini `mask_agent` verification** so all 16 PII types are masked with asterisks (`*`) using only `GOOGLE_API_KEY`.

### 2.3 Access Control & Database Permission Boundaries

| Actor / Service | Target Resource | Permitted Operations | Current Codebase Mechanism | Target Hardening (OpenSpec) |
| :--- | :--- | :--- | :--- | :--- |
| **Authenticated Shopper (`USER_ID`)** | Own Orders & Preferences | Read own orders; request cancel/return/address updates via `actions_log`; recall/save own Mem0 memories. | Login check against `users` (`greet.py`) + System prompt binding (`SQL_PROMPT_INSTRUCTION.format(USER_ID=email)`). | Bind authenticated `user_id` at the tool/SQL layer so cross-tenant rows never reach `tool_result` events. |
| **ADK Support Agent** | MCP Toolset (`cs_agent_tools`) | Call `get-order-status`, `find-customer-orders`, `action-log`, `search_memory`. **Forbidden:** `update-order-status`. | System prompt policy (`You MUST NOT call any direct write tools`). | Keep `update-order-status` loaded for compliance testing while enforcing `action-log` audit trail. |
| **MCP Toolbox (`toolbox_user`)** | PostgreSQL `toolbox_db` | Parameterized SQL queries defined in `mcp_toolbox/tools.yaml`. | Connects via `127.0.0.1:5432` in local config. | Connect via `DATABASE_URL` / `PG*` env vars over Railway internal network. |

### 2.4 Streamlined Environment & Secrets Matrix (Local & Railway)

We have eliminated `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`, and `google-cloud-secret-manager`. Only two API keys (`GOOGLE_API_KEY` and `MEM0_API_KEY`) plus standard service URLs are needed:

| Variable | Classification | Required | Local Default | Railway Multi-Service Value | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | **Secret** | **Yes** | — | `<AI Studio Key>` | Authenticates Gemini STT, Support Agent, Judge, Masker, and TTS. |
| `MEM0_API_KEY` | **Secret** | **Yes** | — | `<Mem0 API Key>` | Authenticates Mem0 Cloud API for customer memory recall and persistence. |
| `DATABASE_URL` | **Secret / Conn** | No (uses `PG*` locally) | `postgresql://toolbox_user:mysecretpassword@127.0.0.1:5432/toolbox_db` | `${{Postgres.DATABASE_URL}}` | PostgreSQL connection string for `greet.py` and `mcp-toolbox`. |
| `TOOLBOX_URL` | Service URL | No | `http://127.0.0.1:5000` | `http://${{mcp-toolbox.RAILWAY_PRIVATE_DOMAIN}}:5000` | Internal URL for MCP Toolbox server. |
| `A2A_JUDGE_HOST` / `A2A_JUDGE_PORT` | Service Address | No | `localhost` / `10002` | `${{a2a-judge.RAILWAY_PRIVATE_DOMAIN}}` / `10002` | Internal address for A2A Security Judge microservice. |
| `A2A_MASK_HOST` / `A2A_MASK_PORT` | Service Address | No | `localhost` / `10003` | `${{a2a-masker.RAILWAY_PRIVATE_DOMAIN}}` / `10003` | Internal address for A2A Data Masker microservice. |
| `PHOENIX_URL` | Service URL | No | `http://localhost:6006` | `http://${{phoenix.RAILWAY_PRIVATE_DOMAIN}}:6006` | OTLP HTTP collector endpoint (`/v1/traces`). |
| `PHOENIX_PUBLIC_URL` | Public URL | No | `http://localhost:6006` | `https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}` | Browser-accessible URL for `"View trace in Phoenix ↗"` links in UI. |
| `MASK` | Security Flag | No | `true` | `true` | Enables (`true`) or bypasses (`false`) A2A Data Masker. |
| `AGENT_RESPONSE_STREAM` | Feature Flag | No | `false` | `false` | Enables sentence-streaming TTS when `MASK=false`. |
| `TELEMETRY` | Observability Flag | No | `true` | `true` | Enables OpenTelemetry / OpenInference span export to Phoenix. |

---

## 3. Data Audit & Gaps

### 3.1 Data Source Inventory & Ownership

| Data Store | Technology | Access Mechanism | Owner | Purpose & Lifecycle |
| :--- | :--- | :--- | :--- | :--- |
| **Customer & Order Relational DB** | PostgreSQL 15+ (`toolbox_db`) | Direct `psycopg2` (`greet.py` auth/context via `DATABASE_URL` / `PG*`) + Declarative **MCP Toolbox** (`@toolbox-sdk/server` v1.5.0 on `:5000`) | Client Order Ops / DB Admin | Stores customer credentials, tier metadata, order records, and the immutable `actions_log` audit table. |
| **Cross-Session Customer Memory** | Mem0 Platform (`mem0ai`) | Python SDK (`MemoryClient` via `MEM0_API_KEY`) | AI Platform Team | Stores semantic user preferences and conversation summaries keyed by `user_id = <email>`. Flushed once at session end. |
| **In-Process Session & Task State** | Google ADK `InMemorySessionService` & A2A `InMemoryTaskManager` | In-memory Python dictionaries (`_runners`, `_transcripts`, `tasks`) | Application Runtime | Ephemeral session history (`session_<email>`) and A2A JSON-RPC task state (`submitted → working → completed`). |
| **Telemetry & Span Store** | Arize Phoenix + OpenTelemetry | OTLP HTTP (`${PHOENIX_URL}/v1/traces`) | AI / Observability Team | Captures per-turn traces (`agent.turn`, `voice.turn`), LLM token usage, tool arguments/results, and guardrail verdicts. |

### 3.2 Relational Database Schema Audit (`toolbox_db`)

#### `users` Table
Stores shopper authentication credentials, display names, and loyalty tier metrics.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `user_id` | `SERIAL` | `PRIMARY KEY` | Internal Identifier | Numeric PK; note that downstream session/memory APIs use `email` as canonical `user_id`. |
| `email` | `VARCHAR(255)` | `UNIQUE NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Primary lookup key across `customer_orders`, `actions_log`, ADK sessions, and Mem0. |
| `full_name` | `VARCHAR(100)` | Nullable | **Direct PII (`PERSON_NAME`)** | Used in personalized greetings (`Hi {full_name}!`). |
| `is_premium_customer` | `BOOLEAN` | `DEFAULT FALSE` | Business Metadata | Controls Premium tier recognition in CLI and Web header badge. |
| `total_items_purchased` | `INTEGER` | `DEFAULT 0` | Business Metadata | Displayed in CLI greeting for Premium customers. |
| `password` | `VARCHAR(255)` | `NOT NULL` | **Credential (`PASSWORD`)** | **Gap Identified:** Seeded as plaintext lowercase first name for demo simplicity. |

#### `customer_orders` Table
Stores historical and active e-commerce orders.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `order_id` | `SERIAL` | `PRIMARY KEY` | Business Identifier | Queried by integer ID via `get-order-status`. |
| `customer_email` | `VARCHAR(100)` | `NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Links order to `users.email` (no formal FK constraint in seed DDL). |
| `delivery_address` | `VARCHAR(255)` | Nullable | **Direct PII (`STREET_ADDRESS`)** | High-risk PII field; must be redacted by A2A Data Masker when `MASK=true`. |
| `status` | `VARCHAR(20)` | `CHECK (status IN ('PROCESSING','SHIPPED','DELIVERED','CANCELLED','RETURNED'))` | Business State | 5 valid lifecycle states. |
| `items` | `JSONB` | Nullable | Transactional Data | JSON array of `{"product": str, "qty": int, "price": float}`. Agent must format into natural prose. |
| `order_date` | `TIMESTAMPTZ` | `DEFAULT NOW()` | Temporal Metadata | Used for `ORDER BY order_date DESC` in `find-customer-orders`. |
| `total_amount` | `DECIMAL(10,2)` | Nullable | Financial Data | Order total in USD. |

#### `actions_log` Table
Immutable audit log recording confirmed customer modification intents without mutating `customer_orders`.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PRIMARY KEY` | Internal Identifier | Returned upon insert (`RETURNING id, timestamp, action_type`). |
| `timestamp` | `TIMESTAMPTZ` | `DEFAULT NOW()` | Temporal Metadata | Audit timestamp. |
| `user_email` | `VARCHAR(255)` | `NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Authenticated user email requesting the action. |
| `action_type` | `VARCHAR(50)` | `NOT NULL` | Audit Category | Expected values: `UPDATE_DELIVERY_ADDRESS`, `RETURN_ITEM`, `UPDATE_ORDER_STATUS`, `UPDATE_PROFILE_DETAILS`. |
| `parameters` | `JSONB` | `NOT NULL` | **Mixed / Potential PII** | Free-form JSONB payload (e.g., new delivery address, `order_id`, reason). |

### 3.3 Seeded Reference Dataset Profile (`seed.sql`)

The Customer's baseline dataset (`seed.sql`) contains **10 users** and **17 orders**:

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

### 3.4 Data Quality, Connection & Schema Gaps Identified

| Gap ID | Finding in Current Codebase | Impact | Remediation Path |
| :--- | :--- | :--- | :--- |
| **DATA-GAP-01** | **Hardcoded Localhost DB Connection (`greet.py` & `tools.yaml`):** `greet.py` hardcodes `127.0.0.1:5432` (`toolbox_db` / `toolbox_user` / `mysecretpassword`), and `run.sh` writes hardcoded localhost credentials into `mcp_toolbox/tools.yaml`. | Cannot connect to managed PostgreSQL on **Railway** or **Neon** (`DATABASE_URL` / `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`). | Update `greet.py` and the `tools.yaml` generator/entrypoint to parse `DATABASE_URL` or `PG*` environment variables, defaulting to `127.0.0.1:5432` locally. |
| **DATA-GAP-02** | **Unscoped `get-order-status` SQL Query:** `SELECT ... FROM customer_orders WHERE order_id = $1;` does not filter by `customer_email`. | If User A asks for Order #5 (User B's order), PostgreSQL returns User B's row (and `web.py` streams it in the `tool_result` NDJSON event to the browser UI!) even though the LLM prompt refuses to state it in prose. | Track in OpenSpec to enforce tenant isolation at the tool/SQL boundary. |
| **DATA-GAP-03** | **Tool Parameter Naming Drift (`parameters` vs. `parameters_json`):** The MCP tool `action-log` defines the 3rd parameter as `parameters` (`tools.yaml`), whereas `prompts.py` line 56 refers to `parameters_json`. | Can cause LLM tool-call validation mismatches. | Align `prompts.py` and `tools.yaml` on `parameters`. |
| **DATA-GAP-04** | **UTF-8 Byte Offset vs. Character Slicing in Masker:** `masker.py` slices Python `str` (`masked_text[:start]`) using UTF-8 byte offsets (`byte_range.start`), which shifts indexes whenever multibyte characters (`—`, `…`, smart quotes) appear before a PII span. | Corrupts masked strings containing non-ASCII punctuation or names. | Use character-span replacement (`re.sub` / character offsets) in the self-contained masker. |
| **DATA-GAP-05** | **Destructive Re-Seed (`DROP TABLE IF EXISTS`):** `seed.sql` drops and recreates `actions_log`, `customer_orders`, and `users`. | Useful for local benchmark resets (`./run.sh seed`), but unsafe for live cloud restarts. | Use `CREATE TABLE IF NOT EXISTS` + idempotent `ON CONFLICT (email) DO NOTHING` seeding for Railway deployment startup. |

---

## 4. Workflow Maps

### 4.1 End-to-End Multi-Service Cascade Architecture Flow

All user interactions—whether spoken into a browser microphone, typed in the Web UI, or entered in the Terminal CLI—converge on a single guardrailed reasoning pipeline orchestrated across independent services:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERACTION CHANNELS                                  │
│  [1. Browser Mic (16 kHz PCM)]      [2. Web Chat UI (HTTP)]      [3. Terminal CLI]      │
└───────────────┬────────────────────────────────┬─────────────────────────┬──────────────┘
                │ (Voice Only)                   │                         │
                ▼                                │                         │
     ┌──────────────────────┐                    │                         │
     │  Speech-to-Text (STT)│                    │                         │
     │ gemini-3.1-flash-lite│                    │                         │
     │ (1500ms Settle Timer)│                    │                         │
     └──────────┬───────────┘                    │                         │
                │                                ▼                         ▼
                └───────────────────► ┌──────────────────────────────────────────┐
                                      │      LAYER 1: LOCAL INPUT SANITIZER      │
                                      │ • Max 300 chars (`MAX_INPUT_LENGTH`)     │
                                      │ • Whitelist strip + Regex validation     │
                                      └────────────────────┬─────────────────────┘
                                                           │ (A2A JSON-RPC 2.0)
                                                           ▼
                                      ┌──────────────────────────────────────────┐
                                      │  SERVICE: A2A SECURITY JUDGE (:10002)    │
                                      │ • 100+ SQLi / XSS / Cmd / Prompt regexes │
                                      │ • Gemini 3.8 Flash threat reasoning      │
                                      │ • Verdict: Echo text OR return "BLOCKED" │
                                      └────────────────────┬─────────────────────┘
                                                           │ (CLI also runs Layer 2b
                                                           │  Topical Guardrail Agent)
                                                           ▼
                                      ┌──────────────────────────────────────────┐
                                      │     CORE ADK SUPPORT AGENT (LlmAgent)    │
                                      │ • Model: gemini-3.8-flash                │
                                      │ • Bound to authenticated USER_ID (email) │
                                      ├────────────────────┬─────────────────────┤
                                      │ SERVICE: MCP       │ Python Function     │
                                      │ Toolbox (:5000)    │ • search_memory     │
                                      │ • get-order-status │   (Mem0 Cloud API)  │
                                      │ • find-customer-   │                     │
                                      │   orders           │                     │
                                      │ • action-log       │                     │
                                      └─────────┬──────────┴─────────────────────┘
                                                │ (A2A JSON-RPC 2.0)
                                                ▼
                                      ┌──────────────────────────────────────────┐
                                      │   SERVICE: A2A DATA MASKER (:10003)      │
                                      │ • Enabled when MASK=true (default)       │
                                      │ • Self-contained 16-PII redaction + LLM  │
                                      │ • Replaces spans with asterisks (*)      │
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
   - **Web UI:** User submits `email` and `password` (`POST /api/login`) or clicks a Demo Account chip (`alice.jones@example.com`, `bob.smith@techmail.com`, `julia.child@kitchen.com`).
   - **Terminal CLI:** User views the registered user table and enters `email` and masked `password` (`getpass`).
2. **Database Verification (`greet.py`):**
   - Queries `SELECT user_id, full_name, email, is_premium_customer, total_items_purchased FROM users WHERE email = %s AND password = %s;`.
3. **Idempotent Session Initialization:**
   - If a prior in-memory ADK session (`session_<email>`) exists, it is deleted along with any unsaved transcript buffer.
   - A fresh ADK `Runner` is initialized with `SQL_PROMPT_INSTRUCTION.format(USER_ID=email)`, MCP toolset `cs_agent_tools`, and `search_memory`.
4. **Tier-Aware Greeting:**
   - **Web UI:** Displays `Hi {full_name}!` in the first chat bubble and adds a `premium` badge in the top bar when `is_premium_customer = True`.
   - **Terminal CLI:** Runs a 4-stage loader (`[1/4] Authenticating user`, `[2/4] Loading user memory`, `[3/4] Loading current orders`, `[4/4] Loading previous actions` from `actions_log`), then prints a Premium greeting (including `total_items_purchased`) or Standard greeting.
5. **Session Termination & Memory Persistence:**
   - Triggered by CLI `quit`/`exit`/`bye`/`q`, Web **Sign out** button (`POST /api/logout`), or browser tab close (`pagehide` via `navigator.sendBeacon`).
   - Flushes the session transcript (`[{role, content}, ...]`) to **Mem0** (`mem0.add(messages, user_id=email)`) exactly once and removes the session.

#### Workflow 2: Order Status & Order History Lookup
1. **User Utterance:** e.g., *"What's the status of Order #3?"* or *"Show me all my orders"*.
2. **Pre-Agent Security Gate:** Passes Layer 1 Sanitizer and Layer 2 A2A Security Judge (`:10002`).
3. **Order ID Normalization & Tool Selection:**
   - For a specific order (*"Order #3"* → integer `3`), the agent invokes `get-order-status(order_id=3)`.
   - For full history, the agent invokes `find-customer-orders(email=USER_ID)`.
4. **Tenant Isolation Check:**
   - If `get-order-status` returns an order whose `customer_email != USER_ID` (or returns `[]`), the agent **never** discloses the owner or existence of the order and responds:
     > *"I can't find this order in your account. Would you like to check the status of one of your other orders?"*
5. **Natural Language Synthesis & PII Masking:**
   - The agent formats JSON `items` (e.g., `[{"product": "Mechanical Keyboard", "qty": 1, "price": 120.00}]`) into natural prose.
   - If `MASK=true`, the response passes through A2A Data Masker (`:10003`) before display/speech.

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
         1. Input passes Sanitizer + Judge (note: `\brm\b` word boundary ensures "confirm" is not false-positively blocked).
         2. Agent calls `action-log(user_email=USER_ID, action_type="UPDATE_ORDER_STATUS", parameters='{"order_id": 4, "new_status": "CANCELLED"}')`.
         3. Agent NEVER calls `update-order-status`.
         4. `actions_log` table records the immutable audit row and returns `id`, `timestamp`, `action_type`.
```

#### Workflow 4: Cascade Voice Turn-Taking & Barge-In (`/voice/ws`)
1. **Client-Side Audio Capture & Energy VAD (`ui.js`):**
   - Captures mono mic audio at `16,000 Hz` (`2048`-sample frames = `128 ms`).
   - Retains `PREROLL_FRAMES = 3` (`~384 ms`) prior to speech onset (`VAD_RMS = 0.02` over `2` frames).
   - Ends a speech burst after `END_SILENCE_MS = 1500 ms` of silence (ignoring bursts `< 400 ms`).
2. **Server-Side Multi-Burst Accumulation (`router.py`):**
   - Wraps each PCM burst in a WAV header and transcribes via `gemini-3.1-flash-lite` under an async lock.
   - Appends text to `pending`, emits `{"type": "partial_transcript", "text": pending}`, and resets a `SETTLE_MS = 1500 ms` timer.
   - Once the caller stays quiet for `1500 ms`, dispatches the combined `pending` text into `text_pipeline`.
3. **Echo-Resistant Barge-In:**
   - While TTS audio is playing, the browser applies a `400 ms` grace window (`PLAYBACK_GRACE_MS`) and a stricter threshold (`BARGE_RMS = 0.05` over `3` frames).
   - If the caller speaks over the agent, the client stops Web Audio playback and sends `{"type": "interrupt"}`, cancelling the server's running agent/TTS task (`turn_end` with `reason="interrupted"`).
4. **TTS Synthesis & Safety Interlock:**
   - **Default Safe Mode (`MASK=true`):** Buffers full reply → runs A2A Data Masker → synthesizes `24,000 Hz` PCM audio via `gemini-3.8-flash-tts` in `48,000`-byte (~1s) chunks.
   - **Low-Latency Streaming Mode (`MASK=false` & `AGENT_RESPONSE_STREAM=true`):** Splits LLM output on sentence boundaries (`.!?…`) and streams TTS audio concurrently while subsequent sentences are still being generated.

