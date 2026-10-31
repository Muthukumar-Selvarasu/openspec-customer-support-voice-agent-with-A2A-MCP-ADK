"""100-scenario gate for the local sanitizer and blocker."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tests.evals.evaluator import SimpleEvaluator

_RESULTS = Path(__file__).resolve().parent / "security_test_results.json"


def test_security_eval_corpus_is_green() -> None:
    evaluator = SimpleEvaluator()
    malicious = evaluator.scenarios["malicious_queries"]
    legitimate = evaluator.scenarios["legitimate_queries"]
    assert len(malicious) == 61
    assert len(legitimate) == 39

    results = asyncio.run(evaluator.run_evaluation())
    summary = results["summary"]
    failed = [item for item in results["details"] if not item["passed"]]
    assert summary["total"] == 100
    assert summary["failed"] == 0, failed
    assert summary["passed"] == 100
    _RESULTS.unlink(missing_ok=True)
