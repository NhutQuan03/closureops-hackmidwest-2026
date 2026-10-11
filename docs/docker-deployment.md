# ClosureOps Docker packaging — Task 11A

This packages the existing React console and FastAPI application for **local,
read-only verification**. It does not deploy to Akamai Cloud, implement
authentication, or enable manager writes/inference. The working Windows demo and
its `backend/data/manager-workflow-demo.sqlite3` are not imported or modified.

## Build and run (PowerShell)

Install/start Docker Desktop with Linux containers. Run from the repository root:

```powershell
Set-Location C:\Users\14172\Downloads\ClosureOps
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose ps
```

Open **http://127.0.0.1:8080/**. Only Nginx port 8080 is published, bound to loopback.
FastAPI listens on port 8001 inside the dedicated Docker bridge. `/api/*` uses
Nginx's fixed backend destination; the browser never calls the Windows port 8001.
SPA paths fall back to `index.html`; existing sidebar navigation remains unchanged.
The bridge permits outbound HTTPS for the existing public NWS integration (an
[`internal` network](https://docs.docker.com/reference/compose-file/networks/#internal)
would disable that outbound connection). It is not a production trust boundary.

Stop containers while preserving the audit volume:

```powershell
docker compose stop
# Or remove containers/network, retaining the named database volume:
docker compose down
```

Restart stopped containers with `docker compose up -d --wait`. Do not add `--volumes`
to `down` when preserving Docker audit history.

## Dependencies and images

- Backend: digest-pinned `python:3.12-slim-bookworm`, application UID/GID 10001,
  unchanged `backend.app.main:app` import, Uvicorn with `--no-proxy-headers`.
- `backend/requirements-docker.in` pins the runtime dependencies from the working
  environment, including `strands-agents[openai]` and OpenAI. The checked-in
  `requirements-docker.lock` pins all 61 runtime dependencies and their wheel
  SHA-256 hashes. Installation uses `--require-hashes --no-deps --only-binary=:all:`
  and runs `pip check`. Windows virtual environments and test dependencies are excluded.
- The runtime lock was resolved and tested for **Linux x86_64 / Python 3.12**.
  Regenerate/review hashes before using an ARM instance or another Python version.
- Frontend: digest-pinned Node 24 build stage runs `npm ci` and the production
  build from the existing `package-lock.json`. Digest-pinned Nginx serves only
  compiled assets as its non-root `nginx` user. Vite does not run in the image.
- The build explicitly sets empty `VITE_API_BASE_URL` for same-origin `/api`
  requests. Local development without this setting still uses port 8001.
  Settings displays `Same origin · /api` for Docker.
- Dockerfile-specific build-context allowlists exclude secrets, `.env` files,
  databases, `.venv`, Git, `node_modules`, caches, tests and private artifacts.
  No credentials are passed as build arguments or runtime environment variables.

To regenerate the Linux lock deliberately after a dependency update:

```powershell
.\.venv\Scripts\python.exe scripts/generate_docker_lock.py --constraints
New-Item -ItemType Directory -Force artifacts/docker | Out-Null
docker run --rm --mount "type=bind,source=$PWD/backend/requirements-docker.in,target=/input.in,readonly" --mount "type=bind,source=$PWD/backend/requirements-docker.constraints.txt,target=/constraints.txt,readonly" --mount "type=bind,source=$PWD/artifacts/docker,target=/output" python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 python -m pip install --dry-run --ignore-installed --report /output/requirements-report.json -r /input.in -c /constraints.txt
.\.venv\Scripts\python.exe scripts/generate_docker_lock.py --report artifacts/docker/requirements-report.json
docker compose build
```

Constraints capture installed package names/versions only. Review their changes
and the resolved lock; the ignored pip report is not a deployment artifact.

## Read-only security boundary

Compose fixes `CLOSUREOPS_LOCAL_DEMO_WRITES=false` and
`CLOSUREOPS_AI_BRIEFING_ENABLED=false`, without an `env_file` or provider keys.
`container_readonly` mode permits reads from loopback and the configured bounded
private IPv4 Docker subnet, retains local upstream Host checks, forwarding-header
rejection, request limits and existing rate limits, and **refuses startup** if
either privileged flag is enabled. Nginx independently denies API methods other
than GET/HEAD/OPTIONS, returning JSON 403 for manager writes and AI briefing requests.
It strips forwarding, authorization and cookie headers. This mode does not alter
the existing direct-loopback manager workflow's authorization guards.

Both containers use read-only root filesystems, temporary `/tmp` mounts, dropped
capabilities and `no-new-privileges`. The isolated audit volume is writable because
SQLite can initialize its schema and the explicit fixture command needs storage.
Read-only describes API capabilities; it is not immutable database storage.
Neither a demo manager label nor Docker network membership authenticates a person.
The Docker package cannot generate an AI briefing or a new evaluation through HTTP.
It can display existing synthetic records initialized by the explicit command below.
No real employee notifications or facility changes occur.

Default network subnet: `172.30.11.0/24`. If it overlaps an existing Docker/VPN
network, set a different unused RFC1918 subnet (/24 or smaller) before starting:

```powershell
$env:CLOSUREOPS_DOCKER_SUBNET = '172.30.12.0/24'
docker compose up -d --wait
```

Nginx fixes the upstream Host rather than trusting the browser's Host. Keep the
frontend loopback-bound for this phase; do not tunnel/publish it as an authenticated
application. Shared backend rate limits remain conservative because all requests
arrive through the proxy.

## Isolated SQLite and optional synthetic fixture

Compose creates `closureops-docker-demo_audit`, mounted at `/var/lib/closureops`.
The database is `/var/lib/closureops/docker-demo.sqlite3`. A fresh volume has an
empty audit list. No operational database is baked into either image or bind-mounted.

To explicitly initialize one historical synthetic severe-flood evaluation,
synthetic APPROVE record and generated simulated notification plan in an **empty**
Docker database:

```powershell
docker compose exec -T backend python scripts/init_docker_demo.py --initialize-synthetic-records
```

This is a trusted operator CLI operation, not an HTTP endpoint or an AI action.
It runs only in the configured Linux container and targets the fixed Docker
database path. It refuses to overwrite any existing evaluation, decision or plan.
The synthetic record is clearly `SIMULATED DEMO`; notifications are only
`GENERATED_SIMULATED`. Refresh API/History in the browser to view it.

Persistence check:

```powershell
$before = Invoke-RestMethod http://127.0.0.1:8080/api/audit
docker compose restart backend
docker compose up -d --wait
$after = Invoke-RestMethod http://127.0.0.1:8080/api/audit
$before.decision_id
$after.decision_id
```

The same decision IDs should remain. A volume is persistence, not a backup.

## Verification

With containers healthy:

```powershell
powershell -NoProfile -File scripts/verify_docker.ps1
Invoke-RestMethod http://127.0.0.1:8080/api/health
Invoke-RestMethod http://127.0.0.1:8080/api/facilities
Invoke-RestMethod http://127.0.0.1:8080/api/demo/scenarios
Invoke-RestMethod http://127.0.0.1:8080/api/nws/alerts/active
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_readonly.py backend/tests/test_demo_api.py backend/tests/test_ai_briefing.py -q
Set-Location frontend
npm ci
npm run typecheck
npm run lint
npm run test
npm run test:e2e:docker
```

The Docker browser checks use installed Microsoft Edge, actual same-origin APIs,
the actual OpenFreeMap style/vector tiles, retained attribution, desktop/mobile
navigation, and live NWS refresh. Screenshots and the NWS verification result go
to ignored `artifacts/docker/`. NWS failure/stale responses are recorded and marked
as a skipped live-source success check, never reported as a successful live fetch.
The browser map success check requires internet access and WebGL; the existing
coordinate/selection fallback still works when the basemap is unavailable.

`verify_docker.ps1` checks image environment variable **names**, application artifact
paths, container users/filesystem/capabilities, unpublished backend, loopback frontend,
volume type, safe public health fields, and direct backend rejection of privileged
requests independently of Nginx. It does not read host secrets or claim
a forensic scan of every base-image byte.

Verified locally on October 11, 2026: both images built successfully and both
containers were healthy; health/facilities/scenarios/audit reads passed through
Nginx; manager writes, notification-plan creation and AI inference returned 403;
the isolated synthetic audit record survived a normal backend restart unchanged;
the original Windows demo database SHA-256 remained unchanged. The actual NWS
request returned `LIVE` at `2026-10-11T08:13:43.809072Z`, examined 507 alerts and
displayed five, with Jefferson applicability `NOT_ASSESSED`. This is verification
evidence, not a promise that those alerts remain current. OpenFreeMap dark vector
tiles, worker rendering, attribution, sidebar navigation and mobile layout passed
against the production container. Focused backend tests: 148 passed. Frontend:
83 unit tests and 44 existing browser tests passed; all three Docker browser tests
passed; typecheck, lint and production build passed. Existing bundle-size and
third-party annotation warnings remain. Screenshots: `overview-desktop.png`,
`settings.png`, `facilities-mobile.png`, `nws-desktop.png` in `artifacts/docker/`.

## Before eventual Akamai Cloud deployment

No cloud resources or deployment are created here. A later phase must select an
x86_64 Ubuntu instance and review the locked dependencies/base images for security
updates; install Docker/Compose; configure HTTPS, domain and host firewall; manage
volume ownership, backups and recovery; and review outbound access and NWS contact
configuration. Retain the unpublished backend and disabled writes/inference for a
public read-only demo. Any privileged private workflow needs **backend-enforced
authentication/authorization**, secret provisioning and a separate security review
before changing capabilities. Do not enable privileged flags in this Docker mode.
The loopback-only Compose port must not be changed to public exposure as part of
Task 11A. Public deployment remains explicitly unapproved.
