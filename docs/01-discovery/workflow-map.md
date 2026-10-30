# Stage 1: Workflow & Process Map (`workflow-map.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 1 — Discovery & Scoping |
| **Channels Covered** | Web Chat (`POST /api/chat/stream`), Cascade Voice (`WS /voice/ws`), Terminal CLI (`agent_cli.py`) |

---

## 1. End-to-End Multi-Service Cascade Architecture Flow

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

---

## 2. Core Workflow Sequence Maps

### Workflow 1: Authentication, Context Hydration & Session Lifecycle
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

---

### Workflow 2: Order Status & Order History Lookup
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

---

### Workflow 3: Read-Confirm-Audit Workflow for Order Mutations
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

---

### Workflow 4: Cascade Voice Turn-Taking & Barge-In (`/voice/ws`)
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
