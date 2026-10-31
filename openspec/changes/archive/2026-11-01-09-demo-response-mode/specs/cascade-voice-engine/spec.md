# Spec Delta

## MODIFIED Requirements

### Requirement: Multi-Burst Settle and Barge-In
The voice router SHALL append STT bursts into one buffer and SHALL cancel in-flight TTS on client `{"type":"interrupt"}`. An Explain turn, and any turn that does not name a mode, SHALL wait `1500 ms` of quiet before sending the combined query. A Quick turn SHALL wait `400 ms`.

#### Scenario: Two bursts combine
- **WHEN** two PCM bursts arrive within the settle window
- **THEN** the pipeline receives one combined transcript

#### Scenario: Interrupt stops speech
- **WHEN** the client sends `interrupt` during TTS
- **THEN** the server emits `turn_end` with `reason: "interrupted"`

#### Scenario: Quick settle is shorter
- **WHEN** the voice client has selected Quick and speech goes quiet
- **THEN** the combined query is sent after `400 ms`

## ADDED Requirements

### Requirement: Quick voice turn skips judge and masker
A Quick voice turn SHALL skip the A2A Security Judge and the A2A Data Masker, SHALL still run the sanitizer, and SHALL start TTS on the first finished sentence. An Explain voice turn SHALL keep the Judge, the Masker, and buffered speech while process `MASK` is true.

#### Scenario: Quick omits judge and masker
- **WHEN** a voice turn runs with mode `quick`
- **THEN** the turn events include the sanitizer and the spoken answer, and include neither judge nor masker

#### Scenario: Quick speaks the first sentence early
- **WHEN** a Quick voice turn produces more than one sentence
- **THEN** TTS audio for the first sentence is sent before the rest of the reply is spoken

#### Scenario: Explain still masks before speech
- **WHEN** a voice turn runs with mode `explain` and process `MASK` is true
- **THEN** TTS starts only after the full reply has been masked
