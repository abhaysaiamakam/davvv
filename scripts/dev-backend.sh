#!/usr/bin/env bash
set -e

# Change directory to apps/api
cd "$(dirname "$0")/../apps/api"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment in apps/api/.venv..."
    if command -v uv >/dev/null 2>&1; then
        uv venv .venv
        uv pip install --python .venv -r requirements.txt
    else
        python3 -m venv .venv
        .venv/bin/pip install -r requirements.txt
    fi
fi

echo "Starting CropLens FastAPI backend on http://127.0.0.1:8000 (Docs at /api/v1/docs)..."
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

