#!/usr/bin/env bash
# Start the OmniFormat backend. Run from gen-ai-content-engine/backend/.
#
# NOTE: --reload is intentionally OFF. The .venv lives inside this directory, so
# `uvicorn --reload` watches site-packages and thrashes in an infinite reload loop.
# When you change backend code, Ctrl+C and re-run this script.
# (If you really want reload: uvicorn main:app --port 8001 --reload --reload-exclude '.venv/*')

set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/uvicorn" ]; then
  echo "Creating .venv and installing deps…"
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port "${PORT:-8001}"
