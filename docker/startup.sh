#!/bin/bash
set -u

# Backend: FastAPI. The proxy strips "${CROSSBAR_ROOT_PATH}/api" before forwarding,
# so --root-path only tells FastAPI its public prefix (OpenAPI/docs URLs).
uvicorn crossbar_llm.api.main:app \
  --host 0.0.0.0 --port 8000 \
  --root-path "${CROSSBAR_ROOT_PATH}/api" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}" &

# Frontend: static React build. Unknown paths fall back to index.html so
# client-side routes (e.g. /dashboard) survive a page reload.
static-web-server --host 0.0.0.0 --port 8501 --root /public \
  --page-fallback /public/index.html &

# Pass docker stop's SIGTERM on to both processes.
trap 'kill -TERM $(jobs -p) 2>/dev/null' TERM INT

# Exit as soon as either process dies, so the container restarts
# instead of staying up half-broken.
wait -n
status=$?
kill -TERM $(jobs -p) 2>/dev/null
exit $status
