# Proposal: Security Guardrails & 100-Scenario Evals (`03-security-guardrails-and-evals`)

## Why

The cascade must block SQLi/XSS/command/prompt injection before the agent runs, and must redact 16 PII categories before TTS. The PoC proved the architecture and found three defects: discarded `_preprocess_query`, unused Model Armor leftovers in the sanitizer, and a DLP masker that no-ops unless an extra cloud project is set and also corrupts multibyte UTF-8. This slice keeps masking as a local regex function so Groups 1–7 need no extra cloud SDK.

This slice is independently testable: sanitizer, blocker, and masker are pure functions. The 100-scenario eval suite (`61` malicious + `39` legitimate) does not need FastAPI or A2A.

## What Changes

- Add `src/security/sanitizer.py` with `MAX_INPUT_LENGTH = 300` and `ALLOWED_CHARS` whitelist, without Model Armor / `google.auth`.
- Add `src/security/blocker.py` that evaluates both the raw query and `_preprocess_query` (URL-decode + leetspeak) with word-boundary patterns so `"confirm"` is not blocked as `rm`.
- Add `src/security/masker.py` as a self-contained 16-PII `re.sub` redactor (asterisks, character-safe, no DLP), with per-type unit fixtures and conservative `PERSON_NAME`.
- Move the eval suite to `tests/evals/` and require `100/100` pass.
- Prove URL-encoded detection with a raw `evaluate_query` unit test, because the eval harness sanitizes first and strips `%`.

## Capabilities

### New Capabilities
- `security-guardrails`: Pre-execution sanitizer + blocker, post-execution 16-PII masker, and the 100-scenario eval corpus.

### Modified Capabilities

## Impact

- `src/security/{__init__.py, sanitizer.py, blocker.py, masker.py}`
- `tests/evals/{evaluator.py, test_config.json, test_scenarios.json, test_security_eval.py}`
- `tests/unit/test_security.py`

## Channels

- **In scope:** none (library modules + eval corpus)
- **Out of scope:** A2A JSON-RPC wrapping, Web Chat, Voice, CLI (Groups 4 and 6 call these functions)

## Out of Scope

- A2A Judge/Masker servers (Group 4)
- ADK `before_tool_callback` tenant isolation (Group 6)
