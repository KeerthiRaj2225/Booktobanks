#!/usr/bin/env bash
# One-command start: creates a virtualenv on first run, installs deps, starts the app.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
echo "BankToBooks running at http://127.0.0.1:8000"
exec ./.venv/bin/uvicorn app.main:app --reload --port 8000
