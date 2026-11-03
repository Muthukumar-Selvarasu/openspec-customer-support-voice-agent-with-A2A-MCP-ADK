# Spec Delta

## MODIFIED Requirements

### Requirement: Multi-Burst Settle and Barge-In
The voice router SHALL append each flushed utterance into one buffer and SHALL cancel in-flight TTS on client `{"type":"interrupt"}`. An utterance is flushed when the client sends `{"type":"utterance_end"}`. When the client sends `{"type":"utterance_end","commit":true}` (Push-to-Talk release), the server SHALL flush the live transcript and start the turn immediately with zero settle delay (`0 ms`), bypassing the mode settle window. When `commit` is omitted or false, an Explain turn (and any turn that does not name a mode) SHALL wait `1500 ms` of quiet before sending the combined query, and a Quick turn SHALL wait `400 ms`. One transcription connection SHALL stay open while the microphone is active until the microphone turns off, the socket closes, or the client sends `interrupt`. A flush SHALL NOT open a second transcription connection. When a flush produces no transcript, the server MUST NOT emit a speech-to-text step, MUST NOT start the turn or settle timer, and MUST cap empty flush drain within `250 ms`. Audio that arrives while a voice turn is running MUST NOT be transcribed unless the client has sent `interrupt`.

#### Scenario: Two bursts combine
- **WHEN** two utterances flush without `commit: true` within the settle window and both have transcript text
- **THEN** the pipeline receives one combined transcript

#### Scenario: Push-to-Talk release commits immediately without settle delay
- **WHEN** the client sends `{"type":"utterance_end","commit":true}` after streaming speech frames
- **THEN** the server flushes the transcript and starts the voice turn immediately without waiting `1500 ms` or `400 ms`

#### Scenario: Interrupt stops speech
- **WHEN** the client sends `interrupt` during TTS
- **THEN** the server emits `turn_end` with `reason: "interrupted"`

#### Scenario: Quick settle is shorter
- **WHEN** the voice client has selected Quick and speech goes quiet without `commit: true`
- **THEN** the combined query is sent after `400 ms`

#### Scenario: Settle uses the live transcript
- **WHEN** the client sends `utterance_end` and a transcript was already produced during that utterance
- **THEN** the settle timer starts from that transcript and no second full-clip transcription runs

#### Scenario: An empty flush does nothing
- **WHEN** the client sends `utterance_end` and that flush has no transcript text
- **THEN** no speech-to-text step is emitted, drain finishes within `250 ms`, and the reply does not start

#### Scenario: The same connection covers the next phrase
- **WHEN** the shopper speaks again after a flush and before the microphone turns off
- **THEN** those frames go to the transcription connection already open

### Requirement: Sentence Chunking and Cost Accounting
`split_sentences` SHALL chunk on `.!?…`, and streamed voice chunking SHALL also split finished clauses on colons, semicolons, or newlines once a minimum readable phrase length is reached so lists and multi-line replies start TTS early. `cost.usd`, `estimate_tokens`, and `usage_tokens` SHALL produce per-stage token and USD totals.

#### Scenario: Cost helper returns USD
- **WHEN** `cost.usd` is called with input/output token counts
- **THEN** it returns a non-negative float

#### Scenario: Streamed list header speaks before the list finishes
- **WHEN** the agent streams an introductory clause ending with `:` or `\n` followed by order items
- **THEN** the voice router queues that introductory clause for TTS before the remaining lines finish streaming

## ADDED Requirements

### Requirement: Words appear while the shopper is speaking
The voice channel SHALL send speech audio while the shopper is still speaking and SHALL show the growing transcript before the utterance ends. Audio captured while the microphone is only listening SHALL NOT be sent for transcription.

#### Scenario: Transcript grows before silence
- **WHEN** the shopper is speaking and has not yet gone quiet for 1500 ms
- **THEN** the client shows transcript text before `utterance_end`

#### Scenario: Silence ends the utterance
- **WHEN** speech has started and the shopper is then quiet for 1500 ms
- **THEN** the client sends `utterance_end`

#### Scenario: Listening does not open transcription
- **WHEN** the microphone is on and speech has not started
- **THEN** no audio from that quiet period is sent for transcription

### Requirement: Push-to-Talk Immediate Release Commit and Tail Capture
The browser voice client SHALL provide a single Push-to-Talk control (`#mic` button and `Tab` key, with no separate Hold/Mute button) that interrupts any in-progress agent turn or playback when pushed, streams 16 kHz PCM frames while active, immediately turns off the active button visual state upon release, and continues streaming microphone frames for a fixed `1.0 s` tail window before sending `{"type":"utterance_end","commit":true}` and stopping microphone listening.

#### Scenario: Releasing the Talk control or Tab key turns off visual state and sends commit after tail window
- **WHEN** the shopper holds the Talk button or `Tab` key to speak and then releases it
- **THEN** the button removes its `.live` visual state immediately, continues streaming audio frames for `1.0 s` to prevent clipping the last word, and sends `{"type":"utterance_end","commit":true}` upon tail expiry

#### Scenario: Pushing Talk while the agent is thinking combines the questions
- **WHEN** a voice turn is still thinking (before answer text is produced) and the shopper pushes the Talk button to ask an additional question
- **THEN** the in-flight turn is interrupted, the new transcript is appended to the pending question, and the agent answers both together

