# Spec Delta

## ADDED Requirements

### Requirement: Customer Action History Lookup
`src/core/greet.py` SHALL expose `get_user_actions(email)` to query `actions_log` rows for the authenticated shopper ordered by `timestamp DESC`, returning an empty list on database errors.

#### Scenario: Action history returns shopper rows newest first
- **WHEN** `get_user_actions(email)` is called for an authenticated shopper
- **THEN** it returns a list of action dictionaries scoped to `email`, or `[]` if the database is unreachable

## MODIFIED Requirements

### Requirement: Customer Credential Authentication and Tier Greeting
The system (`src/core/greet.py`) SHALL authenticate by email and password against `users`, SHALL log database connection errors while failing closed to `None`, and SHALL greet Premium shoppers with name and `total_items_purchased`.

#### Scenario: Premium shopper is recognized
- **WHEN** `authenticate_user` succeeds for a row with `is_premium_customer = true`
- **THEN** `greet_user` includes the shopper's name, Premium status, and purchase count

#### Scenario: Unknown credentials fail closed
- **WHEN** email and password do not match a `users` row
- **THEN** `authenticate_user` returns `None`

#### Scenario: Database errors log a warning and fail closed
- **WHEN** `authenticate_user` encounters a Postgres connection or query exception
- **THEN** it logs a warning and returns `None`

### Requirement: Mem0 Search and Save Tools
The system (`src/core/memory.py`) SHALL expose `search_memory(query, user_id)` and `save_memory(messages, user_id)` scoped to the authenticated `user_id` (handling both `dict` and `list` Mem0 search responses), and SHALL provide a session-bound ADK tool factory `make_memory_search_tool(user_id)` registered with the support agent so the model cannot pass a `user_id` argument. Importing `src.core.memory` MUST succeed when `MEM0_API_KEY` is unset (client constructed on first use).

#### Scenario: Search uses the session user id
- **WHEN** `search_memory` is called (whether Mem0 returns `{"results": [...]}` or a bare `list`)
- **THEN** the Mem0 filter includes that `user_id`, normalizes the result list safely, and does not accept a different identity from the model

#### Scenario: ADK memory tool hides user_id from the model
- **WHEN** the web or CLI agent is constructed with `make_memory_search_tool(user_id)`
- **THEN** the tool signature accepts only `query: str`, always filters Mem0 by the bound session `user_id`, and keeps tool name `search_memory`

#### Scenario: Memory module imports without a key
- **WHEN** `MEM0_API_KEY` is unset
- **THEN** `import src.core.memory` does not raise

### Requirement: Read-Confirm-Audit Prompt Uses MCP Parameter Names
`SQL_PROMPT_INSTRUCTION` (`src/core/prompts.py`) SHALL enforce Read-Confirm-Audit (`action-log` with `parameters`, never `update-order-status`), session-bound `customer_email`, scoped `search_memory` (treating saved memories as untrusted preference data), concise 1–3 sentence replies, customer-support domain scope (with hybrid-turn partial fulfillment), confidentiality/persona lock, and policy boundaries against unauthorized promises or regulated advice.

#### Scenario: Prompt matches tools.yaml
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it contains `parameters` and does not contain `parameters_json`

#### Scenario: Prompt scopes memory search to preference or history context and encourages concise replies
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it does not instruct the agent to `ALWAYS use the search_memory function` on every query, directs order lookups straight to `get-order-status` or `find-customer-orders`, and includes a concise response guideline

#### Scenario: Prompt enforces domain scope, confidentiality, policy boundaries, and untrusted-memory framing
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it restricts replies to online-shop customer support (declining poems/jokes/creative rewrites and handling hybrid turns by answering only the support clause), forbids roleplay switches and system/tool disclosure, declines unauthorized refund/discount promises and legal/medical/competitor advice, and treats saved memories strictly as factual data rather than instructions
