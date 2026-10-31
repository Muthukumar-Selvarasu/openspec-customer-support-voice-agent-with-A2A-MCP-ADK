# Tasks: `09-demo-response-mode`

Per-turn Explain / Quick demo switch. Explain stays the full cascade. Quick skips the A2A Judge and the A2A Data Masker for that turn. Do not change `08-railway-deploy`. Do not commit until asked.

## 1. Per-turn pipeline mode

- [x] 1.1 Add `judge` beside `mask` on `text_pipeline`, and optional `mode` on `ChatReq` for `POST /api/chat` and `POST /api/chat/stream`. Missing or unrecognized mode is `explain`. Quick calls the pipeline with `judge=False`, `mask=False`, and `stream=True`. Explain keeps `judge=True`, `mask` from `mask_enabled()`, and the current stream interlock. Judge and Masker URLs stay `A2A_JUDGE_*` and `A2A_MASK_*` with localhost `:10002` / `:10003`. Verify with `.venv/bin/pytest tests/unit/test_demo_mode.py -k pipeline`: Quick yields sanitizer and final and does not call the Judge or the Masker; Explain calls both. No live Gemini call.

## 2. Voice mode and settle

- [x] 2.1 Add `settle_ms(mode)` and accept `{"type":"mode","mode":"quick"|"explain"}` on the open `/voice/ws` socket. A Quick turn uses 400 ms settle, skips Judge and Masker, and starts TTS on the first finished sentence. An Explain turn, and a socket that has not sent a mode, keeps 1500 ms settle, the Judge, the Masker, and `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`. The in-flight turn keeps the mode it started with. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "settle_ms or demo_mode or stream_enabled"`.

## 3. Shopper toggle

- [x] 3.1 Add an Explain / Quick control in the header of `src/static/index.html`. Default is Explain. Persist the choice in `localStorage["cs-demo-mode"]`. Send `mode` on `POST /api/chat/stream` and send `{"type":"mode"}` on the voice socket after connect and whenever the toggle changes. In Quick, do not render the "What happened" panel and keep the bubble on one "thinking…" line until `delta` or `final`. Still forward events with `archEvent`. Verify with `.venv/bin/pytest tests/unit/test_demo_mode.py -k toggle`.

## 4. Explain cascade still matches the spec

- [x] 4.1 With no `mode` sent, a live text turn still includes sanitizer, judge, and masker before final. If `tests/integration/test_local_cascade.py` requires the fourth stage event to be `mask`, relax that assertion so repeated `agent` events are allowed and judge still precedes mask. Skip only when `GOOGLE_API_KEY` or `MEM0_API_KEY` is unset, and say which. Verify with `.venv/bin/pytest tests/integration/test_local_cascade.py -k text`.

## Workflow follow-up

- Archive this change only after apply is green and the user asks.
- Do not commit or push until the user asks.
