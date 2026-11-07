#!/usr/bin/env bash
set -e

# Change directory to apps/api
cd "$(dirname "$0")/../apps/api"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Initializing..."
    if command -v uv >/dev/null 2>&1; then
        uv venv .venv
        uv pip install --python .venv -r requirements.txt
    else
        python3 -m venv .venv
        .venv/bin/pip install -r requirements.txt
    fi
fi

echo "Running backend test suite with pytest..."
exec .venv/bin/pytest -v "$@"

