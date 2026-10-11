# Task 10A — USDA live NWS alert demonstration

Alerts contains a nationwide NWS panel above the historical facility evaluation
section. **Refresh Live NWS** performs a read-only GET to
`/api/nws/alerts/active`. Nothing is acquired on page mount or API startup.
This route works with local-demo writes disabled and uses the existing loopback,
CORS, ordinary-read rate limit, and no-store response safeguards unchanged.
There is no new authorization, agent tool, facility action, audit write, or
notification capability.

The existing NWS transport retrieves
`https://api.weather.gov/alerts/active?status=actual` without a point filter.
The national adapter shares the existing TLS trust, identifying server-side
User-Agent, explicit timeouts, three-attempt maximum with bounded backoff,
sanitized failures, expected JSON content types, and restricted HTTPS NWS
redirect handling. No key or new integration dependency is required.
Official endpoint behavior is documented in the
[NWS API guide](https://www.weather.gov/documentation/services-web-api).

The national response is bounded to 10 MiB and 5,000 examined features. The
adapter validates the collection and consumed fields, excludes non-Actual and
Cancel messages, prefers unexpired alerts, sorts by sent timestamp and official
URL, and returns at most five. Event, severity, urgency, certainty, affected
area, sent/effective/expiry timestamps, official feature URL, source and
retrieval timestamp are preserved. Optional absent fields are unavailable.
The source URL is validated as an official HTTPS `api.weather.gov/alerts/` URL
on both backend and frontend; alert text is rendered as escaped data.

Pagination links are never followed. A nonempty partial collection may provide
an explicitly limited selection; an incomplete empty collection is unavailable,
never NO_ACTIVE_ALERTS. Counts describe examined records, not a national total.
Malformed or oversized responses are unavailable, not silently reduced to an
empty successful feed. There is no simulated fallback for this endpoint.

LIVE requires a fresh provider HTTP Date/Age and alert expiry after the retrieval
time. The display freshness deadline is at most five minutes and is independent
of operating-policy thresholds. Missing/old provider freshness, expired or
unknown alert validity is STALE. Browser freshness is checked every 15 seconds;
each alert is also downgraded after expiry. A failed refresh retains the prior
verified public snapshot only as STALE, with its original retrieval timestamp.
A fresh complete empty collection may show NO_ACTIVE_ALERTS; this is never proof
that facility operations are safe. Backend/browser clock differences can reduce
freshness and require a manual refresh.

Nationwide geographic applicability is always NOT_ASSESSED. This data is not
passed into the synthetic flood engine, saved evaluations, approvals, SQLite
records, USGS services, Strands agent, or Akamai adapter. Historical simulated
warnings remain SIMULATED DEMO and are not current live warnings. Settings now
describes the national read capability without making external status probes.

## Startup and verification

Restart an already running FastAPI process to load the new route, using the same
startup command, database and local-demo write setting as before. Keep the
documented `127.0.0.1:8001` backend and `127.0.0.1:5173` frontend defaults.
No new environment variables are needed for ordinary use.

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\verify_national_nws.py
.\.venv\Scripts\python.exe -m pytest backend/tests/test_nws.py backend/tests/test_national_nws.py backend/tests/test_demo_api.py -q
```

From `frontend`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run test:e2e
npm run test:e2e:live -- national-nws.spec.ts
npm run build
```

The live browser test uses actual backend data and never fabricates NWS responses.
For verification without restarting the existing user server, a separate local
read-only backend was started on port 8002; setting
`CLOSUREOPS_NWS_VERIFY_ORIGIN=http://127.0.0.1:8002` in the test shell forwards only
the national GET to that server. Other browser reads continue against 8001.
This variable is a test setting, not a production frontend setting.

Actual direct verification on **2026-10-11 at 06:19:20 UTC** succeeded against the
national collection: LIVE, 492 examined records, five selected alerts, no error.
The selection contained Beach Hazards Statements, a High Surf Advisory and a
Wind Advisory. This is a verification snapshot, not a current-weather claim.
Screenshots from the subsequent actual-data browser check are under
`frontend/test-results/live/nws-actual-desktop.png` and `nws-actual-mobile.png`.
At 06:26:46 UTC that browser check received LIVE evidence, 497 examined records,
and five displayed alerts (winter weather advisories, a winter storm warning,
and a wind advisory), using only real HTTP GET responses.
Final browser verification at **06:29:16 UTC** received LIVE evidence, 500 examined
records and five selected alerts: Flash Flood Warning, Coastal Flood Watch, two
Coastal Flood Advisories and Winter Weather Advisory. The final screenshots use
this snapshot; `nws-actual-feed.png` provides a focused view of the panel.

All 188 focused backend tests, 68 frontend unit tests and 37 browser regression
tests passed. The final freshness changes also passed all three focused browser
tests and a repeated actual-NWS browser check. Typecheck, ESLint, Python
compilation and production build passed. The verification server on 8002 was
stopped afterward; the original server on 8001 was left running unchanged.

## Files changed

- `backend/app/services/nws.py`, `backend/app/national_nws.py`, `backend/app/api.py`
- `backend/tests/test_national_nws.py`, `scripts/verify_national_nws.py`
- `frontend/src/api/client.ts`, `frontend/src/api/schemas.ts`, `frontend/src/App.tsx`
- `frontend/src/components/LiveNwsAlerts.tsx`, `AlertsPage.tsx`, `EvaluationEvidence.tsx`
- `frontend/src/lib/liveNws.ts`, `frontend/src/lib/settings.ts`, `frontend/src/styles.css`
- `frontend/tests/fixtures/national-nws.ts`, `frontend/tests/unit/live-nws.test.ts`, `settings.test.ts`
- `frontend/tests/e2e/live-nws.spec.ts`, `settings.spec.ts`
- `frontend/tests/browser-live/national-nws.spec.ts`, `operational-pages.spec.ts`
- `README.md`, `docs/local-demo-api.md`, `docs/system-settings.md`, this guide

Ruff is unavailable in the existing Python environment; no dependency was added
solely to run it. Frontend ESLint and Python compilation are the available lint
and syntax checks. The production build retains the existing MapLibre chunk-size
and dependency comment warnings.
