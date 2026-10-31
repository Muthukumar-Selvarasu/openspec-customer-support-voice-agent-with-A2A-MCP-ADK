# Proposal: Cascade Voice Engine (`05-cascade-voice-engine`)

## Why

The customer-facing spoken channel is STT → (later) text pipeline → TTS over WebSocket `/voice/ws`. PoC already proved multi-burst accumulate-and-combine (`1500 ms` settle) and barge-in. This slice copies those modules into `src/voice/` and unit-tests them without mounting the full shopper FastAPI app.

`router.py` already receives the text pipeline by dependency injection, so Group 5 does not need Group 6's `web.py`.

## What Changes

- Add `src/voice/{stt.py, tts.py, cost.py, router.py, ui.js}` with imports rewritten to `src.voice` / `src.core.telemetry`.
- Keep `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`.
- Do not warn at startup that masking needs an extra cloud project (Group 3 made masking a local function).
- Preserve `1500 ms` settle, barge-in `interrupt`, PCM framing, and cost accounting.
- Keep `make_voice_router(...)` injectable; monkeypatch `_SETTLE_MS` in tests.

## Capabilities

### New Capabilities
- `cascade-voice-engine`: Browser WebSocket voice, STT/TTS, settle/barge-in, streaming interlock, and per-turn cost.

### Modified Capabilities

## Impact

- `src/voice/{__init__.py, stt.py, tts.py, cost.py, router.py, ui.js}`
- `tests/unit/test_voice.py`

## Channels

- **In scope:** Voice WebSocket (`/voice/ws`) as a FastAPI router
- **Out of scope:** Web Chat HTTP routes, Terminal CLI, A2A process lifecycle

## Out of Scope

- `src/api/web.py` shopper session/chat (Group 6 mounts `make_voice_router`)
- Live Gemini STT/TTS in unit tests (frame/header/math tests; live calls skipped without `GOOGLE_API_KEY`)
