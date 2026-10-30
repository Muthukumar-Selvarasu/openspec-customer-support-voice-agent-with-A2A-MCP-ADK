# Stage 2: Problem Statement & Scope Brief (`problem-brief.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 2 — Problem & Metrics |
| **Inputs** | [`docs/ENGAGEMENT.md`](../ENGAGEMENT.md), [`docs/01-discovery/discovery-report.md`](../01-discovery/discovery-report.md) |
| **Sign-Off Owners** | Client Product Owner, Client InfoSec Lead & FDE Architect |

---

## 1. Core Problem Statement

E-commerce customer support organizations face a fundamental tension when adopting generative AI across **spoken voice** and **text chat**:

1. **The Security & Data Integrity Problem:**
   Connecting an LLM agent directly to an operational PostgreSQL orders database (`toolbox_db`) introduces high-severity risks:
   - **Adversarial Input Attacks:** SQL injection, stacked queries, command injection, XSS, path traversal, obfuscated leetspeak/hex payloads, and prompt jailbreaks.
   - **Cross-Customer Data Leakage (IDOR / Enumeration):** Shopper A asking for the status or delivery address of Shopper B's order (`order_id`), or the UI streaming raw cross-tenant rows before the model filters them.
   - **Unauthorized Live Table Mutations:** An LLM autonomously executing `UPDATE` or `DELETE` statements on `customer_orders` without human confirmation or an immutable audit trail.

2. **The Voice Privacy Problem (Cascade vs. Speech-to-Speech):**
   In native Speech-to-Speech (`S2S`) models, audio frames stream directly from model weights to the caller's speaker. Once the model begins speaking a street address, email, phone number, or credit card number aloud, Data Loss Prevention (DLP) cannot retract it.

3. **The Statelessness Problem:**
   Customers must repeat communication preferences (e.g., *"I prefer email contact only"*) across separate calls or chat sessions, and high-value **Premium** shoppers are not recognized for their loyalty tier.

4. **The Observability & Cost Opacity Problem:**
   Engineering and security teams lack glass-box visibility into what happens inside a multi-agent voice turn: what STT transcribed, why a security gate passed or blocked, what exact SQL query MCP Toolbox ran, which rows came back, how many tokens each stage consumed, and what the turn cost in USD.

---

## 2. Solution Hypothesis: The Guardrailed Cascade Architecture

By decomposing every voice turn into a **Cascade Pipeline** orchestrated across isolated microservices:

```text
Browser Mic (16 kHz PCM)
  ──► Speech-to-Text (gemini-3.1-flash-lite, 1500 ms multi-burst settle)
  ──► Layer 1 Local Sanitizer (300-char limit + character whitelist)
  ──► Layer 2 A2A Security Judge (:10002, 100+ regex patterns + gemini-3.8-flash)
  ──► Core ADK Support Agent (gemini-3.8-flash + MCP Toolbox :5000 + Mem0)
  ──► Layer 3 A2A Data Masker (:10003, 16-PII redaction + gemini-3.8-flash)
  ──► Text-to-Speech (gemini-3.8-flash-tts, 24 kHz PCM stream)
```

We can guarantee:
1. **Pre-Agent Threat Blocking:** Malicious utterances are blocked *before* the support agent or database tools are ever invoked.
2. **Post-Agent PII Scrubbing Before Speech:** When `MASK=true` (default), the complete text reply is scrubbed of all 16 PII categories *before* TTS synthesis begins (`STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`).
3. **Audit-Only Order Modifications:** Every cancellation, return, status update, or address change follows a strict **Read → Confirm → Audit (`actions_log`)** workflow, never calling `update-order-status`.
4. **Full Glass-Box Telemetry:** Every turn emits live NDJSON/WebSocket step events (rendered in the `"What happened"` inspector and `/architecture` topology view) plus OpenTelemetry spans exported to Arize Phoenix.

---

## 3. Functional Scope Boundaries

### 3.1 In-Scope Capabilities (Must-Haves)

| Domain | In-Scope Requirements |
| :--- | :--- |
| **1. Authentication & Session Context** | • Authenticate against PostgreSQL `users` (`email` + `password`).<br>• Hydrate `user_id`, `full_name`, `is_premium_customer`, and `total_items_purchased`.<br>• Render tier-aware greeting (CLI prints item count for Premium; Web UI renders `premium` badge).<br>• Idempotent session reset on re-login; flush transcript to Mem0 once on logout, CLI exit, or browser tab close (`sendBeacon`). |
| **2. Multi-Layer Security Guardrails** | • **Layer 1 Sanitizer:** `MAX_INPUT_LENGTH = 300` and whitelist character filtering.<br>• **Layer 2 A2A Judge (`:10002`):** Pre-processing (URL decode + leetspeak normalization) + 100+ regex threat patterns + Gemini Judge verdict (`BLOCKED` halts turn).<br>• **Layer 2b CLI Topical Guardrail:** Structured JSON safety/on-topic check (`safe` \| `unsafe`).<br>• **Layer 3 A2A Masker (`:10003`):** Self-contained 16-PII redaction + Gemini Masker (zero `GOOGLE_CLOUD_PROJECT` dependency). |
| **3. Order Inquiry & Audit-Only Mutations** | • Normalize natural-language order references (*"Order #3"* → `3`).<br>• Read order details via `get-order-status` and history via `find-customer-orders`.<br>• Enforce strict tenant isolation and neutral anti-enumeration responses for other customers' orders.<br>• Enforce **Read → Confirm → `action-log`** for cancellations, returns, status changes, and address/profile updates; never invoke `update-order-status`. |
| **4. Cascade Voice Engine (`/voice/ws`)** | • Browser `16 kHz` mono PCM capture with energy VAD (`VAD_RMS = 0.02`), `3`-frame pre-roll, and `1500 ms` silence endpointing.<br>• Server-side multi-burst accumulation (`partial_transcript` + `1500 ms` settle timer).<br>• Echo-resistant barge-in (`400 ms` playback grace, `BARGE_RMS = 0.05`) and Hold/Resume toggle.<br>• Buffered masked TTS (`MASK=true`) and low-latency sentence-streaming TTS (`MASK=false` & `AGENT_RESPONSE_STREAM=true`). |
| **5. Glass-Box UI, Observability & Multi-Service Cloud Readiness** | • Web Chat + Voice UI (`/`), `"What happened"` inspector (with highlighted SQL & result tables), and live `/architecture` SVG view via `BroadcastChannel`.<br>• OpenTelemetry / OpenInference traces to Arize Phoenix (`:6006`) + per-stage voice `timing` and USD `cost` events.<br>• Deployable as 5–6 independent services locally (`./run.sh`) and on **Railway** (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`). |

### 3.2 Out-of-Scope (Non-Goals)
- Live payment processing, credit card charging, or automated refund disbursement.
- PSTN / SIP call-center trunk integration (scope is browser Web Audio / WebSocket and CLI).
- Direct autonomous mutations (`UPDATE` / `DELETE`) on `customer_orders` or `users`.
- External GCP project/IAM setup (`GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` are eliminated in favor of self-contained PII masking + `GOOGLE_API_KEY`).
