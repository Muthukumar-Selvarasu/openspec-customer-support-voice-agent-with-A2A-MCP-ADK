# Spec Delta

## MODIFIED Requirements

### Requirement: Read-Confirm-Audit Prompt Uses MCP Parameter Names
`SQL_PROMPT_INSTRUCTION` SHALL instruct the agent to read first, confirm with the shopper, write only via `action-log`, never call `update-order-status`, pass `parameters` (not `parameters_json`), and treat `get-order-status` `customer_email` as the authenticated shopper. To keep voice and chat turn latency within 3–5 seconds, `SQL_PROMPT_INSTRUCTION` SHALL instruct the agent to call `search_memory` only when the shopper asks about past conversations, saved preferences, or context not available from the order tools (rather than calling `search_memory` unconditionally before every order lookup), and SHALL instruct the agent to keep responses concise (1–3 clear sentences).

#### Scenario: Prompt matches tools.yaml
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it contains `parameters` and does not contain `parameters_json`

#### Scenario: Prompt scopes memory search to preference or history context and encourages concise replies
- **WHEN** `SQL_PROMPT_INSTRUCTION` is formatted with `USER_ID`
- **THEN** it does not instruct the agent to `ALWAYS use the search_memory function` on every query, directs order lookups straight to `get-order-status` or `find-customer-orders`, and includes a concise response guideline
