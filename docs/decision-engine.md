# Task 7A: offline deterministic decision engine

`backend/app/decision/engine.py` exposes `evaluate(DecisionInput) -> DecisionResult`.
It performs no I/O, reads no environment variables, calls no LLM, and changes no
facility status. The caller supplies an explicit timezone-aware `evaluated_at`;
identical normalized inputs produce identical serialized results.

This is **PROTOTYPE - NOT OFFICIAL USDA POLICY**. There are no official USDA
operating thresholds or official USGS flood stages in this implementation.
`REVIEW_REQUIRED` is an evaluation status with a null recommendation, never an
operating posture. Every result has `human_approval_required=true`.

## Normalized input and trust boundary

All models in `backend/app/decision/models.py` reject extra fields, control
characters, non-finite numbers, malformed identifiers, invalid coordinates,
naive timestamps, and inconsistent units/intervals. Numeric evidence is numeric,
not numeric text or booleans. Missing sources, exposure, thresholds, and trends
are represented explicitly using nulls or empty observation collections.

Supply:

- Facility ID, name, coordinates, configuration source reference and timestamp,
  and `CONFIGURED` or `SIMULATED DEMO` provenance.
- NWS facility ID, query coordinates, source reference, retrieval timestamp,
  source freshness label, collection status, geographic scope, and normalized
  alert IDs/events/severity/urgency/certainty/effective/expiry times.
- USGS facility ID, numeric gage-height observations (`00065`, feet) with station,
  series, observation/retrieval timestamps, source reference, approval status,
  and freshness label. Discharge (`00060`, cubic feet per second) can be retained
  as a reference but does not select posture in this prototype.
- An optional observed endpoint trend with station and series, both values and
  timestamps, retrieval timestamp, source reference, and freshness label. Its
  interval must span **one to three hours**. The engine requires its final value
  and time to match the latest gage-height observation exactly. Change is
  calculated from the two values; it is not a forecast or inferred rate.
- Explicit facility exposure with facility/station IDs, relationship
  (`REGIONAL_ONLY`, `ACCESS_ROUTE`, or `FACILITY`), documented basis and source
  reference/timestamp/provenance, and optional strictly increasing site-specific
  delay/telework/closure gage triggers in feet.
- Trusted `PrototypeRules` configuration, including a version/policy label,
  freshness windows, and an observed endpoint-rise trigger.

Only trusted server application code may supply geographic scope, exposure, and
rule configuration. They are not client assertions, LLM output, or inferred
meaning from external text. The engine validates scope, facility ID, and exact
query-coordinate equality. `FACILITY_POINT_FILTERED` may be assigned only when
the existing NWS request actually used that selected facility's configured point.
Regional/unknown scope, mismatched IDs or coordinates, and alerts outside
`effective <= evaluated_at < expires` require review. Point applicability does
not establish observed flooding. Real use requires verified facility coordinates
and independently documented exposure; synthetic coordinates remain simulated.

The working NWS/USGS services and Strands tools are unchanged. This phase does
not register an agent tool or add an API route. Raw retrieval dictionaries are
not `DecisionInput`; future application integration must deliberately normalize
the used fields, preserving original labels, references, and times:

- NWS tool status `NO_ACTIVE_ALERTS` maps to collection status `NO_ACTIVE_ALERTS`
  plus source state `LIVE` **only for a successful, sufficiently recent actual
  retrieval**. It is not a safety assessment. NWS `LIVE` maps to `ACTIVE_ALERTS`;
  `UNAVAILABLE` stays unavailable. Freshness is checked again by the engine.
- USGS `evidence_status`, station, series, units, observation time, retrieval
  time, and `source_url` map directly to the corresponding normalized fields.
  Null readings are omitted, not converted to zero. A usable `AVAILABLE` trend
  supplies endpoint values/times; otherwise trend is null. The station/series
  must come from validated observation context, not inferred proximity.
- External descriptions/instructions/qualifiers are not policy inputs. Extra
  raw service fields are excluded during deliberate normalization; they cannot
  be silently passed through the strict decision schema.

The existing `jefferson-research` association with USGS-06910230 remains
**regional monitoring evidence; facility flood exposure not established**. No
triggers or exposure for that real monitoring station have been invented. It
cannot support a recommendation until independently documented configuration
exists; missing exposure or `REGIONAL_ONLY` results in review.

## Rule order

All review guards run before posture rules. Review returns
`evidence_sufficiency=INSUFFICIENT`, or `CONFLICTING` for contradictory evidence.
Recommendations return `SUFFICIENT` for this narrow prototype; this is not a
statistical confidence or general safety guarantee.

| Guard | Behavior |
| --- | --- |
| Missing exposure, thresholds, regional-only exposure, wrong facility, or future configuration | Review |
| Missing/unavailable/stale/future NWS evidence or retrieval older than 15 minutes by default | Review |
| Unvalidated geographic scope, wrong facility/query point, or invalid alert times | Review |
| Unsupported active hazard or unusable severity/urgency/certainty | Review |
| Missing USGS, wrong facility/station, or zero/multiple gage-height series | Review |
| Stale/unavailable/future gage or trend, or observation/retrieval age over 120 minutes by default | Review |
| Missing trend or trend endpoint/station/series disagreement | Review; disagreement is conflicting |
| Applicable severe warning plus gage below delay trigger and endpoint change <= 0 | Review, conflicting signals; neither source is discarded |

Freshness boundaries are inclusive. NWS age uses actual retrieval time; USGS age
uses observation/trend endpoint time **and** retrieval time. A new retrieval
cannot refresh an old observation. Explicit `STALE`, `NO_DATA`, or `UNAVAILABLE`
states never become usable merely because a timestamp is recent. Simulated
evidence must satisfy the same time checks using its synthetic evaluation clock.
A stale demo remains labeled `SIMULATED DEMO` and carries an explicit review reason.

Supported flood events are Flood Warning, Flash Flood Warning, Flood Watch,
Flash Flood Watch, and Flood Advisory. Usable alerts have known severity,
`Immediate`/`Expected` urgency, and `Observed`/`Likely`/`Possible` certainty.
For the severe-warning combination, the event must be Flood Warning or Flash
Flood Warning, severity Severe or Extreme, and certainty Observed or Likely.
Other usable flood alerts support the precautionary delay rule. Other hazards
require review rather than falling through to OPEN.

After the guards, the first matching rule wins:

| Recommendation | PROTOTYPE condition |
| --- | --- |
| `FACILITY_CLOSURE` | Associated gage >= site closure trigger, or applicable severe warning plus gage >= site telework trigger |
| `UNSCHEDULED_TELEWORK` | Gage >= site telework trigger, or applicable severe warning after conflict guards |
| `DELAYED_ARRIVAL` | Gage >= site delay trigger, observed endpoint rise >= configured rise trigger, or any usable applicable flood alert |
| `OPEN` | Complete fresh evidence, documented exposure, no active alerts, gage below delay trigger, and endpoint rise below rise trigger |

Threshold comparisons are inclusive. The default endpoint-rise trigger is
**1.0 ft over the supplied one-to-three-hour observed interval**; it is an
illustrative prototype change trigger, not an official rapid-rise definition.
NWS silence alone never selects OPEN: an elevated associated gage may recommend
delay, telework, or closure even with `NO_ACTIVE_ALERTS`. The exposure requirement
prevents regional USGS observations alone from implying facility flood impact.
Missing trend requires review even if a warning or stage is elevated; this
version deliberately requires complete supporting evidence.

## Outputs and demo fixtures

Results include posture or null, evaluation status, evidence sufficiency,
source references with effective freshness and relevant timestamps, explicit
evaluation time, rule configuration/version, site threshold snapshot, fired
rule IDs with evidence links and reasons, limitations, and human approval flag.
`data_label` is `SIMULATED DEMO` whenever any facility/exposure configuration or
evidence is simulated, including mixed live-source/simulated-facility inputs.
Other labels describe source freshness, not whether operating conditions are safe.

`backend/app/decision/fixtures.py` contains seven independent **SIMULATED DEMO**
scenarios: normal/open, delay, telework, severe applicable flood/closure, missing
evidence, stale evidence, and conflicting signals. All refer to the invented
`demo-flood-facility` and synthetic identifier **USGS-00000000**. The **4/6/8 ft**
site triggers and exposure assumption are invented for this demo and must not
be applied to an actual gauge. No fixture is a live observation.

Example offline use:

```python
from backend.app.decision import evaluate
from backend.app.decision.fixtures import scenario_fixtures

result = evaluate(scenario_fixtures()["severe_applicable_flood"].input)
print(result.model_dump_json(indent=2))  # SIMULATED DEMO recommendation only
```

Run from the repository root using the existing `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_decision_engine.py -q
.\.venv\Scripts\python.exe scripts/test_decision_engine.py
```

No credentials, Strands, Akamai, Bedrock, internet, or manual provider setup are
required. The smoke test checks expected outcomes and truthful demo labels and
exits nonzero on mismatch. Unit tests also block network access and run the
smoke script with provider/HTTP modules unavailable. No frontend, authentication,
approval action, notifications, persistence, or deployment is implemented here.
