# Digest-pinned Python 3.12 image, verified for linux/amd64.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CLOSUREOPS_ENVIRONMENT=container_readonly CLOSUREOPS_BIND_HOST=0.0.0.0 \
    CLOSUREOPS_LOCAL_DEMO_WRITES=false CLOSUREOPS_AI_BRIEFING_ENABLED=false \
    CLOSUREOPS_DEMO_DATABASE=/var/lib/closureops/docker-demo.sqlite3
WORKDIR /app
COPY backend/requirements-docker.lock /app/requirements-docker.lock
RUN python -m pip install --no-cache-dir --no-deps --require-hashes --only-binary=:all: -r requirements-docker.lock && python -m pip check \
    && groupadd --gid 10001 closureops && useradd --uid 10001 --gid 10001 --no-create-home closureops \
    && mkdir -p /var/lib/closureops && chown 10001:10001 /var/lib/closureops
COPY backend/__init__.py /app/backend/__init__.py
COPY backend/app /app/backend/app
COPY scripts/test_akamai_strands.py scripts/test_akamai_decision_tool.py scripts/usgs_diagnostics.py scripts/init_docker_demo.py /app/scripts/
USER 10001:10001
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-proxy-headers"]
