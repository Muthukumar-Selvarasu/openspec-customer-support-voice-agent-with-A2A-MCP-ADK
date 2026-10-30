# Client Engagement Brief (`ENGAGEMENT.md`)

## 1. Engagement Overview

| Field | Details |
| :--- | :--- |
| **Client / Domain** | E-Commerce Retail — Customer Support & Order Operations |
| **Engagement Title** | Enterprise Multi-Modal (Voice & Chat) Customer Support AI Platform |
| **Architecture Track** | Cascade Voice Architecture (`Speech-to-Text → Guardrailed Text Pipeline → Text-to-Speech`) |
| **Sibling Comparison Track** | Native Speech-to-Speech (`S2S` / Gemini Live) for Head-to-Head Benchmarking |
| **Primary Business Goal** | Automate high-volume customer order inquiries, cancellations, returns, and address updates across **real-time spoken voice**, **web chat**, and an **internal operator CLI**—while guaranteeing **zero direct database corruption**, **zero cross-customer data leakage**, and **zero unmasked PII spoken aloud**. |

---

## 2. The Customer's Problem Statement (Why the Customer Engaged Us)

The Customer operates an online retail store serving **Standard** and **Premium** tier shoppers. Their Customer Operations and InfoSec teams identified four blockers preventing them from deploying standard AI chatbots or end-to-end voice bots into production:

1. **Database & Prompt Vulnerability in Agentic Support:**
   Giving an AI agent access to the live orders database exposes the business to SQL injection, prompt jailbreaks, cross-account order snooping (Customer A asking about Customer B's order), and unauthorized live table mutations (`UPDATE` / `DELETE` on `customer_orders`).
2. **Unfiltered PII Exposure on Voice Calls:**
   In monolithic Speech-to-Speech (`S2S`) models, audio streams directly out of a black-box model. Once the voice model begins speaking a street address, email, phone number, or credit card number aloud, it cannot be redacted or unsaid. The Customer wants to evaluate a **Cascade Voice** architecture where speech is transcribed to text first, gated by security/privacy services, and only spoken after PII is scrubbed.
3. **Stateless, Repetitive Customer Experience:**
   Shoppers are frustrated by having to repeat personal preferences (e.g., *"I prefer email contact only"*) every time they call or start a new chat session, and loyal **Premium** customers are not recognized by tier.
4. **Black-Box AI Execution & Cost Opacity:**
   The Customer's engineering and security teams lack visibility into *why* an AI agent gave an answer, what exact SQL query it ran, which guardrail blocked or passed a turn, how much latency each stage added, and what each voice turn costs in tokens and USD.

---

## 3. Customer Personas & Stakeholders

| Persona | Role in the Engagement | What They Care About |
| :--- | :--- | :--- |
| **Online Shopper (Standard & Premium Tier)** | End User | Fast, natural voice or chat answers about order status and order history; easy cancellations, returns, and delivery address updates; natural voice turn-taking with barge-in (interrupting the agent mid-sentence); having preferences remembered across sessions. |
| **Customer InfoSec & Privacy Officer** | Security Sign-Off | Pre-execution blocking of SQLi/XSS/command/prompt injections; strict tenant isolation (anti-enumeration of other customers' orders); DLP redaction of 16 PII categories before audio synthesis; read-only protection on core order tables with an immutable audit log (`actions_log`). |
| **Customer AI / Platform Engineer** | Technical Evaluator & Handover Owner | Glass-box visibility into every step (STT, Sanitizer, Security Judge, SQL executed, rows returned, Data Masker, TTS), live architecture visualization, OpenTelemetry tracing, and fair head-to-head benchmarking against their parallel Speech-to-Speech (`S2S`) prototype. |

---

## 4. Scope of Work Given by the Customer

### 4.1 In-Scope Customer Workflows
The solution must support the following end-to-end workflows across **Web Chat**, **Real-Time Browser Voice**, and **Operator Terminal CLI**:

1. **Customer Authentication & Tier Recognition:**
   - Authenticate customers using their `email` and `password` against the PostgreSQL `users` table.
   - Hydrate their profile (`full_name`, `is_premium_customer`, `total_items_purchased`) and greet them personally (recognizing Premium tier status).
2. **Order Status & Order History Inquiries:**
   - Look up a specific order by numeric ID (e.g., *"Where is Order #3?"*, *"What's the status of order 4?"*).
   - Retrieve a customer's complete order history ordered from newest to oldest.
   - Present order line items (`items` JSON) in natural, conversational language rather than raw database JSON.
3. **Read-Confirm-Audit Workflow for Order Modifications:**
   - When a customer asks to **cancel an order**, **return an item**, **change an order status**, or **update their delivery address / profile**:
     1. **Read First:** Query the database to verify the current order state.
     2. **Explicit Confirmation:** Summarize the proposed change and ask the customer to confirm before taking action.
     3. **Audit-Only Write (`actions_log`):** Once confirmed, log the structured intent (`UPDATE_DELIVERY_ADDRESS`, `RETURN_ITEM`, `UPDATE_ORDER_STATUS`, `UPDATE_PROFILE_DETAILS`) into the `actions_log` table for downstream fulfillment—**never** directly mutating the `customer_orders` table.
4. **Long-Term Cross-Session Memory:**
   - Recall saved customer preferences during the conversation (via Mem0).
   - Automatically persist the conversation transcript to long-term memory when the customer signs out, closes the browser tab, or exits the CLI.
5. **Natural Cascade Voice Experience:**
   - Allow customers to speak naturally in multiple bursts (waiting `1.5 seconds` of silence before submitting the combined question).
   - Support **Barge-In** (immediately stopping agent speech if the customer starts speaking) and **Hold / Resume** microphone controls.

### 4.2 Out-of-Scope (Non-Goals for This Engagement)
- Live payment gateway charging or automated financial refund processing.
- Direct PSTN/SIP telephony trunk cutover (this engagement targets Web Audio / WebSocket voice and local side-by-side benchmarking).
- Direct autonomous `UPDATE` or `DELETE` execution on `customer_orders` or `users` by the AI agent.

---

## 5. Customer-Provided Assets & Environment Baseline

The Customer provided the following database schema, seed population, and operational constraints as the starting baseline:

### 5.1 PostgreSQL Database Schema (`toolbox_db`)
1. **`users` Table:**
   - `user_id` (`SERIAL PRIMARY KEY`), `email` (`VARCHAR(255) UNIQUE NOT NULL`), `full_name` (`VARCHAR(100)`), `is_premium_customer` (`BOOLEAN`), `total_items_purchased` (`INTEGER`), `password` (`VARCHAR(255)`).
2. **`customer_orders` Table:**
   - `order_id` (`SERIAL PRIMARY KEY`), `customer_email` (`VARCHAR(100)`), `delivery_address` (`VARCHAR(255)`), `status` (`PROCESSING` | `SHIPPED` | `DELIVERED` | `CANCELLED` | `RETURNED`), `items` (`JSONB` array of `{product, qty, price}`), `order_date` (`TIMESTAMPTZ`), `total_amount` (`DECIMAL(10,2)`).
3. **`actions_log` Table (Immutable Audit Trail):**
   - `id` (`SERIAL PRIMARY KEY`), `timestamp` (`TIMESTAMPTZ`), `user_email` (`VARCHAR(255)`), `action_type` (`VARCHAR(50)`), `parameters` (`JSONB`).

### 5.2 Customer-Provided Seed Dataset
- **10 Representative Shopper Accounts:**
  - **4 Premium Customers:** Hannah M (`hannah.m@school.edu`, 94 items), Charlie D (`charlie.d@webmail.com`, 88 items), Julia Child (`julia.child@kitchen.com`, 75 items), Evan G (`evan.g@bizcorp.com`, 56 items).
  - **6 Standard Customers:** Alice Jones (`alice.jones@example.com`, 42 items), Ian Malcolm (`ian.malcolm@chaos.com`, 31 items), Diana Prince (`diana.prince@hero.net`, 23 items), George J (`george.j@jungle.com`, 19 items), Bob Smith (`bob.smith@techmail.com`, 15 items), Fiona Shrek (`fiona.shrek@swamp.com`, 12 items).
- **17 Realistic Orders:** Spanning all 5 order lifecycle states (`DELIVERED`, `SHIPPED`, `PROCESSING`, `CANCELLED`, `RETURNED`) and timestamps ranging from 1 year ago to 30 minutes ago.

### 5.3 Legacy / Production Toolset Simulation
- The database tool catalog exposes four operations: `get-order-status`, `find-customer-orders`, `action-log`, and a restricted `update-order-status` tool.
- **Customer Mandate:** `update-order-status` must remain present in the tool catalog to mirror the Customer's legacy production database permissions, proving that the AI agent strictly obeys policy by refusing to call it and routing all confirmed changes to `action-log`.

### 5.4 Sibling S2S Benchmarking Coexistence
- This Cascade platform must share the exact same database schema, tools, and Mem0 memory store—and emit compatible WebSocket timing/cost events—as the Customer's parallel Speech-to-Speech (`advance-customer-support-agent-feature-A2A-MCP-ADK-s2s`) project so their team can run automated head-to-head benchmarks (`benchmarking_voice_agents/`).

---

## 6. Non-Negotiable Security, Privacy & Governance Rules

1. **Multi-Layer Pre-Agent Input Gate:**
   - **Layer 1 (Deterministic Sanitizer):** Enforce a 300-character limit, strip disallowed special characters, and optionally integrate with Google Cloud Model Armor.
   - **Layer 2 (Isolated A2A Security Judge):** Inspect every user input via an independent microservice before the support agent sees it, blocking 100+ attack patterns (SQLi, UNION, time-based blind SQLi, XSS, OS command injection, path traversal, Log4j, leetspeak/hex/comment obfuscation, and prompt injection).
   - **Topical & Harmful Content Guardrail (CLI):** Block off-topic discussions (politics, religion, sports, homework) and harmful/toxic content.
2. **Strict Tenant Isolation & Anti-Enumeration:**
   - The agent is bound to the logged-in user's email and must **never** query or impersonate another email.
   - If a customer asks about an `order_id` belonging to another customer (or a non-existent order), the agent must **never** confirm that the order exists or reveal who owns it; it must respond neutrally: *"I can't find this order in your account. Would you like to check the status of one of your other orders?"*
3. **Post-Agent PII Masking (DLP):**
   - Before an answer is shown or spoken (when `MASK=true`), an isolated A2A Data Masker microservice must scrub 16 PII categories (email, phone, credit card, SSN, person name, street address, IP, DOB, etc.) using Google Cloud DLP, replacing sensitive spans with length-preserving asterisks (`*`).
4. **Voice Streaming vs. Masking Safety Interlock:**
   - A response cannot be PII-masked if it is already being spoken sentence-by-sentence.
   - Therefore, when `MASK=true` (default), sentence-streaming TTS must be automatically disabled so the full text reply is masked *before* TTS synthesis begins. Low-latency sentence-streaming TTS is permitted only when `MASK=false` and `AGENT_RESPONSE_STREAM=true`.

---

## 7. Expected Deliverables & Customer Acceptance Criteria

| # | Deliverable | Customer Acceptance Criteria |
| :- | :--- | :--- |
| **1** | **Unified Cascade Support Platform** | Working Web Chat UI, Real-Time Cascade Voice UI, and Terminal CLI sharing one security-hardened agent pipeline. |
| **2** | **Isolated A2A Security Microservices** | Security Judge and Data Masker running as independent Agent-to-Agent (A2A JSON-RPC 2.0) services with `/.well-known/agent.json` discovery cards. |
| **3** | **"What Happened" Glass-Box Inspector** | Expandable live panel under every turn showing STT transcript, Sanitizer/Judge verdict, Gemini decisions & tokens, exact SQL executed with highlighted parameters, tabular rows returned, Masker status, TTS metrics, and Phoenix trace deep link. |
| **4** | **Live Interactive Architecture View** | Real-time `/architecture` SVG dashboard synchronized with the chat tab (`BroadcastChannel`) that lights up each system component (`active` / `done` / `blocked`) as a voice or text turn executes. |
| **5** | **Per-Stage Latency, Cost & Trace Telemetry** | OpenTelemetry traces exported to Arize Phoenix plus per-turn voice latency (`stt`, `judge`, `agent`, `mask`, `tts`, TTFA) and USD token cost breakdown. |
| **6** | **Automated Adversarial Security Suite** | Executable evaluation suite (`100` scenarios: `61` malicious attacks + `39` legitimate customer queries) outputting pass/fail reports to `security_test_results.json`. |
| **7** | **One-Command Turnkey Orchestration** | Single script (`./run.sh`) to provision dependencies, initialize and seed PostgreSQL, start MCP Toolbox and A2A microservices in dependency order, verify health, and launch the CLI or Web UI. |
