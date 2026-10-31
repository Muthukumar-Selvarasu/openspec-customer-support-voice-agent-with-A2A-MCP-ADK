# cascade-voice-engine Specification

## Purpose

Defines the cascade voice WebSocket: STT, settle-and-combine, barge-in, TTS, the MASK vs stream interlock, and per-turn USD/token cost.

## Requirements

### Requirement: PCM Framing and Transcript Cleanup
The system SHALL wrap 16-bit PCM in a WAV header via `pcm16_to_wav` and SHALL strip VTT/timecode artifacts in `_clean`.

#### Scenario: WAV header is valid
- **WHEN** `pcm16_to_wav` is given PCM16 bytes
- **THEN** the output starts with `RIFF` and `WAVE`

### Requirement: Streaming Interlock Prefers Masking
`STREAM_ENABLED` MUST equal `AGENT_RESPONSE_STREAM and not MASK`. When both flags are true, streaming is off and masking wins.

#### Scenario: MASK wins over streaming
- **WHEN** `MASK=true` and `AGENT_RESPONSE_STREAM=true`
- **THEN** `STREAM_ENABLED` is false

### Requirement: Multi-Burst Settle and Barge-In
The voice router SHALL append STT bursts into one buffer, wait `1500 ms` of quiet before sending the combined query, and SHALL cancel in-flight TTS on client `{"type":"interrupt"}`.

#### Scenario: Two bursts combine
- **WHEN** two PCM bursts arrive within the settle window
- **THEN** the pipeline receives one combined transcript

#### Scenario: Interrupt stops speech
- **WHEN** the client sends `interrupt` during TTS
- **THEN** the server emits `turn_end` with `reason: "interrupted"`

### Requirement: Sentence Chunking and Cost Accounting
`split_sentences` SHALL chunk on `.!?…`. `cost.usd`, `estimate_tokens`, and `usage_tokens` SHALL produce per-stage token and USD totals.

#### Scenario: Cost helper returns USD
- **WHEN** `cost.usd` is called with input/output token counts
- **THEN** it returns a non-negative float

### Requirement: Voice Masking Uses Local Group 3 Masker
Voice startup MUST NOT warn that masking needs an extra cloud project. `MASK=true` uses the local Group 3 masker.

#### Scenario: Config warnings stay local
- **WHEN** `_config_warnings()` runs with `MASK=true`
- **THEN** the list does not say masking is a no-op without a cloud project
