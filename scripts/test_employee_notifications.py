"""Task 8B offline local demonstration; --action approve is an explicit synthetic action."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from backend.app.employee_impact import EmployeeImpactError, resolve_employee_impact
from backend.app.employee_notifications import (
    DuplicateNotificationPlan, NotificationPlanError, NotificationPlanRequest, NotificationPlanService,
)
from backend.app.manager_decisions import (
    AuditStorageError, ManagerDecisionError, ManagerDecisionRequest, ManagerDecisionService,
)

DEMO_DATABASE = Path(__file__).resolve().parents[1] / "backend" / "data" / "employee-notifications-demo.sqlite3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("evaluate-only", "approve"), default="evaluate-only")
    parser.add_argument("--scenario", choices=(
        "normal", "delayed_arrival", "unscheduled_telework", "severe_applicable_flood",
    ), default="severe_applicable_flood")
    parser.add_argument("--database", type=Path, default=DEMO_DATABASE,
                        help="Trusted local demo database path; default is separate from Task 8A history")
    args = parser.parse_args(argv)
    try:
        managers = ManagerDecisionService(
            args.database, demo_scenario=args.scenario, demo_facility_id="jefferson-research",
        )
        evaluation = managers.evaluate_facility("jefferson-research")
        print("ClosureOps | LOCAL ONLY | SIMULATED DEMO | Synthetic Demo Manager | PROTOTYPE rules")
        print("Evidence: invented Jefferson exposure, gauge and fixture readings; no live evidence or inference.")
        print(f"Evaluation: {evaluation.evaluation_id}")
        print(f"Deterministic recommendation: {evaluation.result.recommendation}")
        if args.action == "evaluate-only":
            print("Evaluation persisted. Select --action approve to explicitly record a synthetic approval and prepare a plan.")
            return 0
        record = managers.record_decision(ManagerDecisionRequest(
            evaluation_id=evaluation.evaluation_id, action="APPROVE",
        ))
        impact = resolve_employee_impact(record.facility_id)
        notifications = NotificationPlanService(args.database)
        plan = notifications.prepare(NotificationPlanRequest(decision_id=record.decision_id))
        reopened = NotificationPlanService(args.database)
        if (reopened.get_plan(plan.notification_plan_id) != plan
                or reopened.get_plan_for_decision(record.decision_id) != plan
                or ManagerDecisionService(args.database).get_decision(record.decision_id) != record
                or managers.get_evaluation(evaluation.evaluation_id) != evaluation):
            raise AuditStorageError("Historical decision/evidence/notification reconstruction failed")
        try:
            reopened.prepare(NotificationPlanRequest(decision_id=record.decision_id))
        except DuplicateNotificationPlan:
            pass
        else:
            raise AuditStorageError("Duplicate notification plan was not rejected")
        print(f"Decision: {record.decision_id} | {record.manager_action} | Final posture: {record.final_posture}")
        print(f"Roster: {impact.total_assigned} assigned | {impact.total_scheduled} scheduled/affected | "
              f"{impact.total_unscheduled} unscheduled/excluded")
        print(f"Roster source: {impact.source} | {impact.source_timestamp.isoformat()} | {impact.data_mode}")
        print(f"Plan: {plan.notification_plan_id} | {plan.status} | {plan.data_mode}")
        print(f"Created: {plan.created_at.isoformat()} | Operating effective time: not recorded")
        for message in plan.messages:
            print(f"{message.group}: {message.count} | {message.status} | route={message.route}")
            print(message.message)
        print("PASS | Plan persisted and exactly reconstructed; original decision and evidence unchanged; duplicate rejected.")
        print("Preparation only. No external delivery calls or real facility status changes.")
        return 0
    except (ValidationError, EmployeeImpactError, NotificationPlanError, ManagerDecisionError, AuditStorageError) as error:
        print(f"FAIL | {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
