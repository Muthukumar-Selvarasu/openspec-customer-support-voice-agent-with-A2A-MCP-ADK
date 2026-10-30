# Stage 3: Customer PoC Demo Feedback & Notes (`poc-demo-notes.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 3 — Proof of Concept (PoC) |
| **Attendees** | Client Operations Lead, Client InfoSec Officer, Client AI Platform Lead, FDE Team |

---

## 1. Live Demo Walkthrough Summary

The FDE team demonstrated the end-to-end PoC across **Web Chat (`/`)**, **Live Architecture View (`/architecture`)**, **Real-Time Browser Voice (`/voice/ws`)**, and **Arize Phoenix (`:6006`)**:

1. **Quick Demo Sign-In & Starter Chips:**
   - Signed in as `alice.jones@example.com` and `julia.child@kitchen.com` (showing the `premium` customer badge).
   - Used the starter prompt chips (*"Where is my last order?"*, *"Show me all my orders"*, *"Cancel my processing order"*, *"I want to return order 1"*, *"'; DROP TABLE users; --"*).
2. **Side-by-Side Live Architecture Visualization:**
   - Placed `/` and `/architecture` side-by-side. Stakeholders watched the SVG nodes (`User → STT → Sanitizer → Security Judge → ADK Support Agent → MCP Toolbox → PostgreSQL / Mem0 → Data Masker → TTS`) glow cyan (`active`), transition to green (`done`), and flash red (`blocked`) when the SQL injection chip was clicked.
3. **"What Happened" Glass-Box Inspector:**
   - Expanded the step inspector under each assistant turn to show the exact MCP call path, substituted SQL parameters (`$1`), formatted HTML order table with status pills (`DELIVERED`, `SHIPPED`, `PROCESSING`), per-stage latency (`ms`), token counts, USD cost, and the **"View trace in Phoenix ↗"** deep link.
4. **Cascade Voice & Barge-In:**
   - Demonstrated multi-burst spoken queries with natural mid-sentence pauses (`1500 ms` settle window), Hold/Resume mic control, and mid-sentence barge-in interruption.

---

## 2. Stakeholder Feedback Captured

### 2.1 What the Customer Loved (Keep Unchanged)
- **"What Happened" SQL & Step Inspector:** Both the Engineering and InfoSec leads highlighted the inline SQL viewer + tabular result renderer as a standout feature that completely solves their "black-box AI" concern.
- **Live `/architecture` BroadcastChannel Sync:** Operations leadership requested keeping `/architecture` in the final production app for executive demos and operator training.
- **Accumulate-and-Combine Voice Turn Model:** Callers did not feel rushed when pausing to look up an order number; the growing `partial_transcript` bubble made voice interaction intuitive.
- **Read-Confirm-Audit Pattern:** Operations confirmed that requiring explicit user confirmation before writing to `actions_log` matches their fulfillment SOP.

### 2.2 Customer Requests & Action Items for Stage 4–7 Engineering
1. **Fix the Cross-Tenant `tool_result` Exposure in the Inspector (InfoSec P0):**
   - InfoSec noted that while the LLM refused to tell Alice about Bob's Order `#5`, expanding `"What happened"` showed Bob's row returned from `get-order-status`.
   - **Action Agreed:** Scope `get-order-status` by `customer_email` and enforce session identity in the ADK tool callback so `0 rows` are returned when querying another customer's order ID.
2. **Make PII Masking Work Without GCP Setup (InfoSec & Platform P0):**
   - The Customer is deploying on **Railway** and does not want to maintain a separate Google Cloud Project or Service Account JSON (`GOOGLE_CLOUD_PROJECT`) just for DLP masking.
   - **Action Agreed:** Replace `google-cloud-dlp` in `masker.py` with self-contained 16-PII redaction + Gemini Masker verification so `MASK=true` masks street addresses, emails, phone numbers, and credit cards out-of-the-box using only `GOOGLE_API_KEY`.
3. **Deploy as Independent Services on Railway (Platform Lead P1):**
   - Platform Engineering confirmed they want the multi-service topology (`postgres`, `mcp-toolbox`, `a2a-judge`, `a2a-masker`, `web-voice-app`, `phoenix`) deployed to Railway via environment-driven service URLs while keeping `./run.sh` working for local benchmarking.
