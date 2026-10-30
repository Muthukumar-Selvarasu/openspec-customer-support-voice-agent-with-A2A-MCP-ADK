# Stage 2: Measurable Success Criteria (`success-metrics.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 2 — Problem & Metrics |
| **Inputs** | [`docs/02-problem-metrics/problem-brief.md`](problem-brief.md), [`docs/01-discovery/discovery-report.md`](../01-discovery/discovery-report.md) |
| **Benchmark Target** | Head-to-Head Comparison with Sibling Speech-to-Speech (`S2S`) Platform |

---

## 1. Primary Success Metrics Summary

Every stage of the engagement ( Stage 3 PoC, Stage 6 QA/UAT, and Stage 7 Railway Go-Live) is evaluated against five quantitative metric pillars:

| Pillar | Metric ID | Metric Name | Target Threshold | Measurement Source |
| :--- | :--- | :--- | :--- | :--- |
| **1. Security & Guardrails** | `MET-SEC-01` | Malicious Attack Block Rate | **100% (`61 / 61` blocked)** | Automated Security Harness (`test_scenarios.json`) |
| | `MET-SEC-02` | Legitimate Query Pass Rate | **100% (`39 / 39` passed)** | Automated Security Harness (`test_scenarios.json`) |
| | `MET-SEC-03` | Cross-Tenant Order Leakage Rate | **0% (Zero cross-tenant PII in prose or `tool_result`)** | Tenant Isolation Integration Tests |
| | `MET-SEC-04` | Unauthorized Table Mutation Rate | **0 calls to `update-order-status`** | PostgreSQL `customer_orders` & `actions_log` audit |
| **2. Privacy & DLP** | `MET-PRIV-01` | PII Redaction Recall (`MASK=true`) | **100% across all 16 PII categories** | A2A Data Masker (`:10003`) Evaluation Suite |
| | `MET-PRIV-02` | Unmasked Audio Leakage (`MASK=true`) | **0 unmasked frames sent to TTS** | Voice Interlock Check (`STREAM_ENABLED == False`) |
| **3. Voice Latency** | `MET-LAT-01` | Time to First Audio (TTFA) — Streaming Mode (`MASK=false`, `AGENT_RESPONSE_STREAM=true`) | **`< 2.0 seconds` (p50) after `1500 ms` settle** | Voice WebSocket `timing.stages.tts_start` |
| | `MET-LAT-02` | Time to First Audio (TTFA) — Safe Buffered Mode (`MASK=true`) | **`< 6.0 seconds` (p50) including Judge + Agent + Masker** | Voice WebSocket `timing.stages.tts_start` |
| | `MET-LAT-03` | Barge-In Cancellation Latency | **`< 200 ms` client audio stop; immediate server task cancel** | Browser `ui.js` & Server `turn_end(reason="interrupted")` |
| **4. Cost & Observability** | `MET-OBS-01` | Per-Turn Token & USD Cost Coverage | **100% of voice turns emit `timing` & `cost` events** | `cs_agent/voice/cost.py` & WebSocket stream |
| | `MET-OBS-02` | OpenTelemetry Trace Completeness | **100% of turns (when `TELEMETRY=true`) emit root + child spans** | Arize Phoenix (`/v1/traces`) |
| **5. Functional Accuracy** | `MET-ACC-01` | Read-Confirm-Audit Workflow Compliance | **100% of mutations confirmed before `action-log` insert** | Multi-turn E2E Scenario Suite |
| | `MET-ACC-02` | Cross-Session Memory Recall | **100% recall of saved preferences in subsequent session** | Mem0 `save_memory` → `search_memory` test |

---

## 2. Voice Latency Breakdown Specification (`timing` Event)

Every completed voice turn over `/voice/ws` must emit a structured `timing` JSON frame reporting wall-clock durations and offsets (in seconds, rounded to 3 decimal places) relative to turn dispatch:

```json
{
  "type": "timing",
  "stages": {
    "stt": 0.482,
    "judge": 0.615,
    "agent_start": 0.618,
    "agent_end": 1.940,
    "mask": 0.720,
    "tts_start": 3.110,
    "tts_end": 5.420,
    "total_response": 5.420
  }
}
```

| Stage Key | Definition | Target Budget (p50) |
| :--- | :--- | :--- |
| `stt` | Cumulative duration of `gemini-3.1-flash-lite` audio transcription across bursts in the turn. | `0.35s – 0.80s` |
| `judge` | Round-trip duration of Layer 2 A2A Security Judge (`:10002`) JSON-RPC evaluation. | `0.40s – 0.90s` |
| `agent_start` → `agent_end` | Core ADK `LlmAgent` (`gemini-3.8-flash`) execution window, including MCP Toolbox SQL calls and `search_memory`. | `0.80s – 2.20s` |
| `mask` | Round-trip duration of Layer 3 A2A Data Masker (`:10003`) when `MASK=true` (omitted when `MASK=false`). | `0.40s – 1.20s` |
| `tts_start` | **Time to First Audio (TTFA):** Offset from pipeline start to the first `24 kHz` binary PCM chunk sent over WebSocket. | `< 2.0s` (Streaming)<br>`< 6.0s` (Buffered Masked) |
| `tts_end` / `total_response` | Offset when the final TTS audio chunk is transmitted to the client. | Proportional to reply length |

---

## 3. Per-Stage Token & USD Cost Accounting Model (`cost` Event)

To benchmark the **Cascade Voice** architecture fairly against the sibling **Speech-to-Speech (`S2S`)** architecture, every voice turn emits a `cost` event computed from configurable per-1M-token rates (`cost.py`):

### 3.1 Baseline Pricing Table (USD per 1,000,000 Tokens)

| Stage | Model | Env Override (`IN` / `OUT`) | Default Input Rate | Default Output Rate | Accounting Method (`measured`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **STT** (`stt`) | `gemini-3.1-flash-lite` | `VOICE_PRICE_STT_IN` / `VOICE_PRICE_STT_OUT` | `$0.30` (Audio In) | `$0.40` (Text Out) | `measured: true` (from `usage_metadata`) |
| **A2A Judge** (`judge`) | `gemini-3.8-flash` | `VOICE_PRICE_LLM_IN` / `VOICE_PRICE_LLM_OUT` | `$0.30` (Text In) | `$2.50` (Text Out) | `measured: false` (estimated at `~4 chars/token` across A2A boundary) |
| **Core Agent** (`agent`) | `gemini-3.8-flash` | `VOICE_PRICE_LLM_IN` / `VOICE_PRICE_LLM_OUT` | `$0.30` (Text In) | `$2.50` (Text Out) | `measured: true` (summed across ADK `usage_metadata` turns) |
| **A2A Masker** (`mask`) | `gemini-3.8-flash` | `VOICE_PRICE_LLM_IN` / `VOICE_PRICE_LLM_OUT` | `$0.30` (Text In) | `$2.50` (Text Out) | `measured: false` (estimated at `~4 chars/token` across A2A boundary) |
| **TTS** (`tts`) | `gemini-3.8-flash-tts` | `VOICE_PRICE_TTS_IN` / `VOICE_PRICE_TTS_OUT` | `$1.00` (Text In) | `$20.00` (Audio Out) | `measured: true` (from final streaming chunk `usage_metadata`) |

### 3.2 Cost Formula
For each active stage $s \in \{\text{stt}, \text{judge}, \text{agent}, \text{mask}, \text{tts}\}$:
$$\text{Cost}_s\ (\text{USD}) = \frac{\text{tokens\_in}_s \times \text{Price}_{\text{in}, s} + \text{tokens\_out}_s \times \text{Price}_{\text{out}, s}}{1,000,000}$$

Total turn cost is $\sum_s \text{Cost}_s$, emitted in the WebSocket `cost` frame and rendered in the `"What happened"` inspector.
