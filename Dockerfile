# syntax=docker/dockerfile:1.7
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: Dockerfile
#   layer: deployment
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-26
#
# The one OCI carrier for the hosted Memory 3.0 service (ADR-098): the existing
# l9-memory-server, signed-agent Streamable HTTP on /mcp, over the canonical
# PostgreSQL store. It adds no server, route or credential of its own.
#
# Publication is not done here. The l9-ci-core container-release action builds
# this file once, pushes one immutable digest and requests the deployment
# (.github/workflows/release-container.yml); l9-deploy runs it from
# .l9/deployment.yaml. A local `docker build` is a test build only.

# Base images are pinned by tag and index digest; build with --platform linux/amd64.
FROM ghcr.io/astral-sh/uv:0.8.4-python3.13-bookworm-slim@sha256:b93f8bbb995fa6469a40978d63278714c442eac4208f7e29529fcd2215584521 AS builder

# Source identity is required, not defaulted: the release action passes the
# exact commit as L9_SOURCE_REVISION, and an image that cannot name its source
# is never built.
ARG L9_SOURCE_REVISION
RUN case "${L9_SOURCE_REVISION:-}" in \
      *[!0-9a-f]*|"") echo "L9_SOURCE_REVISION must be the 40-hex source commit" >&2; exit 1 ;; \
    esac \
    && test "${#L9_SOURCE_REVISION}" -eq 40 \
    || { echo "L9_SOURCE_REVISION must be the 40-hex source commit" >&2; exit 1; }

WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md LICENSE MANIFEST.in ./
COPY src ./src
# The locked server and postgres extras only; the package is installed as a
# wheel, not an editable checkout, so the runtime holds no source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra server --extra postgres

FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS runtime

ARG L9_SOURCE_REVISION
LABEL org.opencontainers.image.title="l9-graphite-memory" \
      org.opencontainers.image.version="3.0.0" \
      org.opencontainers.image.revision="${L9_SOURCE_REVISION}" \
      org.opencontainers.image.source="https://github.com/Quantum-L9/l9-graphiti-memory"

RUN groupadd --gid 10001 memory \
    && useradd --uid 10001 --gid memory --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin memory

COPY --from=builder /opt/venv /opt/venv

# The hosted profile has exactly one canonical store. The guard refuses to start
# on anything but signed-agent HTTP over PostgreSQL, so a missing or overridden
# setting stops the container instead of serving from a local SQLite ledger.
COPY --chmod=0755 <<'EOF' /usr/local/bin/l9-memory-carrier
#!/bin/sh
set -eu
refuse() {
  echo "l9-memory-carrier: $1; the hosted Memory service has no fallback" >&2
  exit 64
}
[ "${L9_MEMORY_STORE_BACKEND:-}" = "postgres" ] \
  || refuse "L9_MEMORY_STORE_BACKEND must be postgres"
[ -n "${L9_MEMORY_POSTGRES_DSN:-}" ] \
  || refuse "L9_MEMORY_POSTGRES_DSN is required"
[ "${L9_MEMORY_HTTP_AUTH_REQUIRED:-}" = "true" ] \
  || refuse "L9_MEMORY_HTTP_AUTH_REQUIRED must be true"
[ "${L9_MEMORY_HTTP_AUTH_MODE:-}" = "signed-agent" ] \
  || refuse "L9_MEMORY_HTTP_AUTH_MODE must be signed-agent"
exec l9-memory-server --transport http --host 0.0.0.0 --port 8200 "$@"
EOF

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/nonexistent \
    L9_SOURCE_REVISION="${L9_SOURCE_REVISION}" \
    L9_MEMORY_STORE_BACKEND=postgres \
    L9_MEMORY_HTTP_AUTH_REQUIRED=true \
    L9_MEMORY_HTTP_AUTH_MODE=signed-agent \
    L9_MEMORY_PROJECTION_BACKEND=none \
    L9_MEMORY_JSON_LOGS=1

USER 10001:10001
WORKDIR /
EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8200/readyz', timeout=3)"]

ENTRYPOINT ["/usr/local/bin/l9-memory-carrier"]
