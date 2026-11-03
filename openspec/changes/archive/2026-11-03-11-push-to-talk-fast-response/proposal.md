# Proposal: Push-to-Talk & Fast Voice Response (`11-push-to-talk-fast-response`)

## Why

In the initial cascade voice implementation, a spoken turn suffered from compounded latency, taking 7 to 12+ seconds from when the shopper stopped speaking until audio played:
1. **Silence Timers & One-Shot Transcription:** The browser waited `1500 ms` of silence (`END_SILENCE_MS`) before uploading the entire audio clip, and the server waited another `1500 ms` (`_SETTLE_MS`) before calling the pipeline. Furthermore, each turn opened and closed an STT session, adding 2+ seconds for full-clip transcription.
2. **Synchronous Guardrail Overhead:** A 6-second A2A Security Judge LLM call blocked the pipeline on every turn, and the Data Masker waited for the entire response to complete before any sentence could be spoken.
3. **Eager Memory Recall:** `SQL_PROMPT_INSTRUCTION` forced a synchronous Mem0 Cloud `search_memory` round-trip before looking up simple order statuses.
4. **Clipped Words on Release:** When shoppers used push-to-talk, releasing the button immediately cut off the audio stream, clipping their final spoken word.

Shoppers need a responsive, walkie-talkie style Push-to-Talk experience (hold `#mic` or `Tab`, speak, and release) that captures their full speech with a tail hangover, commits with zero settle delay (`0 ms`), streams clauses to TTS concurrently, and delivers answers in 3 to 5 seconds.

## What Changes

- **Live STT Streaming & Persistent Session:** Stream 16 kHz PCM frames from the browser to Gemini Live (`gemini-3.1-flash-live-preview`) as speech happens, displaying real-time interim words. Keep one Live transcription session open while the microphone is active, and cap empty flush drain within `250 ms`.
- **Push-to-Talk Control & Zero Settle Commit:** Provide a single `#mic` button and `Tab` hotkey (removing the separate Hold/Mute button). Releasing `#mic` or `Tab` sends `{"type":"utterance_end","commit":true}`, bypassing the `1500 ms` / `400 ms` settle timers and triggering `run_agent` immediately (`0 ms` settle). Standard hands-free `utterance_end` retains the settle window.
- **Fixed 1.0s Post-Release Tail Capture:** Releasing `#mic` or `Tab` immediately removes the `.live` visual highlight on the button so it never looks stuck on, while continuing to stream audio frames for a fixed `1.0 s` tail window (`PTT_RELEASE_TAIL_MS = 1000`) before committing. This completely eliminates last-word clipping.
- **Smart Interrupt:** Pushing `#mic` or `Tab` while the agent is still thinking combines the new speech with the pending question; pushing while the agent is speaking stops audio playback, keeps the previous answer readable in the chat, and answers the new speech as the next question.
- **Clause-Level TTS Streaming:** Extend `_take_complete` in `src/voice/router.py` to chunk on colons, semicolons, and newlines (`[:;\n]`) once a readable phrase length is reached, speaking introductory sentences and list headers before the full answer completes.
- **Selective Memory Recall & Concise Prompt:** Direct the agent in `SQL_PROMPT_INSTRUCTION` to call `search_memory` only for preferences and conversational history, querying order tools directly for order questions with 1–3 sentence concise replies.
- **Cached Guardrails & Shared HTTP Client:** Cache a singleton `SecurityBlocker` instance and reuse a shared `aiohttp.ClientSession` across sentence masking requests.
- **Header Guardrail Toggles & Parallel A2A Judge:** Provide `#toggleJudge` and `#toggleMask` toggles in the web header for both Explain and Quick modes. Run the A2A Security Judge concurrently with the Support Agent, cancelling the agent immediately if blocked. Set `thinking_budget=0` on Gemini 2.5 Flash agents.
- **Chronological Inspector Ordering:** Ensure the "What happened" panel always displays steps in true chronological order: `Speech to text` -> `Sanitizer` -> `Security Judge` -> `Gemini + MCP Tools` -> `Data Masker` -> `Text to speech`.
- **Local Phoenix No-Auth:** Run the local Phoenix service with `PHOENIX_ENABLE_AUTH: "false"` so telemetry is immediately accessible without a login prompt.

## Capabilities

### New Capabilities

- `push-to-talk-control`: Single `#mic` Push-to-Talk button and `Tab` key with immediate visual release, 1.0s audio tail hangover, and `commit: true` zero-latency server dispatch.

### Modified Capabilities

- `cascade-voice-engine`: Continuous PCM streaming to Gemini Live, persistent session, clause-level TTS streaming, concurrent sentence masking, and smart thinking/speaking interruption.
- `auth-memory-telemetry`: Selective Mem0 recall and concise prompt guidelines for low-latency voice responses.
- `ops-and-deployment`: Local Phoenix service runs without authentication.

## Impact

- `src/voice/ui.js`, `src/voice/router.py`, `src/voice/stt.py`, `src/voice/cost.py`
- `src/static/index.html`
- `src/core/prompts.py`
- `src/security/blocker.py`, `src/security/masker.py`, `src/a2a/client.py`, `src/agents/judge_agent.py`, `src/api/web.py`
- `compose.yaml`, `.env.example`
- `tests/unit/test_voice.py`, `tests/unit/test_demo_mode.py`, `tests/unit/test_core.py`, `tests/unit/test_security.py`, `tests/unit/test_db_and_mcp.py`

## Out of Scope

- Railway deployment (`08-railway-deploy`)
- Replacing `gemini-3.8-flash-tts` or `gemini-3.1-flash-live-preview`
- Removing hands-free VAD mode support

