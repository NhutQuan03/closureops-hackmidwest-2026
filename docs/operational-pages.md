# Task 9C.2 — Facilities, Alerts and Reports

The three operational screens use the existing validated FastAPI client and
response schemas. No backend services, acquisition tools, decision rules,
credentials, dependencies, or manager-write permissions change.

## Facilities

The selected `GET /api/facilities` record supplies name, ID, synthetic coordinates,
city/state/country, timezone, initial catalog status, source timestamp, review
timestamp, authority scope and limitations. Initial catalog status is not a
current operating decision. The existing OpenFreeMap FacilityMap remains a
synthetic reference map with its attribution, controls and offline fallback.

The current saved evaluation, or latest loaded matching audit evaluation when
none is selected, supplies historical exposure association, basis and any
prototype thresholds. Without an evaluation those details are unavailable;
catalog disclosure is retained. The page links to Alerts and Decision Queue.
Navigation never creates an evaluation or finalizes a decision automatically.

## Alerts

There is no alerts-list or evaluation-list API. This screen uses only the loaded
evaluation plus evaluations embedded in loaded audit decisions, deduplicated by
evaluation ID and filtered to the selected facility. The selector retains access
to those available snapshots; unfinalized evaluations are retrievable by known
ID through the existing Overview form.

Shared evidence details show NWS events, severity, urgency, certainty, geographic
scope, query point, acquisition status and validity; USGS height/streamflow
observations, original trend endpoints, series IDs, approval state and timestamps;
source references, recorded freshness states, acquisition checks and limitations.
Only existing allowlisted HTTPS source URLs become links. Other references remain
escaped text. Absent evidence is unavailable rather than inferred.

`SIMULATED DEMO`, recorded `NO_ACTIVE_ALERTS`, `STALE`, `UNAVAILABLE`, `NO_DATA`
and historical `LIVE` source states retain their meaning. Recorded LIVE is
explicitly a saved snapshot, not a current feed; it is not arbitrarily relabeled
STALE. Public observations and historical simulated evidence are distinguished.
Stale simulated scenarios also display the backend freshness rules that fired.
Regional gauges never establish facility or access-route flooding. Evidence
details are reused by the existing evidence dialog and History inspection.

## Reports

`GET /api/audit?limit=100` supplies finalized records across the facilities in that
response. Counts use distinct decision IDs, separate APPROVE, OVERRIDE and
ACKNOWLEDGE_REVIEW, and group original/final posture pairs. Review retains null
postures. The timeline sorts by the recorded decision timestamp. The report
always discloses that it summarizes only loaded records, not all-time totals.
An unavailable/invalid response supplies no counts; a successful empty list
supplies zero loaded decisions.

Only the selected decision is read through `GET /api/decisions/{decision_id}` and
its eligible `GET /api/decisions/{decision_id}/notification-plan`. This avoids
fetching up to 100 plans against the existing read rate limit. The shared
notification panel shows original synthetic group counts and preparation status.
The plan must match the decision's facility and final posture before display.
404 means no saved plan; other failures mean unavailable status. Review
acknowledgments do not request a plan. Selecting another record retrieves its
own counts; employee counts are not summed across repeated decisions.
`GENERATED_SIMULATED` records preparation only, never delivery. There are no
real send controls, savings calculations, damage estimates or confidence scores.
Timeline inspection navigates to the original record in History.

## Start and verify

Startup is unchanged. From the repository root, use separate PowerShell terminals:

```powershell
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='true'; $env:CLOSUREOPS_DEMO_DATABASE='backend/data/manager-workflow-demo.sqlite3'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
```

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8001'; npm --prefix .\frontend run dev
```

Open `http://127.0.0.1:5173`. Use `CLOSUREOPS_LOCAL_DEMO_WRITES='false'` for a
read-only session. This API remains local-only; see [the local API guide](local-demo-api.md)
and [manager workflow guide](manager-decision-workflow.md) for its security boundary.

From `frontend`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run test:e2e
npm run build
```

Focused tests cover deterministic loaded-record aggregation, preserved snapshot
provenance, safe source links, facility selection, missing/stale evidence, empty
and offline/invalid responses, mismatched/missing/failed plans, record inspection
and all six core destinations at laptop and narrow viewport sizes. Browser API
fixtures originate from the existing backend models; browser checks do not send
real notifications or call public weather acquisition. Basemap failures are
tested separately from facility data failures. Screenshots are local ignored
artifacts under `frontend/test-results`.

For read-only verification against already persisted records, start the API
with the same database and `CLOSUREOPS_LOCAL_DEMO_WRITES='false'`, then run
`npm run test:e2e:live -- operational-pages.spec.ts` from `frontend`. This check
does not intercept API responses, create records, or prepare/send notifications.
It compares the displayed summary to the actual audit response and inspects
the original history record when available.

## Files changed

- `frontend/src/App.tsx`, `frontend/src/styles.css`
- `frontend/src/components/FacilitiesPage.tsx`, `AlertsPage.tsx`, `ReportsPage.tsx`
- `frontend/src/components/EvaluationEvidence.tsx`, `EvidenceFeed.tsx`, `DecisionHistory.tsx`
- `frontend/src/hooks/useCommandCenter.ts`, `frontend/src/lib/reports.ts`
- `frontend/tests/unit/reports.test.ts`, `evaluation-evidence.test.ts`, `evidence.test.ts`
- `frontend/tests/e2e/operational-pages.spec.ts`, `overview.spec.ts`
- `frontend/tests/browser-live/operational-pages.spec.ts`, `command-center.spec.ts`
- `README.md`, `docs/operational-pages.md`

Settings was completed in [Task 9C.3](system-settings.md). These operational pages add no public deployment or authentication,
current weather feed, evaluation enumeration, audit pagination, unique employee
reporting, or notification delivery is added. Map tiles still require internet
and WebGL; the saved-record workflow works independently of the map provider.
