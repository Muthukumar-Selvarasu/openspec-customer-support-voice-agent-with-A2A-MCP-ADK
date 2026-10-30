# Stage 1: Access, Network, Security & Compliance Scoping (`access-security-scoping.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 1 — Discovery & Scoping |
| **Deployment Architecture** | 5–6 Independent Microservices (Localhost & Railway Private Network `*.railway.internal`) |
| **Security Posture** | Defense-in-Depth (Local Sanitizer → A2A Security Judge → Prompt/Tool Isolation → A2A PII Masker) |

---

## 1. Multi-Service Topology (Localhost & Railway Cloud Deployment)

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

---

## 2. Multi-Layer Security & Guardrail Scoping (Zero GCP Project Lock-In)

### Layer 1: In-Process Input Sanitizer (`sanitizer.py`)
- **Length Enforcement:** Rejects any user input exceeding `MAX_INPUT_LENGTH = 300` characters before any network or LLM call occurs.
- **Character Whitelisting:** Strips characters outside `a-zA-Z0-9 .,!?-'` and validates the sanitized string against `^[a-zA-Z0-9\s.,!?()\'-]*$`.
- **Self-Contained Operation:** Runs 100% in-process with zero external cloud dependencies (`GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `MODEL_ARMOR_TEMPLATE_ID` are not required).

### Layer 2: Isolated A2A Security Judge (`a2a-judge` on `:10002`)
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

### Layer 2b: Topical & Harmful Content Guardrail (CLI Mode)
- Evaluates CLI turns via a dedicated Guardrail LLM (`gemini-3.8-flash`) returning structured JSON `{"decision": "safe" | "unsafe", "reasoning": "..."}`.
- Blocks hate speech, dangerous content, sexual content, toxic language, and off-topic queries (politics, religion, sports, homework/cheating). Fails open to `"safe"` on JSON parse errors.

### Layer 3: Isolated A2A Data Masker (`a2a-masker` on `:10003`)
- Inspects agent responses across **16 PII categories** (`EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD_NUMBER`, `US_SOCIAL_SECURITY_NUMBER`, `PERSON_NAME`, `IP_ADDRESS`, `DATE_OF_BIRTH`, `STREET_ADDRESS`, `PASSWORD`, `URL`, `AGE`, `VEHICLE_IDENTIFICATION_NUMBER`, `IBAN_CODE`, `MAC_ADDRESS`, `US_EMPLOYER_IDENTIFICATION_NUMBER`, `LOCATION_COORDINATES`).
- **Cloud-Agnostic Redaction:** Replaces detected spans with length-preserving asterisks (`*`) using deterministic pattern redaction + `gemini-3.8-flash` verification—requiring only `GOOGLE_API_KEY` (no `GOOGLE_CLOUD_PROJECT` or GCP Service Account required).
- **Voice Safety Interlock:** When `MASK=true`, token/sentence streaming is disabled (`STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`) so no unmasked syllable is ever synthesized by TTS.

---

## 3. Access Control & Database Permission Boundaries

| Actor / Service | Target Resource | Permitted Operations | Current Codebase Mechanism | Target Hardening (OpenSpec) |
| :--- | :--- | :--- | :--- | :--- |
| **Authenticated Shopper (`USER_ID`)** | Own Orders & Preferences | Read own orders; request cancel/return/address updates via `actions_log`; recall/save own Mem0 memories. | Login check against `users` (`greet.py`) + System prompt binding (`SQL_PROMPT_INSTRUCTION.format(USER_ID=email)`). | Bind authenticated `user_id` at the tool/SQL layer so cross-tenant rows never reach `tool_result` events. |
| **ADK Support Agent** | MCP Toolset (`cs_agent_tools`) | Call `get-order-status`, `find-customer-orders`, `action-log`, `search_memory`. **Forbidden:** `update-order-status`. | System prompt policy (`You MUST NOT call any direct write tools`). | Keep `update-order-status` loaded for compliance testing while enforcing `action-log` audit trail. |
| **MCP Toolbox (`toolbox_user`)** | PostgreSQL `toolbox_db` | Parameterized SQL queries defined in `mcp_toolbox/tools.yaml`. | Connects via `127.0.0.1:5432` in local config. | Connect via `DATABASE_URL` / `PG*` env vars over Railway internal network. |

---

## 4. Streamlined Environment & Secrets Matrix (Local & Railway)

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
