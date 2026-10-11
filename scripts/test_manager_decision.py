"""Task 8A local CLI: synthetic evidence only, explicit manager action required."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from backend.app.decision.fixtures import scenario_fixtures
from backend.app.decision.models import OperatingPosture
from backend.app.manager_decisions import (
    AuditStorageError, ManagerDecisionError, ManagerDecisionRequest, ManagerDecisionService,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=tuple(scenario_fixtures()), default="severe_applicable_flood")
    parser.add_argument("--action", choices=("evaluate-only", "approve", "override", "acknowledge-review"),
                        default="evaluate-only", help="Explicit synthetic manager action; default only evaluates")
    parser.add_argument("--posture", choices=tuple(OperatingPosture))
    parser.add_argument("--reason", help="Required override reason, 1-500 characters")
    args = parser.parse_args(argv)
    if args.action != "override" and (args.posture is not None or args.reason is not None):
        parser.error("--posture and --reason apply only to --action override")
    if args.action == "override" and (args.posture is None or args.reason is None):
        parser.error("--action override requires --posture and --reason")
    # Validate user input before generating an evaluation or touching storage.
    action = args.action.upper().replace("-", "_")
    request_fields = dict(action=action, selected_posture=args.posture, reason=args.reason)
    if args.action != "evaluate-only":
        try:
            ManagerDecisionRequest(evaluation_id="eval_" + "0" * 32, **request_fields)
        except ValidationError:
            parser.error("Invalid manager action: override reason must be 1-500 characters without controls")
    try:
        service = ManagerDecisionService(data_mode="SIMULATED DEMO", demo_scenario=args.scenario)
        evaluation = service.evaluate_facility("demo-flood-facility")
        print("ClosureOps | SIMULATED DEMO | Synthetic Demo Manager | PROTOTYPE rules")
        print(f"Evaluation: {evaluation.evaluation_id}")
        print(f"Original deterministic result: {evaluation.result.recommendation or evaluation.result.evaluation_status}")
        if args.action == "evaluate-only":
            print("Evaluation persisted; no manager decision recorded. Select --action to record an explicit action.")
            return 0
        record = service.record_decision(ManagerDecisionRequest(
            evaluation_id=evaluation.evaluation_id, **request_fields,
        ))
        # Reopen storage and read historical evidence without re-fetching it.
        restored = ManagerDecisionService().get_decision(record.decision_id)
        if restored != record or restored.evidence_snapshot != evaluation.evidence_snapshot:
            raise AuditStorageError("Historical reconstruction failed")
        print(f"Decision: {record.decision_id} | {record.manager_action}")
        print(f"Final demo posture: {record.final_posture or 'none (review acknowledged)'}")
        print(f"Decision timestamp: {record.decision_timestamp.isoformat()}")
        print("PASS | Audit persisted and exact historical evidence reconstructed.")
        print("No facility status changed; no notifications sent.")
        return 0
    except (ManagerDecisionError, AuditStorageError) as error:
        print(f"FAIL | {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
