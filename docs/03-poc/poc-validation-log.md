# Stage 3: PoC Validation Log & Go/No-Go Decision (`poc-validation-log.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 3 — Proof of Concept (PoC) |
| **Inputs** | [`docs/03-poc/poc-plan.md`](poc-plan.md), [`docs/02-problem-metrics/eval-rubric.md`](../02-problem-metrics/eval-rubric.md) |
| **Decision** | **GO to Stage 4/5 (OpenSpec Engineering & Hardening)** — with 6 tracked engineering fixes |

---

## 1. PoC Hypothesis Validation Results

| Hypothesis | Result | Measured Evidence in PoC Sandbox | Engineering Action Required for Stage 4/5 |
| :--- | :--- | :--- | :--- |
| **HYP-01: Pre-Agent Security Gate** | **PARTIAL PASS** | • Live SQLi (`'; DROP TABLE users; --`), XSS, and command injection are blocked before reaching the core agent.<br>• `\brm\b` word boundary works: *"Yes, please confirm"* passes cleanly.<br>• **Bug Found #1:** In `blocker.py` line 316, `self._preprocess_query(query)` is called without assigning its return value, discarding URL-decode and leetspeak normalization.<br>• **Bug Found #2:** In `sanitizer.py` line 11, `ALLOWED_CHARS` strips `<`, `%`, `/`, and `;` *before* `SecurityBlocker` runs, and over-broad `select` regexes can match the English word *"select"*. | Fix `blocker.py` to evaluate both raw and preprocessed strings; refine regex word boundaries in Stage 4 OpenSpec change. |
| **HYP-02: Voice Multi-Burst & Barge-In** | **PASS** | • Client energy VAD (`16 kHz`, `2048`-sample frames) + server `1500 ms` settle timer cleanly combines multi-burst speech into a single `partial_transcript` bubble.<br>• Barge-in (`BARGE_RMS = 0.05` after `400 ms` grace) stops browser audio immediately and cancels the server task (`turn_end` with `reason: "interrupted"`). | Preserve voice turn-taking protocol unchanged during Stage 4 migration. |
| **HYP-03: Streaming TTS vs. Buffered PII Masking** | **PARTIAL PASS** | • Safety interlock (`STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`) works as designed.<br>• Streaming mode (`MASK=false`, `AGENT_RESPONSE_STREAM=true`) achieves **`1.3s – 1.8s` TTFA** after settle.<br>• **Bug Found #3:** When `GOOGLE_CLOUD_PROJECT` is unset, `masker.py` logs a warning and returns text **unmasked** while still spending ~3–5s calling the A2A Masker LLM.<br>• **Bug Found #4:** `masker.py` slices Python `str` using UTF-8 byte offsets, shifting characters whenever multibyte punctuation (`—`, `…`) is present. | Replace GCP Cloud DLP in `masker.py` with self-contained deterministic 16-PII redaction + character-safe replacement so `MASK=true` masks for real without `GOOGLE_CLOUD_PROJECT`. |
| **HYP-04: Tenant Isolation & Audit-Only Mutations** | **PARTIAL PASS** | • **Audit-Only Write:** Agent consistently reads state first, asks for confirmation, and writes to `actions_log` without calling `update-order-status`.<br>• **Bug Found #5 (Critical IDOR Leak in UI):** When `alice.jones@example.com` asks *"What is the status of order 5?"*, `get-order-status` runs `WHERE order_id = $1` (no email filter) and returns Bob Smith's row (`bob.smith@techmail.com`, `88 Tech Ave, Seattle`). Even though the LLM replies *"I can't find this order in your account"*, `web.py` streams the raw `tool_result` row to Alice's `"What happened"` browser panel! | Add tenant scoping (`customer_email`) and deterministic ADK `before_tool_callback` in Stage 4 OpenSpec so cross-tenant rows never leave PostgreSQL or reach `tool_result`. |
| **HYP-05: Glass-Box Inspector, Topology & Telemetry** | **PASS** | • `"What happened"` panel accurately renders STT, Sanitizer, A2A Judge, Gemini token counts, highlighted SQL (`<mark>$1</mark>`), formatted result tables, A2A Masker, TTS stats, and Phoenix trace deep links.<br>• `/architecture` lights up SVG nodes in real time via `BroadcastChannel('cs-agent')`. | Parameterize `PHOENIX_URL` / `PHOENIX_PUBLIC_URL` and service hosts so the exact same observability works on Railway. |

---

## 2. Channel Parity Audit (Web/Voice vs. Terminal CLI)

During PoC validation, we compared `web.py` against `agent_cli.py` and logged three channel divergences to resolve in Stage 4:

1. **Sanitized Input Drop in CLI:** `agent_cli.py` calls `validate_input(user_input)`, which sanitizes a local variable, returns `True`, and then passes the **unsanitized** `user_input` to `runner.run()`. `web.py` passes the sanitized `clean` string.
2. **Forced Lowercase in CLI:** `agent_cli.py` runs `lower_masked = masked.lower()` before printing the assistant response, stripping all proper nouns and sentence casing.
3. **Prompt Parameter Typo:** `prompts.py` instructs the agent to pass `parameters_json` to `action-log`, while `tools.yaml` defines the parameter as `parameters`.

---

## 3. Formal Stage 3 Go / No-Go Decision

- **Decision:** **GO — Proceed to Stage 4/5 (Spec-Driven Engineering with `openspec/`)**
- **Rationale:**
  1. The core **Cascade Voice & Text architecture**, **A2A JSON-RPC 2.0 microservice protocol**, **MCP Toolbox integration**, **Mem0 cross-session memory**, and **Glass-Box UI + Live Architecture SVG** are proven and highly effective.
  2. All 6 identified defects (cross-tenant `tool_result` leak, `GOOGLE_CLOUD_PROJECT` no-op masker, discarded `_preprocess_query`, CLI sanitization/lowercase drift, `parameters_json` prompt typo, and hardcoded localhost URLs) are well-bounded and ready to be fixed systematically through **OpenSpec specs and changes**.
