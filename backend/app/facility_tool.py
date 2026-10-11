"""Read-only Strands facility tool; execution evidence stays in memory."""

from strands import tool

from backend.app.facilities import lookup_facility

# Minimal smoke-test instrumentation, not a persisted audit record.
execution_events: list[dict[str, str]] = []


@tool
def get_facility(facility_id: str) -> dict[str, object]:
    """Retrieve synthetic facility information by its safe identifier.

    Args:
        facility_id: Lowercase letters, digits and hyphens; 1 to 64 characters.

    Returns:
        Structured SIMULATED DEMO facility data or a controlled lookup error.
    """
    result = lookup_facility(facility_id)
    if result["ok"]:
        execution_events.append({"tool": "get_facility", "facility_id": facility_id})
    return result
