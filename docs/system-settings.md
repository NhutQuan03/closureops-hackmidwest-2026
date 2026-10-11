# Task 9C.3 — System Settings & Integrations

Settings uses the existing command-center resources. Refresh Status reloads the
same fixed GET endpoints as Refresh API: `/api/health`, `/api/facilities`,
`/api/demo/scenarios`, and `/api/audit?limit=100`. It makes no writes or external
connectivity probes. Existing startup commands and environment requirements are
unchanged; see [the local API guide](local-demo-api.md).

System status displays the configured public API base URL (URL credentials,
query, and fragment are excluded), health availability, last successful health
check this session, the backend's synthetic data mode, and the server-owned
local-demo write capability. A failed refresh retains the successful timestamp
but marks current mode and capability unavailable. Health confirms connectivity,
not authentication, authorization, database diagnostics, or third-party health.
Browser timestamps reflect the browser clock.

Integration cards distinguish known configuration from actual reads:

| Integration | What Settings establishes |
| --- | --- |
| NWS | Task 10A adds a read-only national active-alert endpoint used by Alerts. Settings describes this capability without probing NWS. It is separate from saved facility evidence. |
| USGS | No current water-feed endpoint. Saved observations must retain their provenance; gauges do not establish facility flooding. |
| AWS Strands | Task 10B optionally constructs the tested local briefing agent after an explicit Generate AI Briefing action. It has only the read-only decision tool. Settings performs no agent or cloud check. |
| Akamai inference | Task 10B reuses the existing server-only adapter behind a local opt-in. Settings performs no authenticated request or credential inspection; this card is configuration information, not connectivity confirmation. |
| OpenFreeMap | MapLibre is configured with `https://tiles.openfreemap.org/styles/dark`, without a key. Availability is handled by the existing map, not probed by Settings. |
| SQLite | Documented local audit storage. The card reports whether the latest audit GET succeeded, not database or write health. |

Jefferson details are displayed only from the validated facility catalog.
Loading, unavailable, and absent-catalog states do not invent location values.
The page preserves SIMULATED DEMO, prototype-policy, human-approval, and
simulated-notification disclosures. There are no credential, threshold, manager
decision, or security-flag controls.

The only editable setting reduces optional mascot motion. It persists
`reduce` or `system` under `closureops-motion-preference` in localStorage;
denied storage leaves a functional session-only preference. Operating-system
reduced motion always takes precedence and responds to preference changes.
Static replacement artwork is selected and mascot entrance animations stop.
Current Snoopy PNG assets and state mapping are unchanged. Dark-purple styling
remains the default.

Verification commands from `frontend`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run test:e2e
npm run build
```

With FastAPI running on `127.0.0.1:8001`, the additional
`npm run test:e2e:live -- settings.spec.ts` check verifies actual health,
facility, and audit responses without API mocks or manager writes. Screenshots
are written to `frontend/test-results/settings-desktop.png`,
`settings-mobile.png`, and `live/settings-api.png`.
