# Design: Demo Response Mode

## Context

See `proposal.md` for why. The shopper page already renders every NDJSON and WebSocket event in an open "What happened" panel (`src/static/index.html`) and forwards the same events to `/architecture` on `BroadcastChannel('cs-agent')`. `text_pipeline` in `src/api/web.py` always calls the A2A Judge, then the support agent, then the A2A Masker when `mask` is on. Streaming is `stream=not do_mask` on `/api/chat/stream`. Voice copies that rule into `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK` and waits `_SETTLE_MS = 1500` after the last STT burst. Judge and Masker URLs stay `A2A_JUDGE_HOST` / `A2A_JUDGE_PORT` and `A2A_MASK_HOST` / `A2A_MASK_PORT`, localhost `:10002` / `:10003`. This change does not add a service.

## Goals / Non-Goals

**Goals:**

- One browser toggle selects the mode for the next typed turn and the next voice turn.
- Quick skips only the two extra model hops. Sanitizer, support agent, STT, and TTS still run.
- Explain, including a missing mode, is today's cascade, including the masking-wins interlock.

**Non-Goals:**

- A new host, port, or env default. `MASK` stays the process default for Explain.
- Reconnecting the voice socket when the toggle moves.
- A CLI control. The CLI never sends `mode`, so it stays Explain.

## Decisions

### Decision 1: Mode is a per-turn argument, not an env flag

`text_pipeline` gains `judge: bool = True` beside the existing `mask` argument. Quick calls it with `judge=False`, `mask=False`, and `stream=True`. Explain calls it with `judge=True`, `mask` from `mask_enabled()`, and `stream` from the existing interlock (`AGENT_RESPONSE_STREAM and not MASK` on voice; `not do_mask` on the chat stream).

`ChatReq` gains optional `mode`. Missing or unrecognized values mean `explain`. `POST /api/chat` and `POST /api/chat/stream` both pass it through. Voice does not read the process flags inside a Quick turn.

Alternative: flip `MASK` in `.env` and recreate the web container. Rejected. A demo cannot restart mid-conversation, and that flag is process-wide.

### Decision 2: The open voice socket learns the mode from a control frame

The header toggle writes `localStorage["cs-demo-mode"]` as `explain` or `quick`. Typed turns send `{"user_id","message","mode"}`. Voice sends `{"type":"mode","mode":"quick"|"explain"}` on the socket that is already open, including once after connect. The router stores that value on the connection. The turn that is already running keeps the mode it started with. Settle uses 400 ms when the stored mode is `quick`, otherwise 1500 ms. A small `settle_ms(mode)` helper is what tests call, so the suite does not sleep on the wall clock.

Alternative: put `mode` only on the WebSocket query string. Rejected. Changing it would drop the mic session.

### Decision 3: Quick hides the panel in the renderer, and still posts events

`renderEvent` keeps calling `archEvent`. When the saved mode is `quick`, it does not create the "What happened" panel and it leaves the bubble on one "thinking…" line until `delta` or `final`. Explain keeps today's rows. The architecture tab therefore lights only the stages that ran.

### Decision 4: Tests stub the Judge and the Masker

A unit test drives `text_pipeline` with a fake runner and records whether the Judge and Masker helpers were called. Quick must not call them and must still yield sanitizer and final. Explain must call both. A voice unit test checks `settle_ms("quick") == 400` and `settle_ms("explain") == 1500`. No live Gemini call is required for those two checks. The existing local cascade test stays on the default mode.

## Risks / Trade-offs

- **[Risk] Quick speaks or shows unmasked order details, and it does not run the injection Judge** → Mitigation: Explain is the default, the toggle is labeled, and a missing `mode` cannot select Quick. The sanitizer still rejects the blocklist.
- **[Risk] An in-flight voice turn changes mode halfway** → Mitigation: the turn captures mode when it starts. The next quiet period uses the new settle.
- **[Risk] Quick streaming and Explain buffering diverge and the interlock test breaks** → Mitigation: `STREAM_ENABLED` is unchanged. Only a turn whose mode is `quick` passes `stream=True` and `mask=False`.

## Migration Plan

No data migration. Ship the web page, `text_pipeline`, and the voice router together. Rollback is reverting this change. A running Podman web container picks the new page up on the next image rebuild. `08-railway-deploy` is untouched.

## Open Questions

None. Mode names, the storage key, and the 400 ms Quick settle are fixed by the specs.
