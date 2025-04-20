#!/bin/bash

# Run backend
cd crossbar_llm/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --root-path "$REACT_APP_CROSSBAR_LLM_ROOT_PATH/api" &

# Run frontend
cd ../..

# if /public/$REACT_APP_CROSSBAR_LLM_ROOT_PATH not exists, create and move the content of public to it
# removes "/" present at the beginning of the path
NORMALIZED_PATH="${REACT_APP_CROSSBAR_LLM_ROOT_PATH:1}"
if [ ! -d "public/$NORMALIZED_PATH" ]; then

    mkdir -p public/$NORMALIZED_PATH
    mv public/* public/$NORMALIZED_PATH/
fi

# Run frontend server
static-web-server --host 0.0.0.0 --port 8501
