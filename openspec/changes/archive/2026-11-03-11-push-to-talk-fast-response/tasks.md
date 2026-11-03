# Tasks: `11-push-to-talk-fast-response`

Push-to-Talk (hold/tap & release or hold `Tab`) with `0 ms` silence/settle delay, 1.0s tail hangover, fast `LiveUtterance.flush()` drain, selective `search_memory` prompt, clause-level TTS chunking, and parallel guardrails to deliver a 3–5 second spoken response.

## 1. Live Input Transcription & Audio Streaming

- [x] 1.1 Add an utterance session in `src/voice/stt.py` that opens `VOICE_STT_LIVE_MODEL` (`gemini-3.1-flash-live-preview`), forwards 16 kHz PCM in order, yields input-transcription text, and keeps helper functions (`transcribe()`, `pcm16_to_wav`, and `_clean`). Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "live_session or wav or clean"`.
- [x] 1.2 On `/voice/ws`, forward binary frames into the open utterance session and emit `partial_transcript` as text arrives. `{"type":"utterance_end"}` appends the transcript and starts the settle timer without running a second full-clip transcription. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "settle or burst or interrupt or live_socket"`.
- [x] 1.3 In `src/voice/ui.js`, send each PCM frame on the socket during speech and send `{"type":"utterance_end"}` after silence, displaying real-time interim words in the `partial_transcript` bubble. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "ui_streams_frames"`.
- [x] 1.4 Calculate speech cost based on usage metadata or forwarded PCM duration with `VOICE_PRICE_STT_IN`. Document `VOICE_STT_LIVE_MODEL` in `.env.example`. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "live_cost"`.
- [x] 1.5 Keep `PHOENIX_ENABLE_AUTH` set to false on the phoenix service in `compose.yaml` so the local UI opens without login. Verify with `.venv/bin/pytest tests/unit/test_db_and_mcp.py -k "phoenix_auth or compose_publishes"`.

## 2. Persistent Live Session, Sentence Masking & Early Barge-In

- [x] 2.1 Add `flush` on the Live utterance in `src/voice/stt.py` to drain the transcript while keeping the connection open across multiple phrases until closed. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "live_session or same_connection"`.
- [x] 2.2 Drop PCM in `on_audio` while a voice turn is running, reconnect dead sessions, and barge in on energy `>= 0.12`. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "during_turn or interrupt or barge"`.
- [x] 2.3 In voice Explain mode, mask each finished sentence and queue it for TTS before the rest of the reply is written. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "explain or quick or stream_enabled"`.
- [x] 2.4 Evaluate prompts locally with `evaluate_prompt` before calling the A2A Security Judge. Verify with `.venv/bin/pytest tests/unit/test_demo_mode.py tests/unit/test_voice.py -k "judge or explain or quick"`.

## 3. Browser Push-to-Talk, Immediate Commit & 1.0s Tail Hangover

- [x] 3.1 In `src/voice/ui.js`, update `endUtterance(commit)` so `endUtterance(true)` sends `{"type":"utterance_end","commit":true}`. Add Push-to-Talk handlers for holding/releasing `#mic` and holding/releasing `Tab`. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "ui_streams or ptt"`.
- [x] 3.2 Hide the separate `#hold` (Mute/Hold) button so only the single `#mic` Push-to-Talk button is shown. Interrupt any in-progress thinking or speaking turn as soon as `#mic` or `Tab` is pushed. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "ui_streams or ptt or barge"`.
- [x] 3.3 Clear `pending` when answer generation starts so interrupting during thinking combines questions while interrupting during speaking starts a fresh question. Send `{"type":"turn_end","reason":"empty"}` on empty flushes. Verify with `.venv/bin/pytest tests/unit/test_voice.py -q`.
- [x] 3.4 In `src/voice/ui.js`, add a fixed `1000 ms` post-release tail window (`PTT_RELEASE_TAIL_MS = 1000`) in `releasePtt()` so releasing `#mic` or `Tab` immediately removes `.live` on the button while continuing to stream audio frames for `1.0 s` before setting `pttPaused = true` and calling `endUtterance(true)`. Allow `200 ms` post-`audio_stream_end` settle in `LiveUtterance.flush()`. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "ptt"`.

## 4. Immediate Commit, Clause-Level TTS & Fast STT Drain

- [x] 4.1 In `src/voice/router.py`, update `on_utterance_end(commit: bool = False)` so `{"type":"utterance_end","commit":true}` cancels any pending settle timer and starts `run_agent` immediately (`0 ms` settle), while hands-free `{"type":"utterance_end"}` keeps the `1500 ms` / `400 ms` settle window. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "commit or settle or two_bursts"`.
- [x] 4.2 In `src/voice/router.py`, extend `_take_complete(buf)` to split on clause/line breaks (`[:;]\s` or `\n` when prefix is >= 24 chars) in addition to `.!?…` so lists start TTS early. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "take_complete or explain or quick"`.
- [x] 4.3 Update `LiveUtterance.flush()` in `src/voice/stt.py` so zero-byte flushes return immediately (capped at `250 ms`) and active flushes exit as soon as `turn_complete` or quiet settle arrives. Verify with `.venv/bin/pytest tests/unit/test_voice.py -k "live_session or empty_flush"`.

## 5. Selective Memory Recall, Concise Prompt & Cached Guardrails

- [x] 5.1 In `src/core/prompts.py`, update `SQL_PROMPT_INSTRUCTION` so the agent calls `search_memory` only for past conversations and preferences, querying order tools directly for order lookups, and add a concise 1–3 sentence guideline. Verify with `.venv/bin/pytest tests/unit/test_core.py -k "prompt"`.
- [x] 5.2 Cache a module-level `_BLOCKER = SecurityBlocker()` singleton in `src/security/blocker.py` and reuse a shared `aiohttp.ClientSession` in `src/a2a/client.py`. Verify with `.venv/bin/pytest tests/unit/test_security.py tests/evals/test_security_eval.py -q`.
- [x] 5.3 Add configurable `Judge` (`#toggleJudge`) and `Masker` (`#toggleMask`) toggles in `src/static/index.html`, `src/voice/ui.js`, `src/voice/router.py`, and `src/api/web.py` for both Explain and Quick modes. Verify with `.venv/bin/pytest tests/unit/test_demo_mode.py tests/unit/test_voice.py -q`.
- [x] 5.4 Run `A2A Security Judge` in parallel with `Support Agent` execution (`asyncio.create_task`, cancelling the agent if blocked) in `src/api/web.py`, set `thinking_budget=0` on `LlmAgent` in `src/api/web.py` and `src/agents/judge_agent.py`, expand `_NAME_STOP` in `src/security/masker.py`, and tighten post-release `LiveUtterance.flush()` drain. Verify with `.venv/bin/pytest tests/unit tests/evals -q`.
- [x] 5.5 In `src/voice/ui.js`, `src/voice/router.py`, `src/api/web.py`, and `src/static/index.html`, pass `judge_if_flagged=False` on voice turns when `Judge: ON` so `A2A Security Judge` runs and appears in the inspector on every voice turn when enabled, ensure `ensureNode()` is called on `key === "stt"`, reset `live_started` per utterance, set `Cache-Control: no-store` on UI assets, and preserve chronological step order in `addRow()`. Verify with `.venv/bin/pytest tests/unit/test_voice.py tests/unit/test_demo_mode.py -q`.

## Workflow follow-up

- Apply this change only after the user reviews the artifacts and asks to apply it.
- Archive this change only after apply is green and the user asks.
- Do not commit or push until the user asks.
- Do not start `08-railway-deploy` from this change.

