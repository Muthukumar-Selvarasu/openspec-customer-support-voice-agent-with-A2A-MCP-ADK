# Spec Delta

## MODIFIED Requirements

### Requirement: Chat and Streamed Inspector Events
`POST /api/chat` SHALL return the final assistant text. `POST /api/chat/stream` SHALL emit NDJSON for the stages that run. Explain, and a request that omits mode, SHALL include sanitizer, judge, tool_call, tool_result, masker, and final. Quick SHALL include sanitizer and final, SHALL omit judge and masker, and SHALL still return the assistant text.

#### Scenario: Root pages are served
- **WHEN** a client GETs `/` or `/architecture` or `/architecture.svg`
- **THEN** the response is `200`

#### Scenario: Explain stream keeps the cascade
- **WHEN** a signed-in client posts `/api/chat/stream` with mode `explain`, or omits mode
- **THEN** the NDJSON includes sanitizer, judge, and masker before final

#### Scenario: Quick stream skips judge and masker
- **WHEN** a signed-in client posts `/api/chat/stream` with mode `quick`
- **THEN** the NDJSON includes sanitizer and final, and includes neither judge nor masker

## ADDED Requirements

### Requirement: Demo mode toggle
The shopper page SHALL offer Explain and Quick, with Explain as the default. The choice SHALL persist in the browser and SHALL be sent on each streamed chat turn and each voice turn. Explain SHALL show the "What happened" panel. Quick SHALL hide that panel and show the assistant answer.

#### Scenario: First visit is Explain
- **WHEN** the shopper page loads with no saved choice
- **THEN** the toggle shows Explain and the next turn sends mode `explain`

#### Scenario: Quick hides the step list
- **WHEN** the shopper selects Quick and sends a typed turn
- **THEN** the assistant bubble shows the answer and the "What happened" panel is not shown

#### Scenario: Saved choice survives reload
- **WHEN** the shopper selects Quick and reloads the page
- **THEN** the toggle still shows Quick
