# Design

## Context

See `proposal.md` for full motivation and drift citations. Key runtime findings in the current code:
- `src/voice/router.py` hardcodes `turn_stream = True` and incrementally masks/speaks sentences via `absorb_masked()` / `speak_masked()`, which is verified by `test_demo_mode_explain_speaks_each_masked_sentence`. However:
  - `display` holds the unmasked text and line 452 (`answer_text = display.strip()`) persists unmasked text to Mem0; `src/api/web.py` line 641 writes unmasked `final_text` to `voice.turn` span `output.value`.
  - `mask_t0` is set *after* `await mask_text(text)` completes, emitting `"ms": 1` and `timing["mask"] = 0.0`, with no `security.a2a_mask` span and zero `mask_tok`.
  - `send_cost()` line 185 hardcodes `"measured": True` on `stt` even when `cost.stt_charge()` estimated tokens from PCM bytes; `_CLAUSE_END` (`\n+`) can split a multi-line address like `"123 Market St,\nSpringfield"` across separate `mask_text()` calls.
  - `make_voice_router(..., mask_enabled=mask_enabled())` freezes `MASK` at import time.
- `src/static/index.html` line 271 (`cs:login` → `syncGuardrails()`) and `src/voice/ui.js` line 514 (`sendGuardrails()`) automatically store `judge: true, mask: true` in `_guardrails[user_id]` / `voice_ws`, overriding Quick mode.
- `src/voice/ui.js` sets `window.csVoiceOn = true` on `startVoice({ ptt: true })` and never clears it when PTT pauses idle, permanently disabling `shouldFlushOnPageHide()`; `onMicPressStart()` triggers `beginPtt(); releasePtt();` when released before `startVoice()` finishes.
- `src/voice/ui.js` discards `timing`/`cost` frames, still constructs hidden `#hold` + `toggleHold()`, and calls `endUtterance(true)` on non-PTT VAD silence.
- `src/voice/stt.py` `LiveUtterance.flush()` sets `max_wait = 0.7` when `phrase_bytes >= 3200`.
- `src/api/web.py` `trace_url()` calls blocking `urllib.request.urlopen(..., timeout=2)` inside async `chat_stream` and `voice_ws`.
- `src/static/index.html` collides `.steps summary .pill` with `.pill:hover` (`theme.css:170`) and places `position: fixed` `.ds-aurora`/`.ds-grain` inside backdrop-filtered/transformed `.login`.
- `src/api/cli.py` omits `finally:` DB close in `_print_known_shoppers()` and sleeps 1.2 s on a no-op `[2/3] Loading current orders` step.

## Goals / Non-Goals

**Goals:**
- Keep fast sentence-by-sentence masked TTS streaming in Explain voice mode (with a zero-latency `,\n` guard) while guaranteeing masked-only persistence in Mem0/traces, real masking latency/span/cost metrics, accurate `stt.measured`, and dynamic `MASK` evaluation.
- Fix Quick mode after browser login and voice connect without breaking explicit `#toggleJudge`/`#toggleMask` overrides (including preserving explicit choices across page reload).
- Restore tab-close Mem0 flush after idle Push-to-Talk turns while protecting an actively open mic, and eliminate the `#mic` quick-click race.
- Remove dead `#hold` button, fix non-PTT VAD `commit: false`, enforce strict `250 ms` empty flush drain, render `timing`/`cost` in `"What happened"`, eliminate sync HTTP blocking in `trace_url()`, fix `.pill`/`.ds-aurora` CSS bugs, and bring CLI/web/cross-tab theme sync into parity.

**Non-Goals:**
- Security blocker/masker regex hardening or A2A single-role fixes (handled in Change `13`).
- Railway deployment config, `seed.sql` idempotency, or FDE `docs/` reconciliation (handled in Change `15`).
- Dependency upgrades or `arize-phoenix` removal (handled in Change `16`).

## Decisions

1. **Sentence-by-sentence masked voice streaming with full observability, `,\n` guard, redaction & interlock clarity (`src/voice/router.py`, `src/api/web.py`, `.env.example`):**
   - Keep `turn_stream = True` with `absorb_masked()` / `speak_masked()` (preserving `test_demo_mode_explain_speaks_each_masked_sentence`).
   - Keep `_take_complete()` splitting on `.!?…` and `:` (zero TTFA penalty on list introductions), while skipping clause splits at a newline immediately preceded by a comma (`(?<!,)\n+`) when `turn_mask=True` so multi-line addresses like `"123 Market St,\nSpringfield"` stay intact for `mask_text()`.
   - Keep `STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK_ENABLED` intact (representing *raw/unmasked* streaming, preserving existing `test_stream_enabled_is_off_when_mask_wins` and `test_config_warnings_keep_mask_conflict_and_skip_cloud_project` assertions), and update `_config_warnings()` copy and `.env.example` lines 7–9 so they accurately explain that *raw unmasked* streaming is disabled when `MASK=true` (while Explain voice turns mask each sentence via A2A before speaking).
   - In `speak_masked()`: wrap `await mask_text(text)` inside `tracer.start_as_current_span("security.a2a_mask")` (setting `OPENINFERENCE_SPAN_KIND="GUARDRAIL"`, `INPUT_VALUE`, `OUTPUT_VALUE`), record `seg_t0 = time.perf_counter()` *before* `await mask_text(text)`, accumulate `mask_elapsed_sec += time.perf_counter() - seg_t0`, accumulate `mask_in_chars += len(text)` and `mask_out_chars += len(spoken)`, and set `timing["mask"] = round(mask_elapsed_sec, 3)`. Emit the `"Data Masker"` step with actual measured `ms` and populate `mask_tok` for `cost`.
   - Track `stt_measured` per turn (`True` only when `usage_tokens(stt_usage)` is non-zero; `False` when `stt_charge` estimated from PCM bytes) and pass it into `send_cost()` instead of hardcoding `True`.
   - Set `answer_text = (shown if turn_mask and shown else display).strip()`, record sanitized user text (`clean`, captured from the sanitizer step/event) in `record(user_id, "user", clean)` (`router.py` line 467), and set `span.set_attribute(ATTR.OUTPUT_VALUE, answer_text)` on `voice.turn` so neither `_transcripts`/Mem0 nor Phoenix ever persist unmasked assistant replies or raw unsanitized user input.
   - Pass a callable `mask_enabled_fn=mask_enabled` (keeping backward compatibility when a bool or `None` is passed to `make_voice_router`) so runtime `MASK` env changes take effect without re-import.
   - Round all `timing` values to `3` decimal places (`round(..., 3)`).
   - **Voice `off_topic` TTS continuity & Judge error non-fallthrough (`src/voice/router.py`):** When `text_pipeline` yields a `blocked=True` event with `reason == "off_topic"` (keeping `stage="judge"` so `/architecture` highlights `n-judge`), speak the short polite redirect via `speak()` (optionally caching the static PCM bytes per `(TTS_MODEL, TTS_VOICE, text)` for `<20 ms` replay) while skipping `record()` and closing the turn cleanly instead of returning in dead silence. Add an explicit `elif kind == "error":` handler in `run_agent` that forwards the error JSON and returns cleanly instead of falling through to `response_text: ""` and `speak("")`.

2. **Explicit-only guardrail overrides, server-side clearing & lifecycle cleanup (`src/static/index.html`, `src/voice/ui.js`, `src/api/web.py`, `src/voice/router.py`):**
   - Only call `POST /api/guardrails` and `ws.send({type: "guardrails", ...})` when the user has explicitly set `localStorage["cs-judge"]` or `localStorage["cs-mask"]` (i.e., clicked `#toggleJudge` or `#toggleMask`), NOT on initial login/WS open when neither key has been explicitly overridden — while still syncing explicit stored choices on `restoreShopper()` / `cs:login` so intentional overrides survive reload.
   - In `POST /api/guardrails` (`src/api/web.py`), inspect `req.model_fields_set`: an omitted field leaves the existing override unchanged (preserving partial updates), while an explicit `null` (`"judge" in req.model_fields_set and req.judge is None`) pops that override from `_guardrails[user_id]` (removing the user entry when empty). Mirror this in `/voice/ws` (`src/voice/router.py`): `"judge" in data` with `data["judge"] is None` resets `judge_override = None` (and same for `mask`).
   - Clear `_guardrails.pop(uid, None)` in `_flush_shopper()` and `/api/login` (in addition to `/api/logout`) so stale overrides never survive tab-close flushes or re-logins.
   - Fix `demo_pipeline_kwargs()` (`src/api/web.py` lines 145–146) so Quick mode returns `{"judge": False, "mask": False, "stream": stream_endpoint}` instead of hardcoding `stream: True` for non-streaming `POST /api/chat`.
   - When the user clicks `modeQuick` or `modeExplain` (`setDemoMode`), clear explicit per-session overrides (`POST /api/guardrails` `{user_id: USER, judge: null, mask: null}` + WS `{type: "mode", mode: next, judge: null, mask: null}`, removing `localStorage["cs-judge"]`/`"cs-mask"` and syncing toggle button visuals to the chosen mode's defaults), while still letting subsequent clicks on `#toggleJudge` / `#toggleMask` override either mode (preserving `test_guardrails_toggles_override_judge_and_mask_in_both_explain_and_quick`).

3. **Active-capture `window.csVoiceOn` & `#mic` quick-click guard (`src/voice/ui.js`):**
   - Keep `shouldFlushOnPageHide()` checking `if (window.csVoiceOn) return false;` (preserving `test_pagehide_keeps_a_live_mic_signed_in` and `test_session_refresh.py`).
   - In `src/voice/ui.js`, set `window.csVoiceOn = true` during active capture/non-PTT listening (`beginPtt()`, active non-PTT `startVoice({ ptt: false })`) and set `window.csVoiceOn = false` in `finishPttRelease()` once `pttPaused = true` (and in `stopVoice()`), so closing the tab after a completed PTT turn properly beacons `/api/page-leave` and flushes Mem0.
   - In `onMicPressStart()` (`ui.js` lines 592–599), if `!micPressHeld` when `startVoice({ ptt: true })` resolves, abort cleanly (`pttActive = false; pttPaused = true; speaking = false; setVoiceStatus("");`) instead of calling `beginPtt(); releasePtt();`, matching the `Tab` handler (`L657-664`).

4. **Voice UI telemetry, `#hold` removal + `#mic` `.on` coral state, VAD settle, and `LiveUtterance.flush()` (`src/voice/ui.js`, `src/voice/stt.py`, `src/voice/tts.py`):**
   - Handle `case "timing":` and `case "cost":` in `ui.js` by rendering/updating a compact `"Metrics"` / summary line inside `stepsPanel(ensureNode())` when not in `quick` mode (showing total latency in seconds and `$X.XXXX` USD cost with per-stage breakdown).
   - Delete `holdBtn` creation, `#hold` references, and `toggleHold()` from `src/voice/ui.js`; update `setVoiceStatus()` to toggle `.on` (coral recording styling) on `micBtn` while Push-to-Talk is actively capturing (`pttActive || !!pttTailTimer`) and `.live` (teal) when voice is connected/listening (`voiceOn && !pttPaused && !pttActive && !pttTailTimer`), satisfying `web-and-cli-channels/spec.md`'s semantic voice button requirement cleanly; update `test_mute_unmute_and_mic_click_off` in `tests/unit/test_voice.py` to test PTT press/release, `.on`/`.live` classes, quick-click abort, and assert no `#hold` button exists.
   - In `onFrame()` non-PTT silence timeout (`silenceMs >= END_SILENCE_MS`), call `endUtterance(false)` without setting `pttPaused = true`, allowing the server's `1500 ms` / `400 ms` multi-burst settle window to function.
   - In `src/voice/stt.py` `LiveUtterance.flush()`, cap empty-transcript drain strictly at `_FLUSH_DRAIN_SEC` (`0.25 s`) regardless of `phrase_bytes` (keeping a longer wait only when an interim transcript has already arrived and is awaiting finalization).
   - Remove unused `transcribe()` from `src/voice/stt.py` and `synthesize()` from `src/voice/tts.py`, updating `test_tts_and_stt_defaults_are_the_cascade_models` and removing `test_live_transcribe_when_api_key_set` in `tests/unit/test_voice.py`.

5. **Non-blocking `trace_url()`, Web/CLI parity & UI CSS fixes (`src/api/web.py`, `src/api/cli.py`, `src/static/index.html`, `src/static/theme.css`):**
   - Offload `trace_url()`'s Phoenix `/v1/projects` HTTP lookup off the asyncio event loop (`async def resolve_trace_url(span)` calling `asyncio.to_thread(...)`, keeping sync `trace_url(span)` compatible for any direct callers/tests, and forwarding `Authorization: Bearer <PHOENIX_API_KEY>` when `PHOENIX_API_KEY` is set) and add a short failure cooldown (e.g., 30 s) when Phoenix is unreachable so turns never stall 2 s repeatedly.
   - Return `"model": AGENT_MODEL` in `POST /api/login`.
   - Yield sanitized `clean` (or return it via the sanitizer step/event) so `web.py` records sanitized user text in `_transcripts` / Mem0 just like `cli.py`.
   - In `src/api/cli.py`: gate `_mask_response()` behind `mask_enabled()`, use `greet_user(user_context["user_id"])`, add `thinking_budget=0` to `LlmAgent`, track pending tool calls per tool name in a FIFO queue (`pending[name].pop(0)`) matching `web.py`, close `cur`/`conn` in a `finally:` block in `_print_known_shoppers()`, and remove the fake 1.2 s `[2/3] Loading current orders` sleep (simplifying loader steps to `[1/2] Authenticating user` and `[2/2] Loading previous actions`).
   - In `src/static/index.html`: add `window.addEventListener("storage", (e) => { if (e.key === "cs-theme") applyTheme(e.newValue || "light"); });`, prevent `.steps summary .pill` from inheriting `.pill:hover` `transform: translateY(-2px)` from `src/static/theme.css`, and move `.ds-aurora`/`.ds-grain` to a sibling wrapper around `.login` (removed together on sign-in) so `backdrop-filter` + `ds-enter` transform on `.login` no longer clip the fixed aurora backdrop.

## Risks / Trade-offs

- **[Risk] Removing `#hold` / `transcribe()` breaks existing JS/Python tests that assert on those exact identifiers** → Mitigation: Explicitly update `test_mute_unmute_and_mic_click_off` and `test_tts_and_stt_defaults_are_the_cascade_models` in `tasks.md`.
- **[Risk] Changing `timing` rounding from 2 to 3 decimal places could break exact float assertions in unit tests** → Mitigation: Audit `tests/unit/test_voice.py` during apply and verify all timing assertions pass cleanly.
- **[Risk] Clearing `window.csVoiceOn` when PTT pauses while keeping the WebSocket open means a tab reload triggers `/api/page-leave` then cancels via `/api/session`** → Mitigation: Existing 3 s `PAGE_LEAVE_GRACE_MS` and epoch cancellation handle reloads seamlessly while real tab closes now actually flush Mem0.
- **[Risk] Moving `.ds-aurora`/`.ds-grain` out of `#login` means `enterShop()` must remove the wrapper (not just `#login`)** → Mitigation: Wrap `#login` and the aurora/grain divs inside `<div id="loginScreen">` (or remove `#login`, `.ds-aurora`, `.ds-grain` together in `enterShop()`) and assert in `tests/unit/test_design_system_ui.py` that aurora stays scoped to the sign-in screen.
