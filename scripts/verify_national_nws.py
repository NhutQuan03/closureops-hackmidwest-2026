"""Explicit real public NWS smoke check; no inference, writes or demo fallback."""
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.national_nws import NationalAlertsResponse
from backend.app.services.nws import fetch_national_nws_alerts


def main() -> int:
    result = NationalAlertsResponse.model_validate(fetch_national_nws_alerts())
    print(json.dumps({
        "source_url": result.source_url, "status": result.status,
        "retrieved_at": str(result.retrieved_at), "fresh_until": str(result.fresh_until),
        "examined_count": result.examined_count, "selection_count": len(result.alerts),
        "collection_limited": result.collection_limited, "error": result.error,
        "events": [alert.event for alert in result.alerts],
        "official_urls": [alert.source_url for alert in result.alerts],
    }, indent=2))
    return 0 if result.status in {"LIVE", "NO_ACTIVE_ALERTS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
