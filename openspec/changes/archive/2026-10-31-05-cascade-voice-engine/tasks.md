# Tasks: `05-cascade-voice-engine`

Implement the voice cascade under `src/voice/` with `src.voice.*` and `src.core.telemetry` imports. Keep STT default `gemini-3.1-flash-lite` and TTS default `gemini-3.8-flash-tts`. Skip live Gemini unless `GOOGLE_API_KEY` is set.

## 1. Voice helpers

- [x] 1.1 Implement `src/voice/stt.py`, `src/voice/tts.py`, `src/voice/cost.py`, and `src/voice/ui.js`; add unit tests for `pcm16_to_wav` (output starts with `RIFF`/`WAVE`), `_clean`, sentence chunking, `cost.usd`, `estimate_tokens`, and `usage_tokens`; verify with `pytest tests/unit/test_voice.py -k "wav or clean or cost or sentence"`

## 2. Voice router

- [x] 2.1 Implement `src/voice/router.py` WebSocket `/voice/ws` with `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`; inject the text pipeline via `make_voice_router(runners=..., pipeline=..., ...)` so tests do not import `src.api.web`; make `_SETTLE_MS` monkeypatchable; emit `turn_end` with `reason: "interrupted"` on client `interrupt`; do not warn that masking needs an extra cloud project; keep the MASK vs stream conflict warning; add TestClient websocket tests for two-burst combine (`1500 ms` settle) and barge-in; verify with `pytest tests/unit/test_voice.py`
