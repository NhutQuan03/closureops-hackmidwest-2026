r"""Export real backend response shapes using only temporary synthetic records.

Run from the repository root:
  .\.venv\Scripts\python.exe frontend/tests/generate_fixtures.py
Nothing in this file is bundled or used as an app fallback.
"""
from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from backend.app.api_security import LocalDemoSettings
from backend.app.main import create_app


def main() -> None:
    with TemporaryDirectory() as directory:
        app = create_app(LocalDemoSettings(writes_enabled=True, database_path=Path(directory) / 'test.sqlite3'))
        with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
            bundle = {name: client.get(path).json() for name, path in [
                ('health', '/api/health'), ('facilities', '/api/facilities'), ('scenarios', '/api/demo/scenarios'),
            ]}
            evaluations = {}
            for scenario in ('normal', 'severe_applicable_flood', 'missing_evidence', 'stale_evidence', 'conflicting_evidence'):
                response = client.post('/api/evaluations', json={'facility_id': 'jefferson-research', 'scenario_id': scenario})
                assert response.status_code == 201, response.text
                evaluations[scenario] = response.json()
            bundle['evaluations'] = evaluations
            # Finalize only in this isolated fixture database, never the app DB.
            closure = client.post(f"/api/evaluations/{evaluations['severe_applicable_flood']['evaluation_id']}/decisions", json={'action': 'APPROVE'})
            assert closure.status_code == 201, closure.text
            plan = client.post(f"/api/decisions/{closure.json()['decision_id']}/notification-plans", json={})
            assert plan.status_code == 201, plan.text
            bundle['notification_plan'] = plan.json()
            bundle['audit'] = client.get('/api/audit').json()
        destination = Path(__file__).parent / 'fixtures' / 'api.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(bundle, indent=2) + '\n', encoding='utf-8')
        print('Exported synthetic API fixtures from a temporary database.')


if __name__ == '__main__':
    main()
