"""Export deterministic briefing fixtures; no model, database writes, or network."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.ai_briefing import response_for
from backend.app.manager_decisions import TrustedEvaluation


def main() -> None:
    folder = Path(__file__).parent / "fixtures"
    saved = json.loads((folder / "api.json").read_text(encoding="utf-8"))["evaluations"]
    responses = {
        scenario: response_for(
            TrustedEvaluation.model_validate(evaluation), "VALIDATED", "OK",
            confirmed=True, completed=True, validation="VALIDATED",
        ).model_dump(mode="json")
        for scenario, evaluation in saved.items()
    }
    # Stable synthetic response clock, not a claimed real agent execution time.
    for response in responses.values():
        response["generated_at"] = "2026-10-11T07:00:00Z"
    (folder / "situation-briefings.json").write_text(
        json.dumps(responses, indent=2) + "\n", encoding="utf-8",
    )
    print("Exported offline briefing fixtures from saved synthetic API fixtures.")


if __name__ == "__main__":
    main()
