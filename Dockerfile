# CROssBAR-LLM agent (crossbar_agent branch) — single image: FastAPI backend + static React build.
#
# The site is served behind a reverse proxy under a path prefix that the proxy STRIPS:
#   https://<host>${PUBLIC_URL}/api/*  ->  container:8000/*   (uvicorn, FastAPI)
#   https://<host>${PUBLIC_URL}/*      ->  container:8501/*   (static-web-server, React)
# PUBLIC_URL is baked into the frontend at build time, so build one image per prefix.

ARG PUBLIC_URL=/llm-staging

# ---------------------------------------------------------------- frontend build
FROM node:22-bookworm AS frontend
ARG PUBLIC_URL
WORKDIR /frontend

# package-lock.json pins one dependency to a git+ssh GitHub URL; there are no
# SSH keys in the build, so fetch it over https instead.
RUN git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"

COPY crossbar_llm/frontend/package.json crossbar_llm/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY crossbar_llm/frontend/ ./
# CRA reads PUBLIC_URL for asset paths and REACT_APP_* for the API base URL.
RUN PUBLIC_URL=$PUBLIC_URL REACT_APP_CROSSBAR_LLM_ROOT_PATH=$PUBLIC_URL npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.12.11-slim-bookworm
ARG PUBLIC_URL
ARG SWS_VERSION=2.34.0
ARG TARGETARCH

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    CROSSBAR_ROOT_PATH=$PUBLIC_URL \
    APP_ENV=production \
    # Trust X-Forwarded-For from the reverse proxy so rate limiting sees real
    # client IPs instead of the proxy's. The container must only be reachable
    # through the proxy for this to be safe.
    FORWARDED_ALLOW_IPS="*"

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# static-web-server (arch-aware so the arm64 build gets a working binary too)
RUN case "$TARGETARCH" in \
      arm64) SWS_ARCH=aarch64 ;; \
      *)     SWS_ARCH=x86_64 ;; \
    esac \
 && curl -fsSL -o /tmp/sws.tar.gz \
      "https://github.com/static-web-server/static-web-server/releases/download/v${SWS_VERSION}/static-web-server-v${SWS_VERSION}-${SWS_ARCH}-unknown-linux-gnu.tar.gz" \
 && tar xzf /tmp/sws.tar.gz -C /tmp \
 && mv /tmp/static-web-server-*/static-web-server /usr/local/bin/ \
 && rm -rf /tmp/sws.tar.gz /tmp/static-web-server-*

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first (cached unless pyproject/uv.lock change). The project itself
# is not installed as a package; PYTHONPATH=/app makes `crossbar_llm` importable.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY crossbar_llm/__init__.py crossbar_llm/__init__.py
COPY crossbar_llm/agent_tools crossbar_llm/agent_tools
COPY crossbar_llm/api crossbar_llm/api
COPY crossbar_llm/orchestrator crossbar_llm/orchestrator
COPY crossbar_llm/paperclip_tools crossbar_llm/paperclip_tools
COPY crossbar_llm/pubtator3_tools crossbar_llm/pubtator3_tools

COPY --from=frontend /frontend/build /public

COPY docker/startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh \
 && mkdir -p /app/crossbar_llm/agent_tools/logs

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/app/startup.sh"]
