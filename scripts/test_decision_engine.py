"""Offline Task 7A smoke test. No credentials, Strands, or network needed."""

from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.decision import evaluate
from backend.app.decision.fixtures import scenario_fixtures


def main() -> int:
    failures = 0
    print("ClosureOps offline decision engine | SIMULATED DEMO | PROTOTYPE rules")
    for name, scenario in scenario_fixtures().items():
        result = evaluate(scenario.input)
        passed = (
            result.recommendation == scenario.expected_recommendation
            and result.evaluation_status == scenario.expected_status
            and result.data_label == "SIMULATED DEMO"
            and result.human_approval_required is True
        )
        failures += not passed
        print(f"{'PASS' if passed else 'FAIL'} | SIMULATED DEMO | {name}: "
              f"{result.recommendation or result.evaluation_status} | {result.evidence_sufficiency}")
        for rule in result.triggered_rules:
            print(f"  {rule.rule_id}: {rule.reason}")
    print(f"{'PASS' if failures == 0 else 'FAIL'} | No facility status was changed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
