"""Loopback-only demo guards, independent of CORS (which is not authentication)."""

from collections import defaultdict, deque
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
import math
import os
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.manager_decisions import DEFAULT_DATABASE

REACT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_BODY_BYTES = 16 * 1024


@dataclass(frozen=True)
class LocalDemoSettings:
    writes_enabled: bool = False
    environment: str = "local_demo"
    bind_host: str = "127.0.0.1"
    database_path: Path = DEFAULT_DATABASE
    ai_briefing_enabled: bool = False
    container_network: str = "172.30.11.0/24"

    def validate_local(self) -> None:
        if self.environment == "container_readonly":
            if self.bind_host != "0.0.0.0" or self.writes_enabled or self.ai_briefing_enabled:
                raise ValueError("Container mode requires a 0.0.0.0 internal bind with writes and AI inference disabled.")
            network = ip_network(self.container_network, strict=True)
            private_ranges = (ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"), ip_network("192.168.0.0/16"))
            if network.version != 4 or network.prefixlen < 24 or not any(network.subnet_of(private) for private in private_ranges):
                raise ValueError("Container network must be a bounded private IPv4 subnet (/24 or smaller).")
        elif self.environment != "local_demo" or self.bind_host != "127.0.0.1":
            raise ValueError("This API requires local_demo mode and a 127.0.0.1 bind; public/production use requires backend authentication.")
        if type(self.writes_enabled) is not bool:
            raise ValueError("Local demo writes flag must be boolean.")
        if type(self.ai_briefing_enabled) is not bool:
            raise ValueError("AI briefing flag must be boolean.")

    @classmethod
    def from_environment(cls) -> "LocalDemoSettings":
        flag = os.environ.get("CLOSUREOPS_LOCAL_DEMO_WRITES", "false").lower()
        if flag not in {"true", "false"}:
            raise ValueError("CLOSUREOPS_LOCAL_DEMO_WRITES must be true or false.")
        ai_flag = os.environ.get("CLOSUREOPS_AI_BRIEFING_ENABLED", "false").lower()
        if ai_flag not in {"true", "false"}:
            raise ValueError("CLOSUREOPS_AI_BRIEFING_ENABLED must be true or false.")
        return cls(
            writes_enabled=flag == "true",
            ai_briefing_enabled=ai_flag == "true",
            environment=os.environ.get("CLOSUREOPS_ENVIRONMENT", "local_demo"),
            bind_host=os.environ.get("CLOSUREOPS_BIND_HOST", "127.0.0.1"),
            database_path=Path(os.environ.get("CLOSUREOPS_DEMO_DATABASE", str(DEFAULT_DATABASE))),
            container_network=os.environ.get("CLOSUREOPS_CONTAINER_NETWORK", "172.30.11.0/24"),
        )


def error_response(status: int, code: str, message: str,
                   *, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _loopback(peer: str) -> bool:
    try:
        return ip_address(peer).is_loopback
    except ValueError:
        return False


class LocalDemoGuard:
    """Require direct loopback transport, local Host and explicit write opt-in.

    Forwarding headers are rejected; run Uvicorn with --no-proxy-headers. Neither
    an Origin, demo-manager label nor these local checks authenticates a person.
    There is no agent tool registration for HTTP writes.
    """

    def __init__(self, app: ASGIApp, settings: LocalDemoSettings) -> None:
        self.app = app
        self.settings = settings
        # A separate, permanently read-only transport permits the Docker proxy.
        # The local_demo loopback/write/origin boundary remains unchanged.
        self.container_network = ip_network(settings.container_network) if settings.environment == "container_readonly" else None
        # Local transport bounds cardinality; counters are never returned.
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)

        async def reject(status: int, code: str, message: str,
                         headers: dict[str, str] | None = None) -> None:
            await error_response(status, code, message, headers=headers)(scope, receive, send)

        try:
            host = urlsplit("//" + request.headers.get("host", "")).hostname
        except ValueError:
            host = None
        peer = request.client.host if request.client else ""
        allowed_peer = _loopback(peer)
        if self.container_network is not None:
            try:
                allowed_peer = allowed_peer or ip_address(peer) in self.container_network
            except ValueError:
                pass
        if host not in LOCAL_HOSTS or not allowed_peer:
            await reject(403, "LOCAL_ONLY", "This API accepts direct loopback requests with a local Host only.")
            return
        if any(name in request.headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto")):
            await reject(403, "PROXY_NOT_ALLOWED", "Forwarded requests are unsupported by this local demo.")
            return
        write = request.method not in {"GET", "HEAD", "OPTIONS"}
        if write:
            if not self.settings.writes_enabled:
                await reject(403, "DEMO_WRITES_DISABLED", "Local demo writes are disabled; enable the documented local startup flag.")
                return
            origin = request.headers.get("origin")
            # Same-origin /docs requests are local; React is restricted to exact origins.
            approved_origins = {*REACT_ORIGINS, str(request.base_url).rstrip("/")}
            if origin is not None and origin not in approved_origins:
                await reject(403, "ORIGIN_NOT_ALLOWED", "Browser write origin is not approved for this local demo.")
                return
            if request.headers.get("sec-fetch-site") == "cross-site" and origin is None:
                await reject(403, "ORIGIN_REQUIRED", "Cross-site browser writes require an approved Origin.")
                return
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                await reject(415, "JSON_REQUIRED", "Write requests require application/json; uploads are unsupported.")
                return

        if request.url.path.startswith("/api/"):
            path = request.url.path
            bucket, limit = ("read", 60)
            if path == "/api/health":
                bucket, limit = ("health", 120)
            elif write:
                if path.endswith("/ai-briefing"):
                    bucket, limit = ("inference", 10)
                elif path == "/api/evaluations":
                    bucket, limit = ("evaluation", 20)
                elif path.endswith("/notification-plans"):
                    bucket, limit = ("notification", 10)
                else:
                    bucket, limit = ("decision", 10)
            timestamps = self.requests[bucket]
            now = monotonic()
            while timestamps and timestamps[0] <= now - 60:
                timestamps.popleft()
            if len(timestamps) >= limit:
                await reject(429, "RATE_LIMITED", "Too many local demo requests; retry later.",
                             {"Retry-After": str(max(1, math.ceil(60 - (now - timestamps[0]))))})
                return
            timestamps.append(now)

        if write:
            length = request.headers.get("content-length")
            if length is not None:
                try:
                    declared_length = int(length)
                except ValueError:
                    await reject(400, "INVALID_LENGTH", "Invalid Content-Length.")
                    return
                if declared_length < 0:
                    await reject(400, "INVALID_LENGTH", "Invalid Content-Length.")
                    return
                if declared_length > MAX_BODY_BYTES:
                    await reject(413, "BODY_TOO_LARGE", "JSON body exceeds 16 KiB.")
                    return
            # Count actual chunks too, so missing/incorrect Content-Length cannot bypass the cap.
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY_BYTES:
                    await reject(413, "BODY_TOO_LARGE", "JSON body exceeds 16 KiB.")
                    return
                if not message.get("more_body", False):
                    break

            original_receive = receive
            consumed = False

            async def buffered_receive() -> dict:
                nonlocal consumed
                if consumed:
                    return await original_receive()
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            receive = buffered_receive

        async def secure_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (b"cache-control", b"no-store"),
                ])
            await send(message)

        await self.app(scope, receive, secure_send)
