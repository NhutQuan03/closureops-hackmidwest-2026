"""Explicit synthetic fixture initialization, restricted to the Docker volume."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.employee_notifications import NotificationPlanRequest, NotificationPlanService
from backend.app.manager_decisions import ManagerDecisionRequest, ManagerDecisionService

DOCKER_DATABASE = Path("/var/lib/closureops/docker-demo.sqlite3")


def initialize_synthetic_fixture(database: Path) -> dict[str, str]:
    """Append one explicitly approved synthetic fixture only to an empty store."""
    if database.exists():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type=?", ("table",))}
            for table in ("manager_evaluations", "manager_decisions", "notification_plans"):
                if table in tables and connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                    raise ValueError("Synthetic initialization requires an empty Docker audit database; existing records are preserved.")
    service = ManagerDecisionService(database, data_mode="SIMULATED DEMO",
                                     demo_scenario="severe_applicable_flood", demo_facility_id="jefferson-research")
    evaluation = service.evaluate_facility("jefferson-research")
    record = service.record_decision(ManagerDecisionRequest(evaluation_id=evaluation.evaluation_id, action="APPROVE"))
    plan = NotificationPlanService(database).prepare(NotificationPlanRequest(decision_id=record.decision_id))
    return {"data_mode": "SIMULATED DEMO", "evaluation_id": evaluation.evaluation_id,
            "decision_id": record.decision_id, "notification_status": plan.status}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize-synthetic-records", action="store_true", required=True)
    parser.parse_args()
    # No HTTP route, arbitrary database argument, credentials, or real delivery.
    if (os.name != "posix" or os.environ.get("CLOSUREOPS_ENVIRONMENT") != "container_readonly"
            or os.environ.get("CLOSUREOPS_LOCAL_DEMO_WRITES") != "false"
            or os.environ.get("CLOSUREOPS_AI_BRIEFING_ENABLED") != "false"
            or Path(os.environ.get("CLOSUREOPS_DEMO_DATABASE", "")).resolve() != DOCKER_DATABASE):
        raise SystemExit("Run this explicit fixture command only inside the configured read-only Docker backend.")
    try:
        print(json.dumps(initialize_synthetic_fixture(DOCKER_DATABASE)))
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
