# Task 10B.2 — Manager situation briefing

The optional browser AI briefing now presents five concise sections:

1. Situation summary
2. Operational implications
3. Recommended response and rule rationale
4. Suggested next steps
5. Evidence limitations and provenance

Displayed prose is **deterministically composed in Python**, not model-authored
natural-language prose. A successful run is labeled **AI-assisted validated
briefing** and **VALIDATED agent execution** only after the existing Strands tool
ledger and strict AI selection validation succeed. The agent, Akamai adapter,
validator, tool invocation, and deterministic engine remain unchanged.

`situation_briefing` adds five bounded, strict text fields to the existing
response. The composer uses saved identity, recommendation, provenance, fired
rule rationale, and only observations/alerts referenced by those rules. The
existing validator requires the agent to select every fired rule and its
supporting references, so these facts are supported by validated agent-selected
evidence. Optional unselected readings are not promoted into the summary.
Composition explains a recommendation already made; it never chooses posture.

For the severe-flood demo, the rationale states that the **synthetic 7 ft gauge
exceeds the 6 ft prototype telework threshold**, and the **applicable severe
warning combined with that reading supports conservative closure**. The
standalone **8 ft closure threshold was not crossed**. The thresholds come from
the saved result; there is no policy or threshold change. Synthetic exposure and
gauge evidence do not prove facility or access-route flooding. Prototype policy
is not official USDA policy.

The UI prominently preserves SIMULATED DEMO, FACILITY_CLOSURE, validated agent
execution when confirmed, and human approval required. It distinguishes the
saved evidence, AI-assisted explanation, deterministic recommendation, and final
human manager decision. Source and evaluation/response timestamps remain
visible. Raw IDs, complete raw explanations, missing timestamps, validation
fields, and execution details are inside **Technical diagnostics**, collapsed
by default, with nested raw explanation and reference disclosures.

## Protections and fallback

The endpoint still accepts only a persisted evaluation ID and `{}`. Exact
scenario/evidence/result binding, the strict AI validator, local guards, request
size/rate limits, timeouts, one-worker concurrency, and backend-only credential
handling remain in place. The parent process also checks that all five returned
sections exactly equal composition from the authoritative saved evaluation;
altered conclusions or injected prose are rejected.

Model rejection/failure may display the same saved-evidence composition as an
explicitly labeled **DETERMINISTIC FALLBACK**, never successful AI execution.
Unsupported or mismatched snapshots produce no briefing. Missing, stale, or
conflicting evidence preserves REVIEW_REQUIRED with no recommended operating
posture. Review acknowledgment authorizes no operating change or notification
plan. Older backends without the structured fields keep their raw explanation
collapsed and show a clear restart message.

No live authenticated inference was made during this task. Tests mock provider
responses and browser API requests. The user has separately verified live
inference through the browser; these presentation changes retain that pathway.
Existing [private startup and verification commands](browser-ai-briefing.md)
are unchanged. Restart the backend on `127.0.0.1:8001` to load the added response
fields, then refresh the browser and explicitly generate a briefing.

## Verification

Final results: **209 focused backend tests**, **82 frontend unit tests**, and
**16 focused browser tests** passed. Typecheck, ESLint, Python compilation, and
the production build passed. Build output retains the existing MapLibre chunk
size and Zod annotation warnings. Python Ruff lint was not run because Ruff is
unavailable in the existing environment; no dependencies were added.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_ai_briefing.py backend/tests/test_decision_tool.py backend/tests/test_demo_api.py -q
.\.venv\Scripts\python.exe -m py_compile backend/app/situation_briefing.py backend/app/ai_briefing.py backend/tests/test_ai_briefing.py frontend/tests/generate_situation_fixtures.py
```

From `frontend`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run test:e2e -- ai-briefing.spec.ts manager-workflow.spec.ts
npm run build
```

The offline UI fixture exporter reads existing saved synthetic API fixtures and
uses the actual Python composer and response model. It makes no model request,
database write, or public data request:

```powershell
.\.venv\Scripts\python.exe frontend/tests/generate_situation_fixtures.py
```

Browser screenshots are UI verification using mocked inference, not evidence of
an authenticated provider run:

- `frontend/test-results/situation-briefing-panel.png`
- `frontend/test-results/situation-briefing-mocked-desktop.png`
- `frontend/test-results/situation-briefing-mocked-mobile.png`

## Files changed

- `backend/app/situation_briefing.py` (new)
- `backend/app/ai_briefing.py`
- `backend/tests/test_ai_briefing.py`
- `frontend/src/api/schemas.ts`
- `frontend/src/components/AIBriefingPanel.tsx`
- `frontend/src/styles.css`
- `frontend/tests/fixtures/ai-briefing.ts`
- `frontend/tests/fixtures/situation-briefings.json` (new)
- `frontend/tests/generate_situation_fixtures.py` (new)
- `frontend/tests/unit/ai-briefing.test.ts`
- `frontend/tests/e2e/ai-briefing.spec.ts`
- `docs/browser-ai-briefing.md`
- `docs/manager-situation-briefing.md` (new)

No manager approvals, audit history, Snoopy assets, retrieval services, decision
rules, credentials, real notifications, deployment, or commits were changed.
Briefings remain ephemeral and limited to exactly reproducible saved demo
evaluations; arbitrary or live snapshots remain unsupported.
