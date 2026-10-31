# Design: Security Guardrails & 100-Scenario Evals

## Context

See `proposal.md`. Independent of Groups 4–7. Implement sanitizer, blocker, and masker under `src/security/` and the eval corpus under `tests/evals/`. Closes PoC bugs #1 (discarded preprocess), #3 (DLP no-op), and #4 (byte-offset UTF-8 corruption), and drops Model Armor.

## Goals / Non-Goals

**Goals:**
- Deterministic local sanitizer / blocker / masker (regex, no extra cloud SDK).
- `100/100` on the existing eval corpus.
- Per-type masker fixtures so PII coverage is not a single email example.

**Non-Goals:**
- Hosting Judge/Masker as A2A services.
- Changing the 100 scenario texts unless a regex word-boundary tweak is required for a legitimate PASS.

## Decisions

### Decision 1: Drop Model Armor from sanitizer
Do not add Model Armor, `google.auth`, or extra cloud env vars. Keep length cap + whitelist + final regex.

### Decision 2: Use preprocess output
In `evaluate_query`, replace the discarded call with `processed = self._preprocess_query(query)` and search patterns on both `query` and `processed`. If English `"select"` or similar legitimate phrases fail, tighten `\\b` only (PoC bug #2).

### Decision 3: Self-contained masker
Replace `google.cloud.dlp_v2` with regexes covering the 16 `PII_INFO_TYPES`. Signature becomes `mask_sensitive_data(text: str) -> str` (no `project_id`). Use character spans, not UTF-8 byte slices. `PERSON_NAME` must not eat order-status tokens or the words `Order` / `Status` / `Premium`.

### Decision 4: Evals live under `tests/evals/`
Move `evaluator.py`, `test_scenarios.json`, and `test_config.json` out of application code. Add `tests/evals/test_security_eval.py` as the pytest entry.

### Decision 5: URL-encoding is a unit test, not an eval-harness accident
The copied evaluator sanitizes first, then blocks. `ALLOWED_CHARS` strips `%`, so the corpus case `url_encoding` may never reach `_preprocess_query`. Prove bug #1 with a unit test that calls `evaluate_query` on the raw encoded string. Do not claim the 100-scenario harness covers preprocess unless the evaluator is also changed to pass raw text in.

## Risks / Trade-offs

- **[Risk] Regex PII is weaker than a managed DLP product** → Mitigation: local PoC uses the 16 types in `PII_INFO_TYPES` plus unit tests for each category; no extra cloud SDK until a later change asks for one.
- **[Risk] Preprocess + word-boundary tweaks could fail a legitimate scenario** → Mitigation: run the full 100 and adjust `\b` patterns only, do not rewrite the corpus.
