"""In-memory synthetic facility lookup for the first Strands tool demo."""

import re

_FACILITIES = {
    "jefferson-research": {
        "id": "jefferson-research",
        "name": "Jefferson Research Facility",
        "city": "Columbia",
        "state": "Missouri",
        "criticality": "standard",
        "normal_opening": "07:30",
        "timezone": "America/Chicago",
        "latitude": 38.9517,
        "longitude": -92.3341,
        "location_label": "SIMULATED FACILITY LOCATION — Columbia reference point",
        "data_source": "SIMULATED DEMO",
        "source_timestamp": "2026-10-10T18:00:00Z",
        "usgs_monitoring_location_id": "USGS-06910230",
        "usgs_station_name": "Hinkson Creek at Columbia, MO",
        "usgs_facility_relevance_note": (
            "Regional monitoring evidence — facility flood exposure not established."
        ),
    }
}


def lookup_facility(facility_id: str) -> dict[str, object]:
    """Return a copy of demo data or a controlled error without echoing input."""
    if not isinstance(facility_id, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{0,63}", facility_id
    ):
        return {"ok": False, "error": "INVALID_FACILITY_ID"}
    facility = _FACILITIES.get(facility_id)
    if facility is None:
        return {"ok": False, "error": "UNKNOWN_FACILITY_ID"}
    return {"ok": True, "facility": dict(facility)}
