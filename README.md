# ClosureOps

ClosureOps is a human-in-the-loop facility weather operating decision-support prototype for Hack Midwest 2026.

ClosureOps includes a FastAPI backend and a React + TypeScript + Vite command center. All facility data is synthetic demo data.

## Requirements

- Windows PowerShell
- Python 3.12
- Node.js and npm
- The existing `.venv` in this repository

## Backend Setup

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt
python -m pytest --import-mode=importlib -q
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='false'
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001 --no-proxy-headers
```

The read-only Command Center API will be available at `http://127.0.0.1:8001`.
Task 9A write operations are disabled by default. For the complete synthetic
workflow use the exact startup command in [the local API guide](docs/local-demo-api.md).

Useful endpoints:

- `GET http://127.0.0.1:8001/api/health`
- `GET http://127.0.0.1:8001/api/facilities`
- `GET http://127.0.0.1:8001/api/demo/scenarios`
- `GET http://127.0.0.1:8001/api/audit`

The old `jefferson-research-facility` detail URL remains a deprecated read alias
and returns the canonical `jefferson-research` identity. New frontend code must
use the canonical identity for evaluations and employee workflows.

## Frontend Setup

Open a second PowerShell terminal:

```powershell
cd .\frontend
npm install
npm run dev
```

The dashboard will be available at `http://127.0.0.1:5173`.

The dark command center includes Overview, Decision Queue and the explicit
synthetic manager workflow, persisted History inspection, Facilities, saved
Alerts evidence, and loaded-record Reports. It preserves the OpenFreeMap
reference map and user-provided Snoopy artwork. System Settings shows local API
capabilities, integration limitations, and a browser-local reduced-motion option.
See [the operational pages guide](docs/operational-pages.md) and
[manager workflow guide](docs/manager-decision-workflow.md), plus
[system settings guide](docs/system-settings.md), for current behavior,
startup, security boundaries and limitations. Manager actions require the
backend's local-demo write flag; read-only mode remains supported.
Alerts also offers [a read-only nationwide NWS demonstration](docs/live-nws-demonstration.md)
through Refresh Live NWS, clearly separated from historical synthetic facility evidence.
Task 10B adds an explicit Generate AI Briefing action for exactly reproducible
saved demo evaluations. Inference is disabled by default; see the
[private briefing startup and verification guide](docs/browser-ai-briefing.md).

To override the API URL, create a local `.env` file from `.env.example` and set:

```powershell
VITE_API_BASE_URL=http://127.0.0.1:8001
```

Do not put credentials or secrets in frontend environment variables.

## First Strands facility tool (Task 4A)

The read-only `get_facility` tool uses a separate in-memory synthetic dataset
with ID `jefferson-research`. The existing API dataset is unchanged. Its fixed
source timestamp describes demo data, not a live observation.
The tool script imports the working Akamai compatibility model without changing
the connection test. It requires an actual recorded tool execution for success;
provider failures do not trigger a chatbot fallback.

Offline validation (uses the existing Strands/OpenAI-enabled `.venv`):

```powershell
.\.venv\Scripts\python.exe -m pytest scripts/test_akamai_facility_tool_local.py scripts/test_akamai_strands_local.py
.\.venv\Scripts\python.exe scripts/test_akamai_facility_tool.py --check
```

For a private live test, set `AKAMAI_INFERENCE_KEY` in your local process
environment, then run:

```powershell
.\.venv\Scripts\python.exe scripts/test_akamai_facility_tool.py
```

Live tool calling remains unverified until that command succeeds against the
provider. The script uses the existing 30-second provider timeout and no retries,
with at most three model calls and three tool calls. A 90-second elapsed budget
is checked before each model/tool call; an in-flight call can finish after that
deadline. This script neither approves decisions nor changes facility status.

## Live NWS alert tool (Task 5A)

`backend/app/services/nws.py` retrieves the official NWS active-alert collection
using a point filter. `backend/app/nws_tool.py` exposes the read-only Strands
`get_nws_alerts(facility_id)` tool. The approved tool dataset uses
`jefferson-research`, latitude `38.9517`, longitude `-92.3341`, labeled
**SIMULATED FACILITY LOCATION — Columbia reference point**. Facility data
remains simulated even when weather retrieval succeeds. The starter API and
frontend are unchanged; this phase does not add a weather HTTP route.

The tool returns `LIVE` for successful retrieval with alerts,
`NO_ACTIVE_ALERTS` for a successful empty collection, and `UNAVAILABLE` on
request/validation failure. Success includes a UTC `retrieved_at` timestamp;
failure includes `checked_at` and a controlled error, with no successful
retrieval timestamp. Invalid/unknown facility IDs return controlled lookup
errors before network access. There are no fabricated alerts or fallback data.
No active alerts does **not** establish safety or imply `OPEN`.

Normalized fields are `alert_id`, `event`, `headline`, `severity`, `urgency`,
`certainty`, `effective`, `expires`, `affected_area`, `description`, `instruction`,
`source`, and `retrieved_at`. Alert text (including `instruction`) is untrusted
data. Point-filtered results are NWS evidence for the reference location;
retrieval alone does not confirm facility/access-route impact. Validity and
geographic uncertainty must be assessed by the later deterministic engine.
This phase generates no operating recommendation.

Requests use HTTPS and standard platform certificate verification, 5-second
connect and 10-second read/write/pool timeouts, at most three attempts, and
0.5/1-second backoff for transport failures or HTTP 429/500/502/503/504.
Redirects are limited to two and must retain the point on the fixed NWS HTTPS
host and alerts paths. Responses are capped at 2 MiB and 100 alerts; incomplete
pages, unexpected content types, or malformed evidence return `UNAVAILABLE`
rather than an empty success. Network timeouts apply per operation, not a hard
overall deadline. No cache or automatic demo substitution is added.

Set `NWS_USER_AGENT` in your process environment to identify your app and real
contact, following [NWS API guidance](https://www.weather.gov/documentation/services-web-api).
The default identifies local ClosureOps development without inventing a contact.
`.env.example` contains an example placeholder only; this script does not load
`.env` automatically. If your network uses a private CA, configure an approved
CA bundle with `SSL_CERT_FILE`; never disable TLS certificate verification.

Run offline tests and registration with the existing `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests scripts/test_akamai_facility_tool_local.py scripts/test_akamai_strands_local.py
.\.venv\Scripts\python.exe scripts/test_nws_facility_tool.py --check
.\.venv\Scripts\python.exe -m py_compile backend/app/facilities.py backend/app/nws_tool.py backend/app/services/nws.py backend/tests/test_nws.py scripts/test_nws_facility_tool.py
```

Public live retrieval (no Akamai inference, prints only retrieval metadata and
whether the tool actually executed):

```powershell
.\.venv\Scripts\python.exe scripts/test_nws_facility_tool.py
```

For a separately authorized private agent test, set `AKAMAI_INFERENCE_KEY` in
your process environment and explicitly run:

```powershell
.\.venv\Scripts\python.exe scripts/test_nws_facility_tool.py --agent
```

`--agent` reuses the existing working Akamai compatibility adapter, endpoint,
model, token limit, and provider timeout unchanged. It registers only the NWS
tool and requires recorded tool execution, successful NWS retrieval, and a
nonempty agent response. It prints no model output, raw alerts, credentials,
or request headers. The smoke agent permits three model calls and two tool
calls with a 90-second budget checked before each call. An in-flight call can
finish after that deadline. Authenticated inference is not needed for NWS and
was not run during implementation; genuine provider tool calling remains a
manual check.

## USGS regional flood evidence (Task 6A)

`backend/app/services/usgs.py` uses the modern USGS Water Data API at
`https://api.waterdata.usgs.gov/ogcapi/v1/`. The read-only Strands tool
`get_usgs_conditions(facility_id)` resolves `jefferson-research` through the
server-owned facility configuration to **USGS-06910230, Hinkson Creek at
Columbia, MO**. This is an explicit regional monitoring association, not proof
of facility or access-route exposure. Every observation retains this note:
**Regional monitoring evidence — facility flood exposure not established.**
Facility data remains `SIMULATED DEMO`; public USGS observations are labeled
independently. The existing facility/NWS tools, Akamai adapter, starter HTTP
API, and frontend remain intact. No recommendation, decision, flood threshold,
deployment, or notification behavior is added.

Latest readings use `latest-continuous/items` with documented `f=json`,
`monitoring_location_id`, `parameter_code=00065,00060`, and `limit` filters.
Parameter `00065` is gage height (`ft`), and `00060` is discharge (`ft^3/s`).
Historical `continuous/items` is requested only when exactly one usable latest
gage-height series exists, filtered to that station, parameter, `time_series_id`,
and an explicit three-hour `time=start/end` interval ending at the latest
observation. See the [USGS API guide](https://api.waterdata.usgs.gov/docs/ogcapi/)
and [v1 OpenAPI parameter definitions](https://api.waterdata.usgs.gov/ogcapi/v1/openapi?f=html).

Normalized observations contain `monitoring_location_id`, `station_name`,
`parameter_code`, numeric `value`, `unit`, `observation_timestamp`, `retrieved_at`,
`approval_status`, `qualifier`, `source=USGS`, `source_url`, `evidence_status`,
`facility_relevance_note`, and `time_series_id`. The configured station name
is used; no untrusted upstream URL is fetched or returned as a source URL.
An absent/unusable parameter gets an explicit placeholder with null observation
fields rather than an invented reading. Malformed individual observations are
counted and rejected; malformed collections are service failures.

Observation states:

- `LIVE`: timestamp is not in the future and age is at most the configured window.
- `STALE`: a valid observation exists but its observation time is older than the window.
- `NO_DATA`: successful retrieval, but no usable reading for that parameter.
- `UNAVAILABLE`: request, collection validation, or local configuration failure.

`USGS_FRESHNESS_MINUTES` is server-side configuration, default **120**, allowed
integer range **1–1440**. This is a prototype freshness setting, not official
USDA policy or a flood threshold. The scripts read process environment variables;
they do not load `.env` automatically. Retrieval time, `last_modified`, and HTTP
success never substitute for observation time. The aggregate `status` is
conservative: a missing parameter yields `NO_DATA`; otherwise any stale reading
yields `STALE`; only all recent readings yield `LIVE`. Individual states always
remain available. `ok=true` denotes successful latest collection retrieval,
including `STALE` and `NO_DATA`, not sufficient evidence for an operating decision.

A trend needs at least two distinct, finite gage-height observations from the
same series, spanning at least one hour within the three-hour query window.
The last historical point must match the latest observation's time and value.
The result reports observed endpoint change in feet, both values/timestamps,
actual elapsed seconds, observation count, query window, source URL, retrieval
time, and freshness. It is an endpoint difference, not an inferred rapid-rise
rate or flood classification. Insufficient, conflicting, ambiguous, or incomplete
history yields `trend.status=UNAVAILABLE` and `change_feet=null`. Historical
request failure preserves valid latest readings. No interpolation or demo
substitution occurs.

Requests use fixed server-constructed HTTPS URLs with TLS verification,
5-second connect and 10-second read/write/pool timeouts, at most two attempts
per collection, and 0.5-second retry backoff for transport failures or HTTP
429/500/502/503/504. Redirects are refused. Each response is bounded to 2 MiB
and 1,000 observations; incomplete pages are refused without following links.
Timeouts are per network operation, not a hard overall deadline. There is no
cache or automatic simulated fallback. Public unauthenticated retrieval needs
no credentials and may be rate limited by USGS.

Offline validation with the existing `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests scripts/test_akamai_facility_tool_local.py scripts/test_akamai_strands_local.py
.\.venv\Scripts\python.exe scripts/test_usgs_facility_tool.py --check
.\.venv\Scripts\python.exe -m py_compile backend/app/facilities.py backend/app/services/usgs.py backend/app/usgs_tool.py backend/tests/test_usgs.py scripts/test_usgs_facility_tool.py
```

Live public USGS tool test, with no Akamai inference:

```powershell
.\.venv\Scripts\python.exe scripts/test_usgs_facility_tool.py
```

Optional, separately authorized authenticated agent test (not run during Task 6A):

```powershell
.\.venv\Scripts\python.exe scripts/test_usgs_facility_tool.py --agent
```

`--agent` reads `AKAMAI_INFERENCE_KEY` from the process environment and reuses
the existing adapter/model/endpoint with an explicit **1024 output token** budget.
The shared Akamai smoke-test default remains **150** (see Task 7B below). Only the read-only
USGS tool is registered. The smoke test requires an actual in-memory execution
event for the configured facility and successful latest retrieval; plausible
model prose alone fails. `UNAVAILABLE` fails the smoke test. `STALE` and `NO_DATA`
remain truthful successful retrieval states. Provider output, credentials,
headers, and raw external qualifiers are never printed. The agent allows at
most three model calls and two tool calls, with a 90-second elapsed budget
checked before calls; in-flight calls can finish after the deadline. `--check`
registers the tool offline without reading credentials or invoking the model.
Authenticated provider tool calling is still a manual check.

### Task 6D: private USGS agent diagnostics

Run the opt-in diagnostic mode privately, with `AKAMAI_INFERENCE_KEY` already
set in the process environment:

```powershell
.\.venv\Scripts\python.exe scripts/test_usgs_facility_tool.py --agent --diagnose
```

`--diagnose` requires `--agent` or `--check`; it does not itself authorize
inference. `--check --diagnose` registers the diagnostic tool offline without
reading credentials or invoking USGS/the model. Task 6D performed only offline
tests, not authenticated inference. The existing Akamai adapter, tool schema,
prompt, model parameters, tool/call budgets, service and evidence are unchanged.

Lines prefixed `DIAG` contain only safe metadata. `model_request_1` and subsequent
numbered stages mark the Strands before/after model hooks. These encompass
request formatting, transport and SDK response parsing; they do not prove an
HTTP request reached the provider. `get_usgs_conditions entered` marks actual
function entry after SDK input validation. Completion is followed by
`tool_result_serialization` (return type, serialized UTF-8 bytes and aggregate
value-type/depth/list counts) and `tool_result_wrapping` (SDK envelope type,
block counts and text-content bytes). `agent_response` records final completion
or failure, including the failed stage. Sizes measure tool content using the
SDK's JSON serialization, not full HTTP bodies or token counts. No evidence
keys/values, prompts, provider prose/responses, requests, headers or credentials
are printed in this mode. Errors expose only stage, exception classes,
allowlisted category and HTTP status, when available.

Strands can wrap second-call failures in `EventLoopException`, which hides the
original HTTP metadata from the previous top-level reporter. Diagnostics read
a bounded, cycle-safe exception chain, including `original_exception`, without
reading request state or formatting exception messages. The before/after hooks
report caught tool failures too: Strands can continue to a final response after
a tool error. Existing smoke-test exit criteria remain execution evidence,
retrieval state and a nonempty response; inspect failed `DIAG` stages even when
the exit code is zero. Diagnostic serialization errors preserve the SDK's
existing fallback and never truncate or replace evidence.

Offline synthetic-fixture comparison (not measurements from the working live
agent runs):

| Tool result | UTF-8 bytes | Maximum depth | Dictionaries / lists |
| --- | ---: | ---: | ---: |
| Facility | 629 | 2 | 2 / 0 |
| NWS, no alerts | 493 | 1 | 1 / 1 |
| NWS, one synthetic alert | 946 | 3 | 2 / 1 |
| USGS, two synthetic observations and available trend | 2,931 | 3 | 4 / 1 |

USGS is about 4.7 times the facility result and 3.1 times this one-alert NWS
fixture. Its observation entries and trend dictionary contain repeated source,
relevance and timestamp metadata. All three return dictionaries serialized by
Strands into one JSON text block; there is no distinct USGS provider message
format. NWS size varies with alert count/text and USGS size with usable series
and qualifiers. These measurements do not establish a provider size limit or
the live failure's cause. The private run is required to identify its stage.

Offline checks with the existing `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests scripts/test_akamai_facility_tool_local.py scripts/test_akamai_strands_local.py -q
.\.venv\Scripts\python.exe scripts/test_usgs_facility_tool.py --check --diagnose
.\.venv\Scripts\python.exe -m py_compile scripts/test_usgs_facility_tool.py scripts/usgs_diagnostics.py backend/tests/test_usgs_diagnostics.py
```

Diagnostic tests use the real Strands event loop/adapter with mocked inference
and public-data transports, and block unmocked HTTP transports. Coverage
includes first/second model failures, response parsing failure, real function
entry, SDK-caught tool failures, result wrapping, UTF-8 sizes, payload/spec
preservation, serialization fallback, tool budgets and safe error chains.

## Offline deterministic decision engine (Task 7A)

`backend/app/decision/engine.py` evaluates validated normalized facility, NWS,
USGS, exposure, and explicit **PROTOTYPE** rules without Strands, Akamai,
Bedrock, credentials, or internet access. It returns `OPEN`, `DELAYED_ARRIVAL`,
`UNSCHEDULED_TELEWORK`, or `FACILITY_CLOSURE` recommendations, or a separate
`REVIEW_REQUIRED` status with a null recommendation for insufficient or
conflicting evidence. Every result requires human approval; no status is changed.
NWS/USGS retrieval is unchanged. No API/agent integration is added in this phase.

See [the decision-engine contract and documented rule order](docs/decision-engine.md)
for applicability checks, timestamps, exposure requirements, prototype thresholds,
limitations, and seven explicitly labeled **SIMULATED DEMO** scenarios. The existing
regional USGS association has no invented facility exposure or flood-stage triggers.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_decision_engine.py -q
.\.venv\Scripts\python.exe scripts/test_decision_engine.py
```

## Token configuration regression (Task 7B)

`scripts/test_akamai_strands.py` exposes
`build_model(openai_model, api_key, max_output_tokens=150)`. The Akamai connection,
facility, and NWS scripts retain the original 150-token smoke budget. The USGS
script explicitly requests 1024 for both agent and offline registration modes,
preserving the budget that resolved the reported `MaxTokensReachedException`.
The new argument rejects nonpositive integers, booleans, and noninteger values
before model construction; previously there was no local token-value validation.
No token environment variable or credential setup is added. Empty-tool omission,
nonempty tool definitions, timeouts, retries, evidence retrieval, and decision
rules are unchanged.

Run all local tests with importlib collection to avoid the existing duplicate
`test_decision_engine.py` basenames in `backend/tests` and `scripts`:

```powershell
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q
.\.venv\Scripts\python.exe scripts/test_decision_engine.py
```

The tests use mocked transports and dummy keys; authenticated inference is a
separate private verification and was not run for Task 7B.

## Strands decision tool and manager briefing (Task 7C)

`backend/app/decision_tool.py` adds the read-only Strands tool
`evaluate_operating_status(facility_id)`. Application code binds its mode and
demo scenario with `create_decision_tool`; the agent cannot supply weather,
measurements, thresholds, exposure, rules, timestamps, mode or scenario.
The tool validates the original SDK invocation with an extra-forbidding schema,
including fields the SDK's generated input model would otherwise ignore.
It calls the unchanged deterministic engine and returns every original output,
plus `recommended_posture` (an alias for `recommendation`), `data_mode`, normalized
`supporting_evidence`, `source_timestamps`, source acquisition checks, and
separate integration limitations. In-memory execution snapshots are independent
copies for the smoke test, not approvals or persisted audit records.

`SIMULATED DEMO` uses the existing seven fixed-clock fixtures and invented
`demo-flood-facility`/`USGS-00000000` association. `LIVE_EVIDENCE` retrieves
NWS and USGS independently through the existing services for
`jefferson-research`. It uses point-filtered NWS coordinates and validity/freshness
checks in the engine, retains regional USGS relevance, and adds no site exposure
or thresholds. **The live pathway currently returns `REVIEW_REQUIRED`** because
regional monitoring alone cannot establish exposure. The facility remains
synthetic: `data_mode=LIVE_EVIDENCE` describes acquisition, while the engine's
`data_label=SIMULATED DEMO` preserves configuration provenance. Individual source
references independently report `LIVE`, `STALE`, or unavailable evidence.
Retrieval/normalization failures preserve the other source and require review;
no fixture fallback occurs in live mode.

The agent has only this tool, 1024 output tokens, no provider retries and a
30-second provider timeout. Hooks allow at most three model calls and two tool
calls, checking a 90-second elapsed budget before each call. In-flight provider
or public-source operations can exceed that elapsed boundary; the existing
services retain their own timeouts and bounded retries.

`backend/app/decision_briefing.py` validates a strict JSON agent response against
the actual tool execution: facility, status, posture, sufficiency, mode, approval
flag, all fired rule IDs and their evidence references must match. Model prose,
invented references, extra fields, duplicate selections and changed conclusions
are rejected. The application renders the manager explanation from authoritative
rule reasons, source references, timestamps and limitations. A rejected response
after tool execution produces a deterministic fallback briefing and a nonzero
smoke-test exit code. Provider prose alone, or multiple evaluation executions,
cannot pass. No agent approval, override, notification or status mutation is added.

Offline commands (no credentials or requests to public/inference services):

```powershell
.\.venv\Scripts\python.exe scripts/test_akamai_decision_tool.py
.\.venv\Scripts\python.exe scripts/test_akamai_decision_tool.py --scenario severe_applicable_flood
.\.venv\Scripts\python.exe scripts/test_akamai_decision_tool.py --check
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q
.\.venv\Scripts\python.exe scripts/test_decision_engine.py
```

Private Akamai test with the existing process-level `AKAMAI_INFERENCE_KEY`:

```powershell
# Authenticated inference using explicitly simulated evidence:
.\.venv\Scripts\python.exe scripts/test_akamai_decision_tool.py --agent --scenario severe_applicable_flood
# Authenticated inference using public NWS/USGS evidence for the synthetic facility:
.\.venv\Scripts\python.exe scripts/test_akamai_decision_tool.py --agent --live-evidence
```

`--live-evidence` alone retrieves public data and renders a deterministic briefing
without inference; it cannot be combined with `--scenario`. `--check`, including
`--check --live-evidence`, registers offline without retrieving evidence or reading
credentials. Task 7C verification uses synthetic transports and mocked inference;
actual authenticated provider execution remains a private manual check.

## Human manager actions and local audit history (Task 8A)

`backend/app/manager_decisions.py` provides an in-process local demo service.
It reuses the existing read-only evaluation tool and unchanged deterministic
engine; no policy is duplicated. `ManagerDecisionService.evaluate_facility(id)`
captures a trusted evaluation in SQLite and returns a server-generated evaluation
ID. Only evaluations generated through this service are actionable: Task 7C tool
outputs, agent prose, in-memory ledgers, and client-provided snapshots cannot be
imported as trusted evaluations. No Strands approval tools or HTTP write routes
were added. Existing NWS/USGS services and the Akamai adapter are unchanged.

Application code supplies an explicit `ManagerDecisionRequest` to
`record_decision` containing the evaluation ID and one of:

- `APPROVE`: records the existing recommendation without changing its posture.
- `OVERRIDE`: requires a different `OperatingPosture` and a 1–500 character reason.
- `ACKNOWLEDGE_REVIEW`: accepts only `REVIEW_REQUIRED`, records no final posture,
  and acknowledges that a human investigation is needed.

`REVIEW_REQUIRED` cannot be approved or overridden. Manual operating decisions
on insufficient evidence are outside Task 8A. Requests reject unexpected fields,
unsupported postures, control characters, blank reasons, supplied manager identity,
recommendations, evidence, policy, and timestamps. The service assigns the fixed
**Synthetic Demo Manager** identity; this identity is not authentication.

The minimal new SQLite schema has immutable evaluation and decision tables;
the schema is needed because the prototype previously had no persistence module.
The default database is `backend/data/manager-decisions.sqlite3`, outside
frontend/public and ignored by Git along with journal/WAL/SHM files. No dependency
or environment variable is added. The service creates the directory/database on
first use. A custom database path is a trusted application setting, never a client
field; frontend/public paths are rejected.

Each audit record retains evaluation/decision/facility IDs, evaluation status,
original recommendation, explicit manager action, selected posture (if any),
override reason, synthetic manager identity, decision time, acquisition mode,
original normalized evidence, source timestamps/checks, integration limitations,
and the full engine result including original thresholds, rules, and approval
requirement. Historical source freshness labels describe the evaluation snapshot,
not current weather. `get_evaluation`, `get_decision`, and bounded/filterable
`list_history` reconstruct history without fetching data or rerunning the engine.

Parameterized inserts, a unique evaluation-to-decision constraint, and a serialized
write transaction prevent duplicate final actions across service instances.
Database triggers reject update, delete, and replacement of stored evaluations
and finalized decisions. There is no editing/deletion service method. An
acknowledgment also finalizes that evaluation's audit action; subsequent evidence
or review requires a new evaluation, preserving the original history.

Offline smoke commands (synthetic evidence; no credentials, network, facility
status changes, or notifications):

```powershell
# Default: persist an evaluation only; no manager action is assumed.
.\.venv\Scripts\python.exe scripts/test_manager_decision.py
# Explicit synthetic manager actions, each on a new evaluation:
.\.venv\Scripts\python.exe scripts/test_manager_decision.py --action approve
.\.venv\Scripts\python.exe scripts/test_manager_decision.py --action override --posture UNSCHEDULED_TELEWORK --reason "Synthetic manager verified an alternate access route."
.\.venv\Scripts\python.exe scripts/test_manager_decision.py --scenario missing_evidence --action acknowledge-review
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q
.\.venv\Scripts\python.exe scripts/test_decision_engine.py
```

Each action smoke test reopens SQLite and verifies exact record/evidence
reconstruction. Repeated CLI runs append new evaluations/decisions. These actions
only record synthetic decisions; they never mutate the facility catalog or real
operating status. No frontend, employee grouping/notifications, authentication,
deployment, or public decision-write endpoints are part of this phase. Keep this
service local; a future public API must enforce backend authorization. SQLite
triggers prevent accidental application rewrites, but are not cryptographic
tamper protection against someone who can directly alter the database/schema.

## Employee impact and simulated notification preparation (Task 8B)

`backend/app/employee_impact.py` defines a deterministic, entirely synthetic
Jefferson Research Facility demonstration-shift roster: **54 assigned, 47 scheduled,
7 unscheduled**. Scheduled groups compute to **31 telework eligible, 10 standard
onsite, 6 essential personnel**. Essential designation takes precedence over
telework eligibility; each scheduled employee belongs to exactly one group.
The resolver computes counts from employee attributes, supports empty rosters,
and rejects invalid/unknown facility IDs, duplicate employee IDs and mismatched
roster membership. `scheduled_today` means the fixed demonstration shift, not the
computer's current date. Synthetic preferences have no real addresses or phone
numbers and never select a delivery provider. The fixture carries its source,
fixed source timestamp and `SIMULATED DEMO` label.

The existing manager service/tool can now bind `demo_facility_id="jefferson-research"`
as trusted application configuration in `SIMULATED DEMO` mode. This explicitly
rebases the existing invented scenario to Jefferson, preserving readings, clock,
rules and prototype thresholds. It uses the **invented USGS-00000000 gauge and
invented access-route exposure**, not Jefferson's actual regional monitoring
association. All labels remain simulated. The default demo-flood-facility and
live-evidence behavior are unchanged; the new binding is rejected in live mode.
There is no client evidence-import path or change to NWS/USGS retrieval.

`backend/app/employee_notifications.py` provides an in-process local-only service:

```python
plans = NotificationPlanService(database_path)
plan = plans.prepare(NotificationPlanRequest(decision_id=saved_decision_id))
restored = plans.get_plan(plan.notification_plan_id)
same_plan = plans.get_plan_for_decision(saved_decision_id)
```

Preparation loads and validates the existing SQLite decision and its evaluation.
Only finalized `APPROVE` and `OVERRIDE` actions with a supported final posture
are accepted; review acknowledgments and unfinalized/missing IDs are rejected.
The request rejects supplied facility, posture, identity, effective time, counts,
evidence and message text. Overrides use the saved **manager-selected posture**.
Only Jefferson has a roster in this phase; other facilities are rejected rather
than substituted. No approval, preparation or sending tool is registered with
Strands, and no HTTP write/upload route or messaging provider is added.

Versioned deterministic templates cover all four postures and all three groups.
Messages identify the facility, final posture, group, instruction, decision
reference and `SIMULATED DEMO`. Essential personnel must confirm assignments and
access authorization with authorized management before travel/entry. A closure
does not automatically assign remote work; staff await management instructions.
The existing manager schema records no operating effective time, so `effective_at`
is null and messages say **Effective time: not recorded**. Neither the decision
timestamp, normal opening nor a weather alert's effective time supplies that time.
Delayed-arrival messages require management confirmation of the revised time.
No LLM generates or modifies these messages.

The additive `simulated_notification_plans` SQLite table links each plan to a
finalized decision with a foreign key and unique decision ID. Serialized writes
prevent concurrent duplicates; triggers reject updates, deletions, replacements
and links inconsistent with the saved facility/posture. Original evaluations,
decisions, evidence and timestamps remain untouched. Persisted aggregate counts,
roster provenance, exact messages, creation timestamp and template version allow
exact reconstruction after restart without reloading the roster or rerunning
evaluation. Individual employee identities/preferences are not saved in plans.
All plan and message statuses are **GENERATED_SIMULATED**, with `route=simulated`;
nothing is queued or marked delivered. There is no delivery function.

From the repository root, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q
# Explicit synthetic manager approval on a new evaluation; no inference/network:
.\.venv\Scripts\python.exe scripts/test_employee_notifications.py --action approve
```

The smoke demonstration executes recommendation -> explicit synthetic approval ->
computed grouping -> prepared plan -> persisted/reconstructed history, and checks
duplicate rejection. It defaults to a separate ignored database,
`backend/data/employee-notifications-demo.sqlite3`, preserving previous Task 8A
records. Repeated runs append new evaluations/decisions/plans. Without `--action
approve` it only evaluates and records no manager action or notification plan.
`--scenario normal`, `delayed_arrival`, `unscheduled_telework`, or
`severe_applicable_flood` selects existing prototype scenarios; `--database` is
trusted local CLI configuration. No new dependency, credential or manual setup
is required. This phase has no frontend, authentication, public endpoints,
deployment or real delivery. Database triggers remain protection against
accidental rewrites, not cryptographic protection from a database administrator.

## Local FastAPI workflow (Task 9A)

The local API now exposes trusted synthetic evaluations, human approval/override/
review acknowledgment, exact SQLite decisions, computed employee impact in
simulated notification plans, and bounded audit history. It reuses the Task 8A/8B
services and the existing explicit Jefferson synthetic scenario binding. No
decision rules, retrieval logic, inference adapter, schema or dependencies were
changed. Manager and notification services remain unavailable as agent tools.

See [the API guide](docs/local-demo-api.md) for the exact Windows launch command,
endpoint sequence, payloads, provenance, local security boundary and limitations.
Swagger is served locally at `http://127.0.0.1:8001/docs`.

```powershell
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q
.\.venv\Scripts\python.exe -m py_compile backend/app/main.py backend/app/api.py backend/app/api_security.py backend/tests/test_demo_api.py
.\.venv\Scripts\python.exe scripts/test_employee_notifications.py --action approve
```

The full synthetic workflow requires no credentials, public data requests or
authenticated inference. Notifications are prepared and persisted with
`GENERATED_SIMULATED` status; nothing is sent, queued or marked delivered.
This task changes no frontend and does not deploy or configure production auth.

## Build Checks

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest .\backend\tests
cd .\frontend
npm run build
```
