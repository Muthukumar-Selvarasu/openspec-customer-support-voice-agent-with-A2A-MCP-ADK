# Design: Cascade Voice Engine

## Context

See `proposal.md`. Depends on `02-core-auth-memory-telemetry` (`telemetry.py`) and injects the text pipeline at mount time (Group 6). Implement the voice cascade under `src/voice/` importing `src.core.telemetry`.

## Goals / Non-Goals

**Goals:**
- Preserve PoC voice protocol (settle, barge-in, glass-box events).
- Unit-test framing, cleanup, interlock, and cost without live audio.

**Non-Goals:**
- Shopper login/session (Group 6).
- Changing STT (`gemini-3.1-flash-lite`) or TTS (`gemini-3.8-flash-tts`) models.

## Decisions

### Decision 1: Inject the pipeline
Keep `make_voice_router(runners=..., pipeline=..., ...)` so Group 5 tests can pass a fake async generator and do not import `src.api.web`.

### Decision 2: Masking is local
Voice startup MUST NOT warn that masking needs an extra cloud project. Keep the MASK vs stream conflict warning. `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK`.

### Decision 3: TestClient websocket for protocol tests
Use FastAPI `TestClient.websocket_connect` with a stub pipeline for settle/interrupt. Skip live STT/TTS unless `GOOGLE_API_KEY` is set. Monkeypatch `_SETTLE_MS` so settle tests are not wall-clock flaky.

### Decision 4: Package is `src.voice`
Imports are `from src.voice...` and `from src.core.telemetry import`. `ui.js` lives beside `router.py` so `Path(__file__).parent / "ui.js"` works.

## Risks / Trade-offs

- **[Risk] Settle/interrupt tests are timing-sensitive** → Mitigation: inject a shorter settle in tests or monkeypatch `_SETTLE_MS`.
