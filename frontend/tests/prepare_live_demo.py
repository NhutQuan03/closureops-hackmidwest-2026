r"""Prepare isolated trusted evaluations for real-browser GET verification.

Run from the repository root with .\.venv\Scripts\python.exe.
No HTTP writes, manager decisions, weather/model calls, or notifications occur.
Existing application databases are not touched; repeated runs reuse these IDs.
"""
from pathlib import Path
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.manager_decisions import ManagerDecisionService


def main() -> None:
    database = ROOT / "backend/data/command-center-verification.sqlite3"
    manifest = database.with_suffix(".ids.json")
    evaluations = {}
    for scenario, expected_status, expected_posture in (
        ("severe_applicable_flood", "RECOMMENDATION_READY", "FACILITY_CLOSURE"),
        ("missing_evidence", "REVIEW_REQUIRED", None),
    ):
        service = ManagerDecisionService(
            database, data_mode="SIMULATED DEMO", demo_scenario=scenario,
            demo_facility_id="jefferson-research",
        )
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            rows = connection.execute("SELECT snapshot_json FROM manager_evaluations").fetchall()
        snapshots = [json.loads(row[0]) for row in rows]
        saved = next((item for item in snapshots if
            item["result"]["facility_id"] == "jefferson-research" and
            item["data_mode"] == "SIMULATED DEMO" and
            item["result"]["evaluation_status"] == expected_status and
            item["result"]["recommendation"] == expected_posture), None)
        evaluation = service.get_evaluation(saved["evaluation_id"]) if saved else service.evaluate_facility("jefferson-research")
        assert evaluation.result.evaluation_status == expected_status
        assert evaluation.result.recommendation == expected_posture
        evaluations[scenario] = evaluation.evaluation_id
    manifest.write_text(json.dumps(evaluations, indent=2) + "\n", encoding="utf-8")
    print("Prepared SIMULATED DEMO evaluations in " + str(database.relative_to(ROOT)))
    print(json.dumps(evaluations, indent=2))


if __name__ == "__main__":
    main()
