# Task 9A local demo API

From the repository root in Windows PowerShell, launch the complete synthetic
workflow with this exact command:

```powershell
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='true'; $env:CLOSUREOPS_DEMO_DATABASE='backend/data/manager-workflow-demo.sqlite3'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
```

Swagger: <http://127.0.0.1:8001/docs>. OpenAPI: <http://127.0.0.1:8001/openapi.json>.
Task 9B.1-F uses this origin with writes **disabled**; see the
[Command Center startup guide](command-center-frontend.md). Port 8000 may still
host an older API and is rejected by the frontend.
Task 9B.2 connects the interactive React workflow using the separate demo database
above; see the [manager workflow guide](manager-decision-workflow.md).
`GET /api/health` now includes server-owned `local_demo_writes_enabled` (boolean).
This is an advisory capability for UI controls, not authentication or permission
to bypass the existing local write guards. Older running servers must be restarted;
the frontend treats an absent capability as read only.
Use Ctrl+C to stop the server. The startup command opts into writes for this
PowerShell session. Set `$env:CLOSUREOPS_LOCAL_DEMO_WRITES='false'` and restart
to disable writes again. Without an explicit true flag, all POST routes return
403. The application defaults to `CLOSUREOPS_ENVIRONMENT=local_demo` and
`CLOSUREOPS_BIND_HOST=127.0.0.1`; incompatible public/production or bind settings
raise an error at application creation even when writes are disabled.

No new dependency or credential setup is needed in the verified `.venv`.
No Akamai, AWS, NWS or USGS requests occur in the synthetic manager workflow.
Task 10A adds the separate read-only `GET /api/nws/alerts/active` nationwide
NWS demonstration. It makes public NWS requests only when explicitly refreshed
in Alerts, and is never applied to saved facility evaluations. See
[the live NWS guide](live-nws-demonstration.md).
The existing Strands SDK must be installed because the trusted evaluation
service reuses its read-only tool locally, without constructing a model/agent.
Task 10B separately adds optional, explicitly triggered Strands/Akamai inference
at `POST /api/evaluations/{evaluation_id}/ai-briefing` with body `{}`. It requires
the server-only `CLOSUREOPS_AI_BRIEFING_ENABLED=true` flag as well as the existing
local write opt-in. Health reports advisory `ai_briefing_enabled`; an absent flag
is treated as disabled by the frontend. Credentials are never returned or checked
by health. See [the private briefing guide](browser-ai-briefing.md) for exact
startup, snapshot validation, limits, and offline verification.

## React endpoint sequence

All write requests use `Content-Type: application/json`. Read lists are JSON
arrays; persisted records use the existing Pydantic models without flattening or
reinterpreting their evidence. Creation returns 201 and a relative `Location`
header; successful reads return 200.

1. `GET /api/health` verifies service availability.
2. `GET /api/facilities` loads the allowlisted `jefferson-research` facility.
3. `GET /api/demo/scenarios` loads the seven allowlisted scenario IDs, their
   expected results, fixed fixture clock, sources and simulation disclosure.
4. `POST /api/evaluations` creates and persists a trusted evaluation:

   ```json
   {"facility_id":"jefferson-research","scenario_id":"severe_applicable_flood"}
   ```

   Store the returned `evaluation_id`. Display `result.recommendation`,
   `result.evaluation_status`, `result.evidence_sufficiency`, `result.data_label`,
   `result.triggered_rules`, `result.rules.policy_label`, `evidence_snapshot`,
   `source_timestamps` and `integration_limitations`. Retrieve the exact saved
   result with `GET /api/evaluations/{evaluation_id}`.
5. After an explicit human click, `POST /api/evaluations/{evaluation_id}/decisions`:

   ```json
   {"action":"APPROVE"}
   ```

   Alternatively, a different supported posture and short reason are required:

   ```json
   {"action":"OVERRIDE","selected_posture":"UNSCHEDULED_TELEWORK","reason":"Synthetic manager confirmed alternate arrangements."}
   ```

   Supported postures: `OPEN`, `DELAYED_ARRIVAL`, `UNSCHEDULED_TELEWORK`,
   `FACILITY_CLOSURE`. Approval preserves the engine recommendation. Override
   preserves the original recommendation and records the human choice separately.
   The server sets the fixed Synthetic Demo Manager; the client cannot supply
   identity, timestamps, evidence, recommendations or facility changes.

   For `REVIEW_REQUIRED`, only `{"action":"ACKNOWLEDGE_REVIEW"}` is accepted.
   Both recommendation and final posture stay null. No notification plan can be
   created from a review acknowledgment. Evaluate again for subsequent review.

   Store the returned `decision_id`. `GET /api/decisions/{decision_id}` retrieves
   the entire persisted record, including original evidence and evaluation.
6. `POST /api/decisions/{decision_id}/notification-plans` with body `{}` prepares
   one simulated plan from the persisted APPROVE/OVERRIDE action. It accepts no
   custom counts, posture, facility, messages, effective time or delivery options.
   Display the returned `group_counts`, messages, status and audit IDs.
7. `GET /api/decisions/{decision_id}/notification-plan` retrieves that exact plan.
8. `GET /api/audit?facility_id=jefferson-research&limit=100` loads decisions newest
   first, with IDs, timestamps, actions, original recommendation and final posture.
   The filter is optional. The limit is 1–100. Exact saved evaluation, evidence,
   decision and plan remain retrievable after an application restart.

The plan computes **54 assigned, 47 scheduled/affected, 31 telework eligible,
10 standard onsite, 6 essential personnel, 7 unscheduled/excluded** through the
existing roster resolver. Every message has `route=simulated` and
`status=GENERATED_SIMULATED`. This records preparation only: there is no send
endpoint or messaging transport. Essential staff must confirm assignments and
access authorization with authorized management. `effective_at` is null and
messages say **Effective time: not recorded**; the decision timestamp is not an
operating effective time.

## Identity and provenance

The browser uses **`jefferson-research`** for the entire workflow. The former
starter API detail URL `/api/facilities/jefferson-research-facility` is a deprecated
read alias with a `Deprecation: true` header; its response carries the canonical
ID. It is not accepted for evaluation creation. Facility listing retains the
starter display fields with a canonical ID and source/disclosure fields. Its
`operating_status` describes the initial synthetic catalog fixture, not the
latest synthetic decision; use audit records for finalized postures.

`severe_applicable_flood` originally belongs to `demo-flood-facility`. The existing
`demo_input_for_facility` binding explicitly creates a Jefferson **SIMULATED DEMO**
scenario, documented in Task 8B. It uses the invented `USGS-00000000` gauge,
invented access-route exposure, original readings, prototype thresholds and
fixed fixture clock. It does not reassign live evidence or use Jefferson's
regional `USGS-06910230` association as proof of exposure. The API reuses this
binding; no fixture or decision rule changed.

Other scenarios are `normal`, `delayed_arrival`, `unscheduled_telework`,
`missing_evidence`, `stale_evidence`, `conflicting_evidence`. Review is a status,
never an operating posture. All scenario data remains **SIMULATED DEMO**. For
example, `normal` has NWS collection status `NO_ACTIVE_ALERTS` while its provenance
remains simulated. `stale_evidence` reports freshness failures relative to the
fixture clock; simulation labels remain simulated as specified by the engine.
Historical LIVE/STALE/NO_ACTIVE_ALERTS source states in existing saved records
are returned without relabeling, refreshing evidence or calling public APIs.
The API preserves source observation/retrieval/validity timestamps and
**PROTOTYPE - NOT OFFICIAL USDA POLICY** labeling. It adds no numerical confidence
score; the frontend should use the existing evidence sufficiency and fired rules.

## Local security boundary

This API is **local demo only**. A demo manager label, CORS policy or loopback
check is not authentication. No real facility action occurs. Do not publish,
tunnel or place this server behind a proxy. Public deployment requires a separate
backend authorization design and is unsupported by this application.

The application requires an actual loopback peer and a Host of localhost,
127.0.0.1 or ::1, rejects forwarding headers and caller-supplied
manager identity. Uvicorn must bind to **127.0.0.1** with **--no-proxy-headers** as
shown above. `CLOSUREOPS_BIND_HOST` validates intended configuration; it does not
override Uvicorn's command-line bind. Remote peers fail even if Uvicorn is
incorrectly started on another interface. Local processes are trusted in this
demo; there is no user/agent authentication. Existing agents have no HTTP, manager
decision or notification preparation tools, and their tool sets are unchanged.

CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`, without
credentials. All writes additionally reject unapproved Origins before invoking
business logic. Same-origin local Swagger writes work. Non-browser local clients
can omit Origin; cross-site browser writes cannot. Arbitrary origins, null origins,
DNS-rebinding Host names and forwarded requests fail closed.

Bodies reject unexpected fields, control characters, invalid identifiers, invalid
postures and invalid reasons using strict schemas. Actual streamed bodies and
declared lengths are capped at **16 KiB**. Only application/json is accepted for
writes; uploads are unsupported. There is no arbitrary fetch, SQL, environment,
config, upload, real-send or arbitrary agent-invocation endpoint. The optional
briefing route accepts only a persisted evaluation ID and an empty JSON body.

Single-process local rate buckets: health 120/minute, ordinary reads 60/minute,
evaluation creation 20/minute, manager actions 10/minute, notification preparation
10/minute, and optional AI briefing 10/minute in a separate bucket. Each bucket
is shared by local clients, preventing alternate loopback
addresses from bypassing limits. Rejections use 429 and `Retry-After`; counters
are not exposed. Limits reset after process restart and are not suitable for a
multi-worker public service.

## Errors and persistence

API errors have the form:

```json
{"error":{"code":"INVALID_REQUEST","message":"Request does not match the API schema."}}
```

- 403: writes disabled, remote/non-local host, unsupported proxy or unapproved Origin.
- 404: unknown allowlisted binding, persisted ID not found, or no plan yet.
- 409: duplicate finalized decision/plan, review approval, or disallowed action.
- 413: JSON body larger than 16 KiB.
- 415: non-JSON write/upload attempt.
- 422: malformed JSON, invalid fields/identifiers or action payload.
- 429: local rate limit; honor `Retry-After`.
- 500/503: internal/storage failure; retrieve history before retrying a write.

Rejected values, validation contexts, private paths, environment variables and
credential values are not returned. CORS preflight rejection uses the standard
CORS middleware response; successful Swagger HTML is not an API JSON response.

The default database remains `backend/data/manager-decisions.sqlite3`, created
on first service use, outside frontend/public and ignored by Git. Override the
server-controlled `CLOSUREOPS_DEMO_DATABASE` path only for local testing. It is
never accepted from an HTTP request. Existing tables, parameterized persistence,
uniqueness constraints and immutable-history triggers are reused unchanged.
No migration or new database schema is introduced. Unfiltered audit history can
include earlier local-demo facility records; exact historical IDs are preserved.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q
.\.venv\Scripts\python.exe -m py_compile backend/app/main.py backend/app/api.py backend/app/api_security.py backend/tests/test_demo_api.py
.\.venv\Scripts\python.exe scripts/test_decision_engine.py
.\.venv\Scripts\python.exe scripts/test_employee_notifications.py --action approve
```

Integration tests use temporary SQLite databases and block all application
network connections, HTTP transports, inference and delivery. Windows asyncio's
private stdlib socketpair is permitted only to initialize the test event loop.
The HTTP workflow survives an application restart with exact JSON reconstruction.

The original Task 9A added no frontend or provider inference; Task 10B adds only
the optional local briefing path documented above. There is no live-evaluation
HTTP path, authentication, public deployment or real notification delivery. SQLite triggers
protect against accidental rewrites, not a privileged database administrator.
Swagger's default browser UI loads CDN assets; the local `/docs` endpoint and
OpenAPI work, but a cold browser cache without internet may not render Swagger
assets. The JSON API workflow itself is fully offline.
