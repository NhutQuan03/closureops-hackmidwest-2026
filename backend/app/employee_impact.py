"""Deterministic synthetic roster and scheduled-shift grouping; no contact data."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, TypeAdapter, model_validator

from backend.app.decision.fixtures import DEMO_TIME
from backend.app.decision.models import FacilityId, Model, Text, TimedModel, Timestamp
from backend.app.facilities import lookup_facility

EmployeeId = Annotated[StrictStr, Field(pattern=r"^synthetic-[a-z0-9-]{1,48}$")]
Count = Annotated[StrictInt, Field(ge=0)]


class EmployeeGroup(StrEnum):
    ESSENTIAL_PERSONNEL = "ESSENTIAL_PERSONNEL"
    TELEWORK_ELIGIBLE = "TELEWORK_ELIGIBLE"
    STANDARD_ONSITE = "STANDARD_ONSITE"


class SyntheticEmployee(Model):
    employee_id: EmployeeId
    synthetic_name: Text
    role: Text
    facility_id: FacilityId
    scheduled_today: StrictBool
    telework_eligible: StrictBool
    essential_employee: StrictBool
    notification_preference: Literal["email", "sms", "onscreen"]
    data_mode: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"


class SyntheticRoster(TimedModel):
    facility_id: FacilityId
    employees: tuple[SyntheticEmployee, ...]
    source: Literal["ClosureOps synthetic demonstration shift fixture"] = "ClosureOps synthetic demonstration shift fixture"
    source_timestamp: Timestamp = DEMO_TIME
    data_mode: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"

    @model_validator(mode="after")
    def valid_membership(self) -> SyntheticRoster:
        ids = [employee.employee_id for employee in self.employees]
        if len(ids) != len(set(ids)):
            raise ValueError("Roster employee IDs must be unique")
        if any(employee.facility_id != self.facility_id for employee in self.employees):
            raise ValueError("Roster employees must belong to the selected facility")
        return self


class ImpactGroup(Model):
    group: EmployeeGroup
    employee_ids: tuple[EmployeeId, ...]
    count: Count

    @model_validator(mode="after")
    def valid_count(self) -> ImpactGroup:
        if self.count != len(self.employee_ids) or self.count != len(set(self.employee_ids)):
            raise ValueError("Group count must match unique employees")
        return self


class EmployeeImpact(TimedModel):
    facility_id: FacilityId
    total_assigned: Count
    total_scheduled: Count
    total_unscheduled: Count
    total_affected: Count
    groups: tuple[ImpactGroup, ...]
    source: Literal["ClosureOps synthetic demonstration shift fixture"]
    source_timestamp: Timestamp
    data_mode: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"

    @property
    def group_counts(self) -> dict[EmployeeGroup, int]:
        return {group.group: group.count for group in self.groups}

    @model_validator(mode="after")
    def valid_partition(self) -> EmployeeImpact:
        if tuple(group.group for group in self.groups) != tuple(EmployeeGroup):
            raise ValueError("Impact must include each employee group exactly once in precedence order")
        ids = [employee_id for group in self.groups for employee_id in group.employee_ids]
        if (len(ids) != len(set(ids)) or len(ids) != self.total_scheduled
                or self.total_affected != self.total_scheduled
                or self.total_assigned != self.total_scheduled + self.total_unscheduled):
            raise ValueError("Scheduled employees must form an exclusive and complete partition")
        return self


class EmployeeImpactError(ValueError):
    pass


def load_facility_roster(facility_id: str) -> SyntheticRoster:
    """Load only a known facility's invented shift; preferences imply no delivery."""
    facility_id = TypeAdapter(FacilityId).validate_python(facility_id)
    if not lookup_facility(facility_id)["ok"]:
        raise EmployeeImpactError("Unknown roster facility")
    employees = []
    # These ranges define the fixture, not the grouping algorithm.
    for index in range(1, 55):
        essential = 42 <= index <= 47
        telework = index <= 31
        employees.append(SyntheticEmployee(
            employee_id=f"synthetic-jefferson-{index:03d}",
            synthetic_name=f"Synthetic Employee {index:03d}",
            role="Essential operations" if essential else "Research support" if telework else "Onsite support",
            facility_id=facility_id, scheduled_today=index <= 47,
            telework_eligible=telework, essential_employee=essential,
            notification_preference=("email", "sms", "onscreen")[(index - 1) % 3],
        ))
    return SyntheticRoster(facility_id=facility_id, employees=tuple(employees))


def group_scheduled_employees(roster: SyntheticRoster) -> EmployeeImpact:
    """Compute counts from any validated roster, including an empty roster."""
    roster = SyntheticRoster.model_validate(roster.model_dump(mode="python", warnings=False))
    grouped: dict[EmployeeGroup, list[str]] = {group: [] for group in EmployeeGroup}
    for employee in roster.employees:
        if not employee.scheduled_today:
            continue
        if employee.essential_employee:
            group = EmployeeGroup.ESSENTIAL_PERSONNEL
        elif employee.telework_eligible:
            group = EmployeeGroup.TELEWORK_ELIGIBLE
        else:
            group = EmployeeGroup.STANDARD_ONSITE
        grouped[group].append(employee.employee_id)
    scheduled = sum(len(ids) for ids in grouped.values())
    return EmployeeImpact(
        facility_id=roster.facility_id, total_assigned=len(roster.employees),
        total_scheduled=scheduled, total_unscheduled=len(roster.employees) - scheduled,
        total_affected=scheduled,
        groups=tuple(ImpactGroup(group=group, employee_ids=tuple(ids), count=len(ids))
                     for group, ids in grouped.items()),
        source=roster.source, source_timestamp=roster.source_timestamp,
    )


def resolve_employee_impact(facility_id: str) -> EmployeeImpact:
    """Load the facility roster and resolve the synthetic demonstration shift."""
    return group_scheduled_employees(load_facility_roster(facility_id))
