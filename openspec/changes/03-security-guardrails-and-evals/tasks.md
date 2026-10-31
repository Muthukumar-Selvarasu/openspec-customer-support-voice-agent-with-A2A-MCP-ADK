# Tasks: `03-security-guardrails-and-evals`

Implement guardrails under `src/security/` with `src.security.*` imports. Grow `tests/unit/test_security.py` per task. Do not rewrite eval scenario texts unless a word-boundary tweak is required for a legitimate PASS.

## 1. Sanitizer

- [ ] 1.1 Implement `src/security/sanitizer.py` with `MAX_INPUT_LENGTH = 300` and `ALLOWED_CHARS`; reject over-long input with `ValueError`; keep it local (no Model Armor, no extra cloud SDK); verify `sanitize_input("Where is order 3?")` via `pytest tests/unit/test_security.py -k sanitizer`

## 2. Blocker

- [ ] 2.1 Implement `src/security/blocker.py` so `evaluate_query` assigns `processed = self._preprocess_query(query)` and matches patterns on both the raw query and the URL-decoded / leetspeak form; word-boundaries MUST leave `"Yes, please confirm"` as `PASS`; add a unit test that raw corpus payload `url_encoding` is `BLOCKED` without running it through the sanitizer first; if English `"select"` becomes `BLOCKED`, tighten `\\b` patterns only; verify with `pytest tests/unit/test_security.py -k blocker`

## 3. Masker

- [ ] 3.1 Implement `src/security/masker.py` `mask_sensitive_data(text: str) -> str` as character-safe `re.sub` covering all 16 `PII_INFO_TYPES` with no `project_id` and no UTF-8 byte slicing; add one unit example per info type; do not redact order-status tokens (`PROCESSING`, `SHIPPED`, `DELIVERED`, `CANCELLED`, `RETURNED`) or the words `Order` / `Status` / `Premium`; verify email + street address with surrounding `—` / `…` stay intact via `pytest tests/unit/test_security.py -k masker`

## 4. Eval corpus

- [ ] 4.1 Implement `tests/evals/{evaluator.py,test_scenarios.json,test_config.json,test_security_eval.py}` against `src.security` with `61` malicious and `39` legitimate scenarios; the harness may sanitize then block (URL-encoding coverage stays in task 2.1); verify `100/100` with `pytest tests/unit/test_security.py tests/evals/test_security_eval.py`
