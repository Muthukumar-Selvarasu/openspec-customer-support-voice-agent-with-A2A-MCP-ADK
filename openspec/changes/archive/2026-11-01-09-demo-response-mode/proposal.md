# Proposal: Demo Response Mode (`09-demo-response-mode`)

## Why

The glass-box cascade is how testers see the agent work, and it is also why a short voice reply takes about 11 seconds. The A2A Security Judge is most of that wait, and buffered masking holds speech until the whole reply is written. Hiding the "What happened" list does not shorten the wait. Testers need a live switch between the full cascade and a faster answer, without restarting the web container or editing `MASK`.

## What Changes

- Add a header toggle, **Explain** or **Quick**, remembered in the browser. **Explain** is the default.
- Each typed turn (`POST /api/chat/stream`) and each voice turn (`/voice/ws`) sends the chosen mode. A missing mode is Explain.
- **Explain** keeps today's path: sanitizer, A2A Judge, support agent, A2A Data Masker, the open "What happened" panel, the 1500 ms voice settle, and the process-level rule that `MASK=true` disables streaming.
- **Quick** skips the A2A Judge and the A2A Data Masker for that turn only. The sanitizer still runs. The step list stays hidden. The support reply streams, and voice starts TTS on the first finished sentence. Voice settle for that turn is 400 ms.
- `MASK` and `AGENT_RESPONSE_STREAM` stay process defaults. They are not the demo switch. Explain turns still obey the masking-wins interlock.
- The architecture tab still receives the events that actually run, so a side-by-side demo can show the shorter path.
- The operator CLI stays on the full cascade. It has no toggle.

## Capabilities

### New Capabilities

### Modified Capabilities

- `web-and-cli-channels`: Chat and the glass-box inspector gain a per-turn demo mode. Explain still emits sanitizer, judge, tool, masker, and final events and shows "What happened". Quick omits judge and masker events and shows only the answer.
- `cascade-voice-engine`: A quick voice turn skips the Judge and the Masker, streams TTS, and settles after 400 ms. Explain voice turns keep the 1500 ms settle and the masking-wins interlock.

## Impact

- `src/api/web.py` (`text_pipeline`, `POST /api/chat`, `POST /api/chat/stream`)
- `src/voice/router.py`
- `src/static/index.html` (header toggle; voice script sends the same mode)
- `tests/integration/test_api_and_tenant.py` and `tests/integration/test_local_cascade.py`, plus a unit test that Quick skips the Judge without a live model

## Out of Scope

- Railway deploy (`08-railway-deploy`)
- Changing the process default of `MASK` or removing Explain mode
- A CLI toggle
- Skipping speech-to-text, the sanitizer, the support model, or TTS
