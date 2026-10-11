# Task 9B.2 — Interactive local manager workflow

The existing dark-purple Overview and Decision Queue now run the same guided
workflow: choose a supported backend scenario, evaluate, explicitly confirm a
manager action, then explicitly prepare a simulated notification plan. History
inspects exact saved decisions and their plans. Snoopy assets and state mapping,
deterministic rules, acquisition code, Akamai adapter and SQLite schema are unchanged.

## Run the complete demonstration in PowerShell

Stop the old API on port 8001 with Ctrl+C in its terminal before restarting it.
From the repository root, use a dedicated demo database; do not use
`manager-decisions.sqlite3` or `command-center-verification.sqlite3`.

Terminal 1:

```powershell
Set-Location C:\Users\14172\Downloads\ClosureOps
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='true'
$env:CLOSUREOPS_DEMO_DATABASE='backend/data/manager-workflow-demo.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
```

Terminal 2 (keep the existing frontend if it already uses port 8001; otherwise
stop it with Ctrl+C before restarting):

```powershell
Set-Location C:\Users\14172\Downloads\ClosureOps
$env:VITE_API_BASE_URL='http://127.0.0.1:8001'
npm --prefix .\frontend run dev
```

Open <http://127.0.0.1:5173>. Click **Refresh API** after restarting the backend.
The banner must say **LOCAL DEMO WRITES**. No credentials or provider setup is
required beyond the existing installed dependencies.

## Three-minute demonstration

1. Keep Jefferson Research Facility and the default `severe_applicable_flood`
   scenario. Click **Evaluate demo scenario**. The trusted backend persists and
   returns an evaluation ID. The browser displays the engine's FACILITY_CLOSURE,
   SUFFICIENT evidence, prototype rules, simulation disclosure and high-risk Snoopy.
2. Inspect **Review Evidence** for references, observed/retrieved/validity times,
   gauge exposure, fixed fixture clock and limitations. These are invented
   Jefferson demo evidence using USGS-00000000, not live weather or its regional
   gauge. Close the dialog. The visible recommendation is still advisory.
3. Click **Approve**, inspect the confirmation summary, then **Confirm action**.
   The backend sets Synthetic Demo Manager and returns the saved decision ID and
   timestamp. Snoopy stays high risk because recording an action does not end the
   hazard. The engine recommendation stays visible separately from manager posture.
4. Click **Prepare simulated notifications**. Backend-computed counts are 54
   assigned, 47 scheduled, 31 telework eligible, 10 standard onsite, 6 essential,
   and 7 excluded. Expand each group for exact backend message previews. Status is
   GENERATED_SIMULATED; no real notifications sent. Essential personnel must
   confirm assignments and access with authorized management before travel/entry.
5. Open **History**, then **Inspect** for the saved decision. Review the original
   recommendation, final posture, action/reason, immutable evidence timestamps
   and associated plan. Reloading the page retains the last evaluation ID in
   sessionStorage; **Load** retrieves its exact persisted result, decision and plan.

Alternative paths: **Override** requires a different supported final posture and
a nonblank reason of at most 500 characters. Missing/stale/conflicting scenarios
produce REVIEW_REQUIRED; only **Acknowledge review** is available. It records no
operating posture and cannot prepare notifications. Evaluate again for further review.

## API and local security

| Method / endpoint | Purpose |
| --- | --- |
| GET `/api/health` | Service validation and server-owned `local_demo_writes_enabled` capability |
| GET `/api/facilities`, `/api/demo/scenarios` | Allowlisted facility/scenario selection |
| POST `/api/evaluations` | Trusted deterministic evaluation, persisted ID and snapshot |
| GET `/api/evaluations/{id}` | Retrieve exact saved evaluation |
| POST `/api/evaluations/{id}/decisions` | Explicit APPROVE, OVERRIDE or ACKNOWLEDGE_REVIEW |
| GET `/api/decisions/{id}` | Exact persisted manager decision |
| POST `/api/decisions/{id}/notification-plans` | Prepare one simulated plan with `{}` only |
| GET `/api/decisions/{id}/notification-plan` | Retrieve existing plan without regenerating |
| GET `/api/audit?limit=100` | Persisted decision history and reconciliation |

The only backend adapter change adds the boolean write capability to the existing
health response, supplied by server settings. It exposes no environment/config
dump. Missing capability in an older server defaults to false in the browser.
The frontend disables write controls until validated health allows them and
rechecks health before every POST. Server loopback peer/Host, Origin, forwarding
header, request schema/size and rate-limit protections remain authoritative.
CORS and the synthetic manager label are not authentication. All requests omit
credentials; the client never supplies manager identity, thresholds, counts,
messages, evidence, timestamps or delivery options.

Native disabled controls plus synchronous submission locks prevent accidental
double actions. Before enabling manager action, the UI checks saved history.
After a lost/409 write response it reads history or the existing plan; it never
repeats a write automatically or invents success. If verification fails, the UI
shows an unconfirmed outcome and offers **Check saved history**. Rate limits show
Retry-After guidance. Evaluation creation has no idempotency key/list endpoint;
if its response is lost, an explicit retry may create a separate evaluation. It
never approves anything. Persisted evaluation IDs are displayed separately from
editable lookup text, and manager/plan results use validated backend IDs.

To disable writes, stop and restart Terminal 1 with
`$env:CLOSUREOPS_LOCAL_DEMO_WRITES='false'`, retaining the dedicated database.
Refresh API. Reads/history still work; all write routes are rejected by the server.
Do not publish or tunnel this local demonstration server.

## Verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_demo_api.py --import-mode=importlib -q
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run lint
npm --prefix .\frontend run test
npm --prefix .\frontend run build
npm --prefix .\frontend run test:e2e
npm --prefix .\frontend run test:e2e:workflow
```

The workflow browser suite starts loopback APIs on ports 8002 (writes enabled)
and 8003 (read only), backed by a new
`backend/data/manager-workflow-test-<run-time>.sqlite3` file on every run. Existing
verification/demo records are not touched. Browser request routing changes only
the API port; responses and backend business/security logic are real, preserving
the approved frontend Origin on 5173. Playwright stops its API processes afterward.
The existing frontend server can be reused. Edge and installed Playwright are
required. Test databases and screenshots under `frontend/test-results/workflow`
are Git-ignored and retained for local inspection.

Limits: synthetic snapshots only, no model briefing, no numerical confidence,
no real delivery or authentication. Operating effective time is not recorded.
History has a 100-record cap; if a finalized evaluation is not found at that cap,
manager controls fail closed. Older decisions outside the list cannot be selected
through this UI. Other navigation destinations retain their existing placeholders.
The reference basemap still depends on external tiles; its failure does not block
the local workflow. Existing map bundle-size and third-party annotation warnings
are unrelated to this task.

## Completion report

Files changed or added in Task 9B.2:

- Backend capability and regression: `backend/app/api.py`, `backend/app/main.py`,
  `backend/tests/test_demo_api.py`.
- Frontend wiring and contracts: `frontend/src/App.tsx`,
  `frontend/src/api/client.ts`, `frontend/src/api/schemas.ts`,
  `frontend/src/hooks/useCommandCenter.ts`,
  `frontend/src/hooks/useManagerWorkflow.ts`, `frontend/src/styles.css`.
- Reused recommendation panel and new workflow components:
  `frontend/src/components/RecommendationPanel.tsx`,
  `frontend/src/components/ManagerActions.tsx`,
  `frontend/src/components/NotificationPlanPanel.tsx`,
  `frontend/src/components/DecisionHistory.tsx`.
- Test runner and fixtures: `frontend/package.json`,
  `frontend/playwright.workflow.config.ts`,
  `frontend/tests/generate_fixtures.py`, `frontend/tests/fixtures/api.json`,
  `frontend/tests/unit/workflow-api.test.ts`,
  `frontend/tests/e2e/overview.spec.ts`,
  `frontend/tests/e2e/manager-workflow.spec.ts`,
  `frontend/tests/browser-workflow/manager-workflow.spec.ts`.
- Documentation: `docs/local-demo-api.md`, `docs/command-center-frontend.md`,
  `docs/manager-decision-workflow.md`.

Verified results: focused backend API tests **104 passed**; frontend unit tests
**49 passed**; API smoke tests **4 passed**; browser checks **8 existing Overview
checks + 9 workflow checks passed**; real isolated workflow browser tests
**5 passed**. Typecheck, ESLint and production build passed. The existing build
warnings concern the map bundle and third-party Zod annotations.

Browser verification found and fixed a refresh loop: a saved decision now
refreshes only audit data, preserving facility/evaluation state and staying
within the existing rate limits. After scenario evaluation the recommendation
receives focus and scrolls into view, reducing manual scrolling on laptop screens.
Additional checks cover duplicate clicks, revoked write capability, lost write
responses, read-only mode, override validation, review restrictions, exact plan
retrieval, persisted audit inspection, Snoopy state and simulated-only delivery.

The optional smoke suite initially found no API listening on port 8001. The local
demo API was started with the dedicated `manager-workflow-demo.sqlite3` database;
the smoke suite then passed. Earlier verification databases were untouched. No
dependencies, secrets, security guards, decision rules, retrieval code, image
assets, deployment or commits were changed. Existing repository files are
untracked in Git; `git diff --check` reports no tracked diff, and no `.env` secret
files are tracked. The task leaves the local frontend and dedicated demo API
available; future restarts use the commands above.
