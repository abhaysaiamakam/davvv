#!/usr/bin/env bash
set -e

# Change directory to apps/web
cd "$(dirname "$0")/../apps/web"

echo "Starting CropLens Next.js frontend on http://localhost:3000..."
exec npm run dev

