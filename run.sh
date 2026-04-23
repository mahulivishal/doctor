#!/usr/bin/env bash
# =============================================================================
# run.sh — Entry point. All logic lives in scripts/pipeline.py
# =============================================================================
set -euo pipefail

# Ensure we're in the project root
cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
  echo "❌ .env not found. Copy .env.template to .env and fill in your values."
  exit 1
fi

# Pass all args straight to the Python pipeline
python3 scripts/pipeline.py "$@"