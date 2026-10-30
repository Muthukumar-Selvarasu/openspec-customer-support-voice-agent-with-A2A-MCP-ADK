# Stage 1: Discovery Findings Report (`discovery-report.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 1 — Discovery & Scoping |
| **Input Reference** | [`docs/ENGAGEMENT.md`](../ENGAGEMENT.md) |
| **Target Cloud Runtime** | Railway Multi-Service Architecture (+ Managed PostgreSQL via Railway / Neon) |
| **Sign-Off Owners** | Forward Deployed Engineering (FDE) Lead & Client Operations / Platform Lead |

---

## 1. Executive Summary of Discovery

During Stage 1 Discovery, the Forward Deployed Engineering (FDE) team audited the Customer's e-commerce order operations, existing codebase baseline, database schemas, security mandates, and cloud deployment targets.

The Customer's primary objective is to automate high-frequency post-purchase support requests—**order status lookups, order history reviews, cancellations, item returns, and delivery address/profile updates**—across three interaction channels (**Real-Time Browser Voice**, **Web Chat**, and **Operator Terminal CLI**) without exposing their PostgreSQL orders database to prompt/SQL injection or leaking Personally Identifiable Information (PII) over synthesized voice.

---

## 2. Stakeholder Interview Findings

| Stakeholder Group | Current Pain Points ("As-Is") | Discovery Requirements & Constraints ("To-Be") |
| :--- | :--- | :--- |
| **Customer Operations & Support Leadership** | • Support agents spend >65% of time on repetitive "Where is my order?" (WISMO) and address/cancellation requests.<br>• Customers must repeat communication preferences (e.g., *"email only"*) on every call.<br>• High-value **Premium** shoppers receive the same generic greeting as Standard shoppers. | • Recognize **Premium** vs. **Standard** tier status immediately upon login.<br>• Persist and recall customer preferences across sessions via long-term memory (**Mem0**).<br>• Never allow an AI agent to directly mutate `customer_orders`; all confirmed changes must be logged to an immutable `actions_log` table for fulfillment review. |
| **InfoSec & Privacy Compliance Team** | • Native Speech-to-Speech (`S2S`) models stream audio directly from weights—once the model begins speaking a street address, credit card, or phone number, PII cannot be retracted.<br>• Giving LLMs database tools creates risks of SQL injection, obfuscated payloads (leetspeak, hex, SQL comments), and cross-tenant order enumeration. | • Enforce a **Pre-Execution Security Gate** (deterministic character/length sanitizer + isolated **A2A Security Judge** microservice) before the support LLM or database tools are invoked.<br>• Enforce a **Post-Execution Privacy Gate** (isolated **A2A Data Masker** microservice scrubbing 16 PII categories) before TTS synthesis.<br>• Eliminate external GCP project lock-in (`GOOGLE_CLOUD_PROJECT`) so PII redaction works out-of-the-box in any cloud environment using deterministic + LLM redaction. |
| **AI / Cloud Platform Engineering Team** | • Multi-agent voice pipelines are typically "black boxes"—engineers cannot see which step added latency, what exact SQL ran, or how much each voice turn cost in tokens/USD.<br>• Need a clean **multi-service cloud deployment on Railway** while keeping local `./run.sh` parity for side-by-side S2S benchmarking. | • Provide an inline **"What happened" step inspector** and a live **`/architecture` SVG topology** (synchronized via `BroadcastChannel`) showing real-time stage execution.<br>• Deploy as independently scalable microservices (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`) communicating over internal service discovery. |

---

## 3. Core Architectural Discovery: Why the Cascade Voice Pattern

A central finding of Discovery is the trade-off between **Native Speech-to-Speech (S2S)** and **Cascade Voice (`STT → Text Pipeline → TTS`)**:

```text
Speech In (16 kHz PCM)
  → Speech-to-Text (gemini-3.1-flash-lite)
  → [ Layer 1 Sanitizer → Layer 2 A2A Security Judge (:10002) → ADK Support Agent (+ MCP Toolbox :5000 & Mem0) → Layer 3 A2A Data Masker (:10003) ]
  → Text-to-Speech (gemini-3.8-flash-tts, 24 kHz PCM)
  → Speech Out
```

### Key Advantages Confirmed in Discovery
1. **Deterministic Pre-Agent Gating:** Because user audio is transcribed to text *before* reaching the reasoning agent, deterministic sanitizers and the A2A Security Judge can inspect and halt malicious inputs (`BLOCKED`) with zero risk of triggering tool calls.
2. **Guaranteed PII Redaction Before Audio Synthesis:** In buffered masking mode (`MASK=true`), the entire text response is scrubbed by the A2A Data Masker *before* `gemini-3.8-flash-tts` synthesizes a single audio frame.
3. **True Microservice Isolation:** Each stage (`mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`) is a distinct network service that can be deployed, scaled, and monitored independently on Railway.
4. **Independent Stage Accounting:** Latency (`ms`) and token cost (`USD`) are measured independently for `stt`, `judge`, `agent`, `mask`, and `tts`.

---

## 4. Codebase Baseline Audit (What Exists in the Supplied Prototype)

A line-by-line audit of the supplied reference codebase revealed several critical findings that must be addressed during our OpenSpec engineering stages:

| Area | What Exists in Current Codebase | Impact on Cloud (Railway) & Production |
| :--- | :--- | :--- |
| **1. Unnecessary GCP Dependencies (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`)** | • `sanitizer.py` only uses `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `MODEL_ARMOR_TEMPLATE_ID` for an optional REST call to GCP Model Armor.<br>• `masker.py` imports `google.cloud.dlp_v2`. When `GOOGLE_CLOUD_PROJECT` is unset, `masker.py` logs `"No GOOGLE_CLOUD_PROJECT set; returning text unmasked"` and returns raw text—meaning `MASK=true` adds ~3–5s of A2A LLM latency while **redacting nothing**!<br>• `requirements.txt` includes `google-cloud-secret-manager>=2.23.2`, which is **never imported anywhere** in the codebase. | **Remove `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `MODEL_ARMOR_TEMPLATE_ID`, `google-cloud-dlp`, and `google-cloud-secret-manager`.** Replace `masker.py` with built-in deterministic regex/pattern redaction across all 16 PII types + Gemini verification so `MASK=true` works 100% self-contained on Railway with only `GOOGLE_API_KEY`. |
| **2. Hardcoded `127.0.0.1` / `localhost` Service URLs** | • `greet.py` hardcodes `host="127.0.0.1"`, `port="5432"`, `dbname="toolbox_db"`, `user="toolbox_user"`, `password="mysecretpassword"`.<br>• `web.py` (lines 66–71) and `agent_cli.py` (lines 51–54, 70) hardcode `A2A_JUDGE_HOST = "localhost"`, `A2A_MASK_HOST = "localhost"`, `TOOLBOX_URL = "http://127.0.0.1:5000"`, `PHOENIX_URL = "http://localhost:6006"`, and bind Uvicorn to `127.0.0.1:8000`. | On Railway, services run in separate containers and communicate over `*.railway.internal` (or `DATABASE_URL`) while binding to `0.0.0.0:$PORT`. All service hosts/ports and DB credentials must read from environment variables with `127.0.0.1` as the local default. |
| **3. Persistent WebSockets & In-Memory State (Why Railway over Vercel)** | • `/voice/ws` (`voice/router.py`) is a stateful, full-duplex WebSocket holding binary PCM buffers, a `1500 ms` async settle timer, and active cancellation handles.<br>• `web.py` stores `_runners` (`InMemorySessionService`) and `_transcripts` in process memory between `/api/login`, `/api/chat/stream`, `/voice/ws`, and `/api/logout`. | **Vercel Serverless Functions cannot host `/voice/ws` or in-memory session state.** Deploying as persistent services on **Railway** (backed by Railway Postgres or Neon Postgres) preserves stateful WebSockets and A2A JSON-RPC/SSE streams natively. |
| **4. Channel Pipeline Drift (`web.py` vs. `agent_cli.py`)** | • `web.py` passes the sanitized string (`clean`) to the ADK agent, whereas `agent_cli.py` sanitizes a local copy, discards it, and passes raw `user_input` to the agent.<br>• `agent_cli.py` runs a 3rd topical guardrail (`guardrail_agent`) and lowercases masked replies (`masked.lower()`), neither of which happens in `web.py`.<br>• `security/blocker.py` computes `self._preprocess_query(query)` (URL-decode + leetspeak normalization) and discards the return value on line 316. | Unify pipeline behavior via OpenSpec domain specifications (`openspec/specs/`) during Stage 4 engineering. |
| **5. Telemetry Browser Pop-Up & Trace Links (`telemetry.py`)** | • `telemetry.py` launches Arize Phoenix in-process (`px.launch_app()`), calls `webbrowser.open("http://localhost:6006")`, and emits `http://localhost:6006/...` links to the browser UI. | Separate `PHOENIX_OTLP_URL` (internal trace ingestion) from `PHOENIX_PUBLIC_URL` (clickable UI deep link) and disable `webbrowser.open()` in headless/cloud containers. |

---

## 5. Technical & Operational Risks Identified During Discovery

| Risk ID | Risk Description | Severity | Discovery Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **RISK-01** | **Streaming TTS vs. PII Masking Conflict:** Sentence-by-sentence TTS streaming cannot scrub PII that spans across tokens or appears mid-sentence before audio is already sent to the browser. | **High** | Enforce a hard configuration interlock: `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`. When `MASK=true` (default), buffer the full reply and run the Data Masker before TTS. |
| **RISK-02** | **Natural Pause Fragmentation in Voice:** Callers pause mid-thought (e.g., *"Can you check my order... um... order number 3?"*), causing naive VAD to fire multiple incomplete turns. | **Medium** | Implement an **Accumulate-and-Combine** turn model: transcribe each speech burst, display a growing `partial_transcript`, and wait `SETTLE_MS = 1500 ms` of quiet before dispatching to the pipeline. Allow **barge-in** cancellation if the user speaks while the agent is responding. |
| **RISK-03** | **Legacy Toolset Over-Permission (`update-order-status`):** The Customer's MCP Toolbox configuration includes a direct `update-order-status` write tool and broad `toolbox_user` table grants. | **High** | Enforce strict system-prompt prohibition on `update-order-status` (requiring `action-log` after user confirmation), and track deterministic tool callbacks + SQL-level tenant scoping in OpenSpec. |
| **RISK-04** | **Regex False Positives on Natural Language:** Aggressive SQL/command injection regexes (e.g., matching `rm` or `select`) can accidentally block legitimate customer sentences like *"Please confirm my order"*. | **Medium** | Use word-boundary matching (`\brm\b`) and exclude valid English words (`"where"`) from typo-evasion patterns; evaluate against a 100-scenario test suite (61 malicious + 39 legitimate). |

---

## 6. Stage 1 Discovery Sign-Off Decision

- **Verdict:** **Approved to proceed to Stage 2 (`02-problem-metrics/`)**
- **Agreed Deployment & Service Model:** Multi-service architecture (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, and optional `phoenix`) running identically via `./run.sh` locally and via **Railway** in production—requiring only `GOOGLE_API_KEY`, `MEM0_API_KEY`, and `DATABASE_URL` (zero GCP Cloud Project / DLP / Secret Manager lock-in).
