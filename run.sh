#!/bin/bash
set -e

cd "$(dirname "$0")"

# Create venv if needed
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install deps
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Run
echo ""
echo "  Job Hunter → http://localhost:8000"
echo ""
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
