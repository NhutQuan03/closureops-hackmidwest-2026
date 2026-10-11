# Task 10B — Browser AI briefing

The Command Center's recommendation panel now separates the **deterministic
recommendation**, optional **AI-assisted explanation**, and **final human
decision**. Generate AI Briefing is an explicit action. Loading evaluations,
refreshing status, approving decisions, and preparing simulated notifications
do not start inference.

Task 10B.2 adds a [manager-friendly situation briefing](manager-situation-briefing.md)
with five deterministically composed sections. Technical details and the complete
raw explanation are now collapsed under Technical diagnostics. The agent and
strict AI selection validator are unchanged; the parent additionally validates
the composed sections against the saved evaluation.

## Trusted evaluation and model/tool design

`POST /api/evaluations/{evaluation_id}/ai-briefing` accepts only `{}`. The server
loads the immutable SQLite evaluation; no client prompt, weather, scenario,
recommendation, credentials, or manager identity is accepted. Unknown IDs return
404, malformed IDs or additional fields return 422. The route does not create
or modify evaluations, decisions, audit events, or notification plans.

The existing tool is scenario-bound rather than snapshot-bound. The service
therefore matches the saved evidence exactly to one of the seven existing
Jefferson demo scenarios and reproduces the complete saved result in a
deterministic preflight. This includes evidence, rules, timestamps, source checks,
and integration limitations. The preflight is not reported as agent execution.
LIVE_EVIDENCE, unknown facilities, changed fixtures/rules, or historical records
that cannot be reproduced exactly return UNAVAILABLE without inference.

The service imports the already tested `build_agent` from
`scripts/test_akamai_decision_tool.py` and the existing Akamai compatibility model
helpers from `scripts/test_akamai_strands.py`. The adapter and decision rules are
unchanged. The sole agent tool is `evaluate_operating_status`; it can only read
the selected scenario and evaluate the deterministic policy. Additional hooks
allow one call with the exact saved facility ID and check the execution ledger
before the next model request. There are no approval, override, notification,
HTTP-write, or arbitrary-fetch tools.

The existing `validate_briefing` checks strict AI JSON selections against the
authoritative Python result. `render_briefing` renders explanation text in Python
from those validated rules and references. This is an AI-assisted selection of
explanation, not unrestricted AI-authored prose. Tool confirmation requires an
actual agent tool call whose entire result matches the saved evaluation. The
parent process checks returned identity, conclusion, references, and rendered
text again before returning the response.

Responses include facility/evaluation identity, authoritative recommendation,
provenance at evaluation, saved references/timestamps, response timestamp,
validation status, tool confirmation, and model-completion status. Only VALIDATED
reports successful validation. FALLBACK is explicitly **DETERMINISTIC FALLBACK**;
UNAVAILABLE, TIMEOUT, and ERROR never claim a successful AI briefing. Unsupported
or mismatched snapshots receive no generated explanation. Saved simulated
evidence remains SIMULATED DEMO regardless of successful inference. AI output
never finalizes a decision or changes its operating posture.

## Local security and limits

- Disabled by default through `CLOSUREOPS_AI_BRIEFING_ENABLED=false`.
- Requires the existing local-demo write opt-in because all POST routes retain
  the existing guard. The inference route itself makes no database writes.
- Actual loopback peer, local Host, approved browser Origin, rejected forwarding
  headers, JSON-only requests, strict body schema, and 16 KiB request-size limit.
- Dedicated 10 requests/minute local inference bucket and one inference process
  at a time per server process. Busy requests return UNAVAILABLE with reason BUSY.
- At most three model calls, one exact decision-tool execution, 1,024 output
  tokens per model call, existing 30-second provider timeout and zero HTTP retries.
- Spawned worker has a 90-second overall inference deadline. The parent terminates
  it on timeout; bounded termination cleanup can add up to ten seconds. The
  browser request timeout is 105 seconds, with no automatic inference retry.
- A persisted snapshot is bounded to 512 KiB before starting a worker.
- Key stays in the backend process environment. No key, provider exception body,
  raw model output, or model trace is returned. Worker logging/callback output is
  suppressed; errors use fixed categories. Health reveals only the server opt-in
  capability, not credential configuration, authentication, or provider health.

These are local-demo controls, not user authentication. Run a single Uvicorn
process on loopback. Do not publish, tunnel, proxy, or deploy this endpoint.

## Exact private startup and manual inference verification

Authenticated inference was **not** run during Task 10B implementation. The
commands below are for the user to run privately when ready. Stop the existing
port-8001 server with Ctrl+C first so it can load the new route and flags. From
the repository root in a private PowerShell terminal:

```powershell
$briefingKey = Read-Host 'Akamai inference key (private)' -AsSecureString
$briefingBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($briefingKey)
try {
    $env:AKAMAI_INFERENCE_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($briefingBstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($briefingBstr)
    Remove-Variable briefingBstr, briefingKey
}
$env:CLOSUREOPS_LOCAL_DEMO_WRITES='true'
$env:CLOSUREOPS_AI_BRIEFING_ENABLED='true'
$env:CLOSUREOPS_DEMO_DATABASE='backend/data/manager-workflow-demo.sqlite3'
try {
    .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
} finally {
    Remove-Item Env:\AKAMAI_INFERENCE_KEY -ErrorAction SilentlyContinue
    $env:CLOSUREOPS_AI_BRIEFING_ENABLED='false'
}
```

The plaintext key is present only where the backend provider requires it, in
the process environment; do not echo it or include it in screenshots. The script
does not load `.env` files or set any Vite credential variable.

In a second terminal:

```powershell
cd .\frontend
npm run dev
```

Open `http://127.0.0.1:5173`, Refresh API, and evaluate an existing supported demo
scenario or load its saved evaluation ID from the same database. Click **Generate
AI Briefing** only when ready to make the authenticated request. Verify VALIDATED,
the exact saved-result tool confirmation, matching facility/recommendation,
SIMULATED DEMO labeling, and evidence references. A fallback or error is not a
successful agent run. Approval/override remain separate explicit manager actions.

To run the complete manager workflow without inference credentials:

```powershell
$env:CLOSUREOPS_AI_BRIEFING_ENABLED='false'; $env:CLOSUREOPS_LOCAL_DEMO_WRITES='true'; $env:CLOSUREOPS_DEMO_DATABASE='backend/data/manager-workflow-demo.sqlite3'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-proxy-headers
```

## Offline verification and artifacts

Task 10B verification: **211 focused backend tests passed** (28 briefing tests),
**77 frontend unit tests passed**, and **41 browser tests passed**, including the
existing manager workflow. TypeScript, ESLint, Python compilation, and the
production build passed. Ruff is not installed in the existing `.venv`, so no
Python Ruff lint was performed and no dependency was added for it. Vite retained
its existing large MapLibre chunk warning. No authenticated inference was run.

From the root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_ai_briefing.py backend/tests/test_demo_api.py backend/tests/test_decision_tool.py backend/tests/test_api.py -q
.\.venv\Scripts\python.exe -m py_compile backend/app/ai_briefing.py backend/app/api.py backend/app/api_security.py backend/app/main.py
```

From `frontend`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run test:e2e
npm run build
```

Backend tests block HTTP transports and mock inference, including the real
Strands lifecycle with a mocked provider response. Browser tests intercept all
API requests; no authenticated inference or API key is used. They exercise
validated, fallback, unavailable, timeout, mismatch, offline, explicit-trigger,
and narrow-layout behavior. Mocked screenshots are saved to
`frontend/test-results/ai-briefing-mocked-desktop.png` and
`frontend/test-results/ai-briefing-mocked-mobile.png`; they are UI verification,
not evidence of live provider execution.

Briefings are ephemeral and are not added to audit storage. Navigating away or
changing the selected evaluation clears the panel; browser cancellation does
not guarantee an already-started provider request is canceled, although the
server deadline still bounds its worker. Multiple workers/public hosting remain
unsupported. Nationwide NWS alerts remain independent of these synthetic saved
facility evaluations. No thresholds, NWS/USGS retrieval, Akamai adapter, Snoopy
assets, database schema, real notifications, or deployment configuration changed.

## Files changed for Task 10B

| Area | Files |
| --- | --- |
| Backend | `backend/app/ai_briefing.py` (new), `backend/app/api.py`, `backend/app/api_security.py`, `backend/app/main.py` |
| Backend tests | `backend/tests/test_ai_briefing.py` (new), `backend/tests/test_api.py`, `backend/tests/test_demo_api.py` |
| Frontend | `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/api/schemas.ts`, `frontend/src/components/AIBriefingPanel.tsx` (new), `frontend/src/components/RecommendationPanel.tsx`, `frontend/src/lib/settings.ts`, `frontend/src/styles.css` |
| Frontend tests | `frontend/tests/fixtures/ai-briefing.ts` (new), `frontend/tests/unit/ai-briefing.test.ts` (new), `frontend/tests/unit/settings.test.ts`, `frontend/tests/e2e/ai-briefing.spec.ts` (new), `frontend/tests/e2e/settings.spec.ts` |
| Configuration and docs | `.env.example`, `README.md`, `docs/local-demo-api.md`, `docs/system-settings.md`, `docs/browser-ai-briefing.md` (new) |
