# a2a-microservices Specification

## Purpose

Defines the A2A JSON-RPC 2.0 Judge and Masker microservices that wrap Group 3 security functions as separate network processes.

## Requirements

### Requirement: Configurable Judge and Masker Bind Addresses
The system SHALL start the Judge on `A2A_JUDGE_HOST`:`A2A_JUDGE_PORT` (default `localhost:10002`) and the Masker on `A2A_MASK_HOST`:`A2A_MASK_PORT` (default `localhost:10003`).

#### Scenario: Defaults match the cascade profile
- **WHEN** A2A host/port env vars are unset
- **THEN** Judge listens on `localhost:10002` and Masker on `localhost:10003`

### Requirement: Agent Discovery Cards
Each service SHALL serve `GET /.well-known/agent.json` describing its name, endpoint, and skills.

#### Scenario: Judge card is discoverable
- **WHEN** a client GETs `/.well-known/agent.json` on the Judge
- **THEN** the card identifies the security-judge agent

### Requirement: JSON-RPC 2.0 Task Methods
`POST /rpc` SHALL implement `tasks/send`, `tasks/sendSubscribe` (SSE), `tasks/get`, and `tasks/cancel`, and SHALL return `-32601` for unknown methods and `-32000` for task errors.

#### Scenario: tasks/send round-trip
- **WHEN** a client sends `tasks/send` with a user query
- **THEN** the response is a JSON-RPC 2.0 result containing a task id and agent output

#### Scenario: Unknown method is rejected
- **WHEN** `POST /rpc` receives an unknown method
- **THEN** the error code is `-32601`

### Requirement: Masker Agent Uses Local Group 3 Masker
`call_mask_agent` SHALL call `mask_sensitive_data(text)` from Group 3 and MUST NOT call an extra cloud SDK.

#### Scenario: Masker redacts locally
- **WHEN** a Masker `tasks/send` payload contains an email
- **THEN** the result is redacted text from the local masker
