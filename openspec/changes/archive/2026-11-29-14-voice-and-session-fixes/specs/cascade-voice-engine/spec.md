# Spec Delta

## ADDED Requirements

### Requirement: Voice WebSocket Guardrail Controls
`/voice/ws` (`src/voice/router.py`) SHALL accept `{"type":"guardrails","judge":bool|null,"mask":bool|null}` and optional `judge`/`mask` overrides on `{"type":"mode",...}`. Sending explicit `null` for `judge` or `mask` SHALL clear that override back to the active mode default, while omitting a field SHALL preserve its current value. Initial WebSocket connect MUST NOT push default toggle values as explicit overrides that disable Quick mode's default omission of Judge and Masker.

#### Scenario: Voice Quick mode skips Judge and Masker on fresh connect
- **WHEN** a browser client connects to `/voice/ws` with default header toggles and switches to `quick` mode without manually clicking `#toggleJudge` or `#toggleMask`
- **THEN** voice turns run with `judge=False` and `mask=False`

#### Scenario: Explicit voice guardrail override applies and clears on demand
- **WHEN** a user explicitly toggles `#toggleJudge` or `#toggleMask` during an active voice session and later sends `{"type":"mode","mode":"quick","judge":null,"mask":null}`
- **THEN** the override applies while set and clears cleanly back to Quick defaults when `null` is sent

### Requirement: Voice Latency and Cost Inspector Rendering
When Explain mode is active, the browser voice client (`src/voice/ui.js`) SHALL render received `timing` and `cost` WebSocket frames in the turn's `"What happened"` inspector instead of discarding them.

#### Scenario: Voice turn displays latency and USD cost in Explain mode
- **WHEN** `/voice/ws` sends `{"type":"timing",...}` and `{"type":"cost",...}` frames for an Explain turn
- **THEN** `src/voice/ui.js` renders a summary row in `"What happened"` displaying the turn's total latency and USD cost

### Requirement: Voice Off-Topic Spoken Redirect and Pipeline Error Handling
When `text_pipeline` blocks a voice turn with `reason="off_topic"`, `src/voice/router.py` SHALL speak the polite customer-support redirect via TTS (skipping Mem0 recording) instead of returning silently. When `text_pipeline` emits an `error` event (such as an unreachable Judge), `src/voice/router.py` SHALL forward the error and return without sending an empty `response_text` or calling TTS.

#### Scenario: Voice off-topic redirect is spoken instead of silent
- **WHEN** a voice turn returns `blocked=True` with `stage="judge"` and `reason="off_topic"`
- **THEN** `/voice/ws` streams TTS audio for the polite redirect, emits `turn_end`, and does not persist the off-topic turn to Mem0

#### Scenario: Voice pipeline error does not fall through into empty TTS
- **WHEN** `text_pipeline` yields `{"type":"error",...}` during a voice turn
- **THEN** `/voice/ws` forwards the error event and returns without emitting `response_text: ""` or invoking `speak("")`

## MODIFIED Requirements

### Requirement: Streaming Interlock Prefers Masking
In `src/voice/router.py`, `STREAM_ENABLED` MUST equal `AGENT_RESPONSE_STREAM and not MASK`, preventing raw unmasked sentence streaming when `MASK` is true. `_config_warnings()` SHALL warn when both flags are true that raw unmasked streaming is disabled while `MASK=true`, while Explain voice turns MAY still mask each finished sentence via A2A before TTS synthesis (`absorb_masked` / `speak_masked`).

#### Scenario: MASK wins over streaming
- **WHEN** `MASK=true` and `AGENT_RESPONSE_STREAM=true`
- **THEN** `STREAM_ENABLED` is false and `_config_warnings()` warns that `AGENT_RESPONSE_STREAM=true` is ignored for raw unmasked streaming while `MASK=true`

### Requirement: Quick voice turn skips judge and masker
In `src/voice/` (`router.py`, `stt.py`, `tts.py`), a Quick voice turn SHALL skip Judge and Masker, run the sanitizer, and start TTS on the first sentence. An Explain turn with dynamic `MASK=true` SHALL run Judge, mask each sentence via A2A before `response_text`/TTS/Mem0/traces (avoiding mid-address `,\n` splits and saving sanitized user text and masked assistant text), and record `security.a2a_mask` span, cumulative timing, and `mask` cost.

#### Scenario: Quick omits judge and masker
- **WHEN** a voice turn runs with mode `quick`
- **THEN** the turn events include the sanitizer and the spoken answer, and include neither judge nor masker

#### Scenario: Quick speaks the first sentence early
- **WHEN** a Quick voice turn produces more than one sentence
- **THEN** TTS audio for the first sentence is sent before the rest of the reply is spoken

#### Scenario: Explain still masks before speech
- **WHEN** a voice turn runs with mode `explain` and process `MASK` is true
- **THEN** each sentence is masked before TTS and `response_text` (keeping comma-newline address lines intact for masking), `_transcripts`/Mem0 and `voice.turn` `output.value` store only the masked response, `timing["mask"]` and step `ms` measure real masking time, and a `security.a2a_mask` span and `cost` entry are recorded

#### Scenario: Voice MASK flag reflects runtime environment
- **WHEN** `MASK` changes in the environment after the voice router is mounted
- **THEN** subsequent voice turns honor the updated `MASK` flag without requiring re-import

### Requirement: Sentence Chunking and Cost Accounting
`split_sentences` (`src/voice/tts.py`) SHALL chunk on `.!?…`, and streamed voice chunking (`src/voice/router.py`) SHALL also split finished clauses on colons, semicolons, or newlines (skipping `,\n` address splits when masking) once minimum phrase length is met. `src/voice/cost.py` SHALL compute per-stage tokens and USD, `cost.stages.stt.measured` SHALL be `false` when estimated from PCM, and `timing` stages SHALL round to `3` decimals.

#### Scenario: Cost helper returns USD
- **WHEN** `cost.usd` is called with input/output token counts
- **THEN** it returns a non-negative float

#### Scenario: stt_charge falls back to forwarded PCM duration and reports measured=false
- **WHEN** `cost.stt_charge(None, pcm_bytes)` is called without usage metadata during a voice turn
- **THEN** it estimates input tokens from forwarded PCM audio seconds, returns `0` for zero bytes, and the turn's `cost` event reports `stages.stt.measured == false`

#### Scenario: Streamed list header speaks before the list finishes
- **WHEN** the agent streams an introductory clause ending with `:` or `\n` followed by order items
- **THEN** the voice router queues that introductory clause for TTS before the remaining lines finish streaming

### Requirement: Words appear while the shopper is speaking
The voice channel SHALL send speech audio while the shopper is still speaking and SHALL show the growing transcript before the utterance ends. Audio captured while the microphone is only listening SHALL NOT be sent for transcription. In non-PTT VAD mode, silence reaching `END_SILENCE_MS` SHALL send `{"type":"utterance_end"}` (without `commit: true`) so the server settle window remains active.

#### Scenario: Transcript grows before silence
- **WHEN** the shopper is speaking and has not yet gone quiet for 1500 ms
- **THEN** the client shows transcript text before `utterance_end`

#### Scenario: Silence ends the utterance
- **WHEN** speech has started in non-PTT mode and the shopper is then quiet for 1500 ms
- **THEN** the client sends `{"type":"utterance_end"}` without `commit: true`

#### Scenario: Listening does not open transcription
- **WHEN** the microphone is on and speech has not started
- **THEN** no audio from that quiet period is sent for transcription

### Requirement: Push-to-Talk Immediate Release Commit and Tail Capture
The browser voice client SHALL expose one Push-to-Talk control (`#mic` and `Tab`, with no `#hold` button) that interrupts active turns when pushed, aborts cleanly if `#mic` is released before startup finishes, streams 16 kHz PCM while held, clears active visual state on release, and streams a `1.0 s` tail before sending `{"type":"utterance_end","commit":true}` and pausing capture.

#### Scenario: Releasing the Talk control or Tab key turns off visual state and sends commit after tail window
- **WHEN** the shopper holds the Talk button or `Tab` key to speak and then releases it
- **THEN** the button removes its `.live` visual state immediately, continues streaming audio frames for `1.0 s` to prevent clipping the last word, and sends `{"type":"utterance_end","commit":true}` upon tail expiry

#### Scenario: Quick click released before startup finishes aborts cleanly
- **WHEN** the shopper releases `#mic` before `startVoice({ ptt: true })` completes
- **THEN** `ui.js` stays paused without starting a `1.0 s` tail recording or sending an empty commit

#### Scenario: Pushing Talk while the agent is thinking combines the questions
- **WHEN** a voice turn is still thinking (before answer text is produced) and the shopper pushes the Talk button to ask an additional question
- **THEN** the in-flight turn is interrupted, the new transcript is appended to the pending question, and the agent answers both together

#### Scenario: No hidden Hold or Mute button is constructed
- **WHEN** `src/voice/ui.js` initializes the voice controls
- **THEN** no `#hold` button or `toggleHold` handler is inserted into the DOM
