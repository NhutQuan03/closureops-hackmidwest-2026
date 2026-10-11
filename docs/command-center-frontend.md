# Task 9B.1-F — Finalized command center frontend

This is the historical Task 9B.1-F verification report. Task 9B.2 now adds
interactive Overview/Decision Queue actions and persisted History inspection;
use the [current manager workflow guide](manager-decision-workflow.md) for startup,
security behavior and browser tests. Read-only mode remains supported.

The Overview is a local, read-only operations console. It uses the existing
React/TypeScript/Vite app, Tailwind's Vite plugin, local shadcn-style primitives
(Button, Card, Badge, Radix Dialog), Lucide icons and MapLibre. Theme variables
match the supplied dark palette. No backend module or AGENTS.md was changed.

## Start in PowerShell

From `C:\Users\14172\Downloads\ClosureOps`, start the current API in one terminal:

```powershell
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='false'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
```

Start the frontend in a second terminal, also at the repository root:

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8001'; npm --prefix .\frontend run dev
```

Open **http://127.0.0.1:5173**. `strictPort` prevents Vite silently moving to an
origin not allowed by the API's existing CORS policy. Stop with Ctrl+C. Run
`npm --prefix .\frontend install` if dependencies have not been installed.
Node 22.13+ is recommended for the new lint toolchain; this task's Node 22.11
passed all checks but npm emitted a transitive ESLint engine warning.

The public `VITE_API_BASE_URL` config defaults to `http://127.0.0.1:8001` and can
be set in the existing root `.env`/`.env.local` configuration or in the launching
PowerShell session. It is an API origin, never a credential. Restart Vite after
changing it. The frontend makes direct GET requests without credentials; no
proxy or forwarding headers bypass the API's local security guard.

The unavailable banner came from the old default on port 8000. That running API
returned a legacy facility ID/schema and lacked the scenario route. The current
8001 API passed health and CORS checks. No security changes were needed. Requests
configured for port 8000 are now rejected with an actionable configuration error.
That old process was left untouched. Stop any existing Vite process before
relaunching on 5173. A schema mismatch is
shown as unavailable data; the frontend never promotes the legacy `open` catalog
status into a recommendation.

## Implemented screens and data

- Overview: operational metric cards, configured Jefferson reference map, recent
  saved evidence feed, recommendation panel and expandable scenario catalog.
- Collapsible desktop sidebar and keyboard-accessible mobile dialog navigation.
  Facilities, Alerts, Decision Queue, History, Reports and Settings are explicit
  planned-screen placeholders.
- Top bar: logo, facility selection, disabled search placeholder, Midwest context,
  timestamped API health check, notification-availability dialog and synthetic demo
  manager label. There is no authentication or notification inbox.
- Persistent **SIMULATED DEMO** and **READ ONLY** disclosure on every screen.

| GET route | Displayed data |
| --- | --- |
| `/api/health` | Validated API availability; never source freshness |
| `/api/facilities` | Canonical IDs, names, coordinates, provenance and represented count |
| `/api/demo/scenarios` | Expected fixture outcomes and fixed clock, explicitly not evaluated recommendations |
| `/api/audit?limit=100` | Latest manager-finalized synthetic posture for each represented facility; history is not a current real operating status |
| `/api/evaluations/{evaluation_id}` | Saved authoritative engine result, evidence snapshot, sufficiency, prototype rules, original timestamps and limitations |

API requests time out after 10 seconds. Runtime Zod models validate displayed
fields against the actual Pydantic models, including review/posture consistency.
Resources load independently; offline, malformed, empty, rate-limited and missing
record responses keep the application usable. Refresh API rechecks catalog,
health and history without creating an evaluation. Evaluation IDs are validated
before a request, and records for another facility are rejected. Requests are
aborted on unmount or facility change. No POST route exists in the frontend client.

Active alerts and pending-review totals remain **Unavailable** because there is
no current weather feed or evaluation-list endpoint. A saved recommendation never
increments confirmed closures. Closure counts use finalized APPROVE/OVERRIDE
records, with review acknowledgments excluded from posture changes. An empty
successful audit response gives a verified count of zero. Failed history or a
response at the 100-record cap gives Unavailable because completeness is unknown.

To inspect evidence, create or retrieve an evaluation through the previously
verified [local API workflow](local-demo-api.md), then paste its `eval_…` ID into
**Load a saved evaluation**. The frontend reads the record without creating or
approving anything. `REVIEW_REQUIRED` displays **Manual review required**, no
operating posture and the backend's insufficient/conflicting evidence state.
Approve and Override are native disabled buttons with an explanation.

The API has no AI briefing field. The panel displays engine reasons and clearly
states that AI briefing is unavailable. No confidence percentage, fabricated
weather, inferred exposure or authenticated inference is introduced.

## Map, mascot and freshness

MapLibre plots only the allowlisted Jefferson catalog coordinates (Columbia
reference point), labeled SIMULATED DEMO. Marker and accessible location-card
selection update the facility selection. Purple denotes a location, not risk.
There are no invented hazard markers, and regional gauges do not establish flood
exposure. The basemap uses OpenFreeMap's dark vector style over HTTPS at
`https://tiles.openfreemap.org/styles/dark`, without an API key. MapLibre retains
the style's OpenFreeMap, OpenMapTiles, and OpenStreetMap attribution. Internet
and WebGL are needed for the basemap; loading and unavailable states preserve
the facility coordinates and selection.
MapLibre is loaded separately from the core dashboard bundle.
Its vector tile worker is bundled locally with Vite's `?worker&url` import and
configured through `setWorkerUrl` so the production build can render vector data.
Style, vector tile, sprite, or glyph errors display the basemap-unavailable
message while retaining the configured marker and coordinate readout. A
10-second loading timeout also surfaces provider unavailability. No map API key
is added to the frontend.

Evidence is a saved snapshot, never implicitly refreshed. Simulated observations
retain SIMULATED DEMO, including stale fixtures evaluated against their fixed clock.
Historical LIVE states are shown as **STALE · SAVED SNAPSHOT** in the feed while
the original state and timestamps remain visible in the evidence dialog. Allowed
HTTPS NWS/USGS source references are linked; fixture references remain text and do
not become fabricated public URLs. Unknown timestamps say Timestamp unavailable.

`AssistantMascot.tsx` preserves the typed nine-state interface and replaceable
asset configuration. Scout's SVG has been replaced with the two user-provided
**static PNGs**, `public/mascot/snoopy-idle.png` and `snoopy-high-risk.png`.
The framed images use responsive sizing and `object-fit: contain`. A brief CSS
entrance animates the frame only; reduced-motion users get a static presentation.
Missing/broken assets show a textual state fallback. No artwork was downloaded
or generated.

State precedence is: reading a saved evaluation → monitoring; no evaluation →
idle; REVIEW_REQUIRED → review_required; a validated ready/sufficient
FACILITY_CLOSURE with SIMULATED DEMO mode and result provenance → high_risk;
otherwise an actual matching manager record → resolved (label: Recorded manager
action), or awaiting_approval. Manager actions never override the high-risk
state or establish that a hazard ended. Hazard recommendation and human approval
information remain separately visible. No severity is inferred from prose.

Only high_risk uses the running Snoopy image. Idle, monitoring and all other
states reuse the sleeping image with their correct state labels. Analyzing,
watch and caution remain available typed states, but are not activated without
a verified workflow supporting them. The API exposes no running agent process.

## Verification

From the frontend directory:

```powershell
npm run typecheck
npm run lint
npm run test
npm run build
npm run test:e2e
```

The browser suite uses installed Microsoft Edge in headless mode. It stubs GET
responses with actual backend-generated synthetic fixtures and blocks basemap
tiles to test failure behavior. It covers all navigation destinations, sidebar
collapse, marker selection, offline/invalid/empty data, review status, disabled
controls, evidence dialog keyboard/focus behavior and layouts at 320, 390, 768,
1366 and 1440 pixels. Screenshots in `frontend/test-results` are ignored.
`tests/fixtures/api.json` is never imported by the application or used as a fallback.

Optional checks against the running local API (GET only):

```powershell
$env:CLOSUREOPS_TEST_API_URL='http://127.0.0.1:8001'; npm run test:api
```

For reproducible **real API browser verification**, prepare a dedicated database
from the repository root, then start the API against it:

```powershell
.\.venv\Scripts\python.exe frontend\tests\prepare_live_demo.py
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='false'
$env:CLOSUREOPS_DEMO_DATABASE='backend/data/command-center-verification.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
```

The helper calls the existing trusted Python service for the severe applicable
flood and missing-evidence scenarios. It creates no manager decisions or
notifications, uses no external services, and reuses its IDs on repeat runs.
Existing application databases stay intact. The dedicated database and ID
manifest are ignored by Git and live outside the frontend/public directory.
The default existing database contained historical records for a different
synthetic facility; the frontend correctly rejects those as Jefferson evidence.

With this API and Vite running, from `frontend` run:

```powershell
npm run test:e2e:live
```

The four real Edge browser tests use no API interception or response fixtures.
They require successful HTTP health/catalog/audit/evaluation responses from 8001;
missing records or an unavailable API fail the tests. They check actual CORS,
sleeping/high-risk images, REVIEW_REQUIRED, disabled manager controls, mobile
navigation and reduced motion. Credential-field/pattern checks do not print
suspected values. Screenshots: `frontend/test-results/live/overview-{idle,high-risk,review,mobile}.png`.

Regenerate response fixtures from the repository root:

```powershell
.\.venv\Scripts\python.exe frontend/tests/generate_fixtures.py
```

The generator uses a temporary SQLite database, creates synthetic evaluations and
a synthetic test decision only there, then removes that temporary database. It
does not contact weather/model/message providers or alter the application's audit
history.

Final results: typecheck, ESLint and build pass; 44 unit tests, 4 running-API smoke
tests, 8 fixture-based browser regression tests and 4 real-API browser tests pass.
Backend code was unchanged; the previous 677 tests and 10 subtests were not rerun
for this frontend finalization.
`npm audit --omit=dev --audit-level=high` reports zero vulnerabilities (the check
used the Windows trusted public certificate bundle in the ignored local npm cache).
The build reports a large MapLibre chunk (~1.06 MB minified, ~289 KB gzip) and
harmless upstream Zod annotation warnings. MapLibre is already dynamically split.
No public deployment, real notifications, commits or pushes were performed.

## Finalization changes (9B.1-F)

Modified: `.env.example`, `.gitignore`, `README.md`, `docs/local-demo-api.md`,
this guide, `frontend/package.json`, `frontend/vitest.api.config.ts`,
`frontend/THIRD_PARTY_NOTICES.md`, `frontend/src/api/client.ts`,
`frontend/src/lib/dashboard.ts`, `frontend/src/styles.css`,
`frontend/src/components/{AssistantMascot,RecommendationPanel,FacilityMap}.tsx`,
`frontend/tests/unit/api.test.ts`, `frontend/tests/e2e/overview.spec.ts`.

Created: `frontend/playwright.live.config.ts`,
`frontend/tests/{browser-live/command-center.spec.ts,unit/mascot.test.ts,prepare_live_demo.py}`.
The two existing user PNGs were inspected and integrated without edits.
No dependencies were installed or upgraded during finalization. Vite's strict
loopback configuration, backend security, and decision/integration services
were preserved. The remaining file/dependency inventory below records 9B.1.

## Foundation files and dependencies (9B.1)

Modified: `frontend/src/App.tsx`, `frontend/src/styles.css`,
`frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`,
`frontend/tsconfig.json`, `frontend/index.html`, `.gitignore`, `README.md`.

Created: `frontend/src/api/{client,schemas}.ts`,
`frontend/src/hooks/useCommandCenter.ts`, `frontend/src/lib/{dashboard,utils}.ts`,
`frontend/src/components/{AssistantMascot,EvidenceFeed,FacilityMap,RecommendationPanel}.tsx`,
`frontend/src/components/ui/{badge,button,card,dialog}.tsx`,
`frontend/public/favicon.svg`, `frontend/components.json`,
`frontend/THIRD_PARTY_NOTICES.md`, `frontend/eslint.config.js`,
`frontend/playwright.config.ts`, `frontend/vitest{,.api}.config.ts`,
`frontend/tests/{unit/api.test.ts,unit/evidence.test.ts,e2e/overview.spec.ts,integration/live-api.test.ts,generate_fixtures.py,fixtures/api.json}`,
and this guide.

Added runtime dependencies: `lucide-react`, `maplibre-gl`, `zod`,
`@radix-ui/react-dialog`, `@radix-ui/react-slot`, `class-variance-authority`,
`clsx`, `tailwind-merge`. Added development dependencies: `tailwindcss`,
`@tailwindcss/vite`, `eslint`, `@eslint/js`, `typescript-eslint`,
`eslint-plugin-react-hooks`, `globals`, `@types/node`, `vitest`, `@playwright/test`,
`prettier`. Each is limited to the requested styling, primitives, strict read
adapter, or verification tooling. React/Vite/Python frameworks were preserved.
The lockfile records exact dependency versions; upstream license notices are
retained in package distributions and the UI notice file.

Only Overview and read-only evidence inspection are implemented. Other screens,
manager actions, automatic evaluation discovery, live evidence and AI briefing
remain outside this phase.
