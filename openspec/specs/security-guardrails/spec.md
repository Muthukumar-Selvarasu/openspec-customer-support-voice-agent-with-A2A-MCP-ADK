# security-guardrails Specification

## Purpose

Defines deterministic input sanitization, pre-execution injection blocking, self-contained 16-PII masking, and the 100-scenario evaluation corpus.

## Requirements

### Requirement: Length and Character Whitelist Sanitizer
The system SHALL reject input longer than `300` characters and SHALL strip characters outside `ALLOWED_CHARS`. The sanitizer MUST be a local function (length + whitelist + regex) and MUST NOT call Model Armor or any extra cloud SDK.

#### Scenario: Over-long input is rejected
- **WHEN** `sanitize_input` receives a string longer than `300` characters
- **THEN** it raises `ValueError`

#### Scenario: Sanitizer runs locally
- **WHEN** `sanitize_input("Where is order 3?")` is called with no extra cloud env vars
- **THEN** it returns a sanitized string

### Requirement: Blocker Evaluates Raw and Preprocessed Queries
`SecurityBlocker.evaluate_query` SHALL assign `processed = self._preprocess_query(query)` and SHALL match patterns against both the raw query and the URL-decoded / leetspeak-normalized form. Word-boundary patterns MUST NOT block the English word `"confirm"`.

#### Scenario: URL-encoded injection is blocked on the raw query
- **WHEN** `evaluate_query` is called with the raw corpus payload `url_encoding` (not pre-sanitized)
- **THEN** status is `BLOCKED`

#### Scenario: Confirm is allowed
- **WHEN** the query is `"Yes, please confirm"`
- **THEN** status is `PASS`

### Requirement: Self-Contained 16-PII Masker
`mask_sensitive_data(text)` SHALL redact all 16 `PII_INFO_TYPES` with asterisks using local character-safe `re.sub` (no extra cloud SDK) and MUST NOT slice Python strings by UTF-8 byte offsets.

#### Scenario: Email and street address are masked locally
- **WHEN** `MASK` processing runs on text containing an email and a street address
- **THEN** those spans are replaced with asterisks and surrounding multibyte punctuation (`—`, `…`) is intact

#### Scenario: Order status tokens are not treated as PERSON_NAME
- **WHEN** `mask_sensitive_data` is given `Order 4 is PROCESSING`
- **THEN** `PROCESSING` and `Order` remain unmasked

### Requirement: One-Hundred Scenario Eval Corpus
The eval suite SHALL contain `61` malicious and `39` legitimate scenarios and SHALL pass `100/100` against sanitizer + blocker.

#### Scenario: Full corpus is green
- **WHEN** `pytest tests/evals/test_security_eval.py` runs
- **THEN** `100` scenarios pass and `0` fail
