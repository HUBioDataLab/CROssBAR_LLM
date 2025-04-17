#!/bin/bash

# Run backend
cd crossbar_llm/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --root-path "$CROSSBAR_LLM_ROOT_PATH/api" &

# Run frontend
cd ../..
static-web-server --host 0.0.0.0 --port 8501
