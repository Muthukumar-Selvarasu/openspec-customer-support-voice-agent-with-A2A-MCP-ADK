# Design: Push-to-Talk & Fast Voice Response (`11-push-to-talk-fast-response`)

## Architecture Overview

This change optimizes the end-to-end voice pipeline from browser audio capture to speech playback, reducing latency to 3–5 seconds while introducing a reliable Push-to-Talk interaction.

```
Browser (UI)                    Server (/voice/ws)                     Background / A2A
  [ Hold #mic / Tab ] --------> [ 16 kHz PCM stream ] --------------> [ Gemini Live STT Session ]
         |                              |                                      |
  [ Release #mic ]                      |                               (words stream back)
         |                              |                                      |
  (1.0s Tail Hangover) -------> [ final speech frames ]                        v
         |                              |                              [ Partial Transcript ]
  (Tail Ends: commit: true) --> [ flush STT drain (<=250ms) ]
                                        |
                             [ run_agent immediately (0ms) ]
                                        |
                        +---------------+---------------+
                        |                               |
                        v                               v
             [ Sanitizer (local) ]             [ Support Agent (ADK) ]
                        |                         thinking_budget=0
                        v                               |
           [ A2A Security Judge (async) ]               v
              (:10002 parallel task)             [ MCP Tools / Postgres ]
                        |                               |
                        +---------------+---------------+
                                        | (delta tokens)
                                        v
                            [ _take_complete ([:;\n]) ]
                                        |
                                        v
                             [ Masker (sentence level) ]
                                        |
                                        v
                             [ Gemini Flash TTS stream ]
                                        |
  [ Audio Playback ] <--------- [ 24 kHz PCM chunks ]
```

## Key Technical Decisions

### 1. Push-to-Talk & 1.0s Post-Release Tail Hangover (`src/voice/ui.js`)
- Holding down `#mic` (`mousedown`/`touchstart`) or holding `Tab` activates `pttActive = true` and streams 16 kHz PCM frames continuously, bypassing `END_SILENCE_MS`.
- When `#mic` or `Tab` is released (`releasePtt()`), the button immediately turns off its active `.live` CSS class and displays `🎙 transcribing…` so the user knows release was acknowledged.
- Under the hood, a fixed `1.0 s` tail timer (`PTT_RELEASE_TAIL_MS = 1000`, `pttTailTimer`) keeps `onFrame` streaming trailing microphone frames. When the timer fires, `finishPttRelease()` sets `pttPaused = true` and sends `{"type":"utterance_end","commit":true}`.
- If the user taps or holds `#mic` again during the `1.0 s` tail, `clearPttTail()` cancels the timer and seamlessly continues the utterance.

### 2. Immediate Commit & Smart Interruption (`src/voice/router.py`)
- When `{"type":"utterance_end","commit":true}` arrives, the router calls `commit_now()`, bypassing the `1500 ms` Explain settle and `400 ms` Quick settle windows to start `run_agent(query, connection_mode)` at `0 ms`. Standard `utterance_end` without `commit: true` retains existing settle timers.
- If `#mic` is pressed while the agent is still thinking (before `delta`), `pending` is preserved so the new utterance is appended to the current question, answering them together.
- If `#mic` is pressed while the agent is speaking, audio playback stops immediately, the existing reply remains visible in the chat bubble, and the new speech is processed as a fresh question.

### 3. Fast STT Flush Drain (`src/voice/stt.py`)
- One `LiveUtterance` connection stays open across turns while the mic is active.
- On `flush()`, empty flushes exit immediately (`<= 250 ms`). On active flushes, `audio_stream_end=True` is sent and the drain loop exits as soon as `turn_complete` is received or after a `200 ms` quiet-settle window, capping active drain at `0.7 s`.

### 4. Clause-Level TTS Chunking (`src/voice/router.py`)
- `_take_complete(buf)` splits on colons, semicolons, and newlines (`[:;\n]`) when the accumulated buffer is at least 24 characters long, in addition to sentence endings (`.!?…`). This allows bullet lists and introductory clauses to start TTS synthesis immediately.

### 5. Selective Memory Recall & Concise Voice Prompt (`src/core/prompts.py`)
- `SQL_PROMPT_INSTRUCTION` directs the agent to call `search_memory` only for preferences and historical conversation context. Direct order questions invoke `get-order-status` or `find-customer-orders` immediately.
- Added a 1–3 sentence response guideline to maintain short, natural spoken responses.

### 6. Concurrent A2A Security Judge & Header Toggles (`src/api/web.py`, `src/static/index.html`)
- Header `#toggleJudge` and `#toggleMask` toggles allow users to turn `A2A Security Judge` and `A2A Data Masker` ON or OFF in both Explain and Quick modes.
- In `text_pipeline`, when `judge` is active, the A2A Security Judge runs concurrently (`asyncio.create_task`) with the Support Agent. If the Judge returns `BLOCKED`, the agent task is cancelled immediately.
- `thinking_budget=0` is configured on `LlmAgent` in `src/api/web.py` and `src/agents/judge_agent.py`.
- Step ordering in `addRow()` places `stt` at the top and `tts` at the bottom, matching the true pipeline sequence.

### 7. Local Phoenix Configuration (`compose.yaml`)
- `PHOENIX_ENABLE_AUTH: "false"` is configured on the local `phoenix` service so telemetry is accessible without authentication.

