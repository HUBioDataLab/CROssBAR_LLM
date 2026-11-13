#!/bin/bash

# Run backend
cd crossbar_llm/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --root-path "$REACT_APP_CROSSBAR_LLM_ROOT_PATH/api" &

# Run frontend
cd ../..
static-web-server --host 0.0.0.0 --port 8501 &

# Pass docker stop's SIGTERM on to both processes
trap 'kill -TERM $(jobs -p) 2>/dev/null' TERM INT

# Exit as soon as either process dies, so the container restarts
# instead of staying up without a backend
wait -n
status=$?
kill -TERM $(jobs -p) 2>/dev/null
exit $status
