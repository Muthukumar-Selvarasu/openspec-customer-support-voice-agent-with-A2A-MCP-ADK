"""Run the 100-scenario corpus through the local sanitizer and blocker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.security.blocker import evaluate_prompt
from src.security.sanitizer import sanitize_input

_EVAL_DIR = Path(__file__).resolve().parent


class SimpleEvaluator:
    """JSON-driven security evaluation."""

    def __init__(
        self,
        scenarios_file: str | None = None,
        config_file: str | None = None,
    ) -> None:
        scenarios_path = Path(scenarios_file or _EVAL_DIR / "test_scenarios.json")
        config_path = Path(config_file or _EVAL_DIR / "test_config.json")
        self.scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.results: dict[str, Any] = {
            "summary": {"total": 0, "passed": 0, "failed": 0},
            "details": [],
        }

    def evaluate_query(
        self, query: str, expected_outcome: str, test_name: str
    ) -> dict[str, Any]:
        """Sanitize, then block on both the original text and the sanitized text.

        The whitelist removes ``%``, ``<``, and ``/`` before the regex gate, so
        the original query is checked as well. URL-decoding still happens inside
        ``evaluate_query`` on that original text.
        """
        try:
            sanitized = sanitize_input(query)
        except ValueError:
            return self._build_result(
                test_name, query, expected_outcome, "BLOCKED", "Blocked by sanitizer"
            )

        if evaluate_prompt(query) == "BLOCKED" or evaluate_prompt(sanitized) == "BLOCKED":
            return self._build_result(
                test_name,
                query,
                expected_outcome,
                "BLOCKED",
                "Blocked by SecurityBlocker",
            )
        return self._build_result(
            test_name, query, expected_outcome, "PASSED", "Passed all checks"
        )

    @staticmethod
    def _build_result(
        name: str, query: str, expected: str, actual: str, response: str
    ) -> dict[str, Any]:
        return {
            "name": name,
            "query": query,
            "expected_outcome": expected,
            "actual_outcome": actual,
            "response": response,
            "passed": actual == expected,
        }

    async def run_evaluation(self) -> dict[str, Any]:
        """Evaluate every malicious and legitimate scenario."""
        scenarios = [
            {"category": "malicious", **item}
            for item in self.scenarios["malicious_queries"]
        ]
        scenarios.extend(
            {"category": "legitimate", **item}
            for item in self.scenarios["legitimate_queries"]
        )
        passed = 0
        for scenario in scenarios:
            result = self.evaluate_query(
                query=scenario["query"],
                expected_outcome=scenario["expected_outcome"],
                test_name=f"{scenario['category']}_{scenario['name']}",
            )
            if result["passed"]:
                passed += 1
            self.results["details"].append(result)

        total = len(scenarios)
        self.results["summary"]["total"] = total
        self.results["summary"]["passed"] = passed
        self.results["summary"]["failed"] = total - passed

        save_name = self.config.get("save_results_to")
        if save_name:
            out_path = _EVAL_DIR / save_name
            out_path.write_text(
                json.dumps(self.results, indent=2),
                encoding="utf-8",
            )
        return self.results
