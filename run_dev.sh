#!/usr/bin/env bash
set -euo pipefail

# Minimal run_dev.sh — start backend and bun dev frontend (no checks)
# Place this script in the aitravel root and run: ./run_dev.sh

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Minimal: start backend and bun dev frontend (no checks)
cd "$BACKEND_DIR"
# Ask which environment to use for the backend
echo "Choose backend Python environment: [conda|venv|none] (default: none)"
read -r ENV_CHOICE
if [ "$ENV_CHOICE" = "conda" ]; then
	echo "Activating conda environment 'travel'..."
	# Try to activate conda env named 'travel'
	if command -v conda >/dev/null 2>&1; then
		# shellcheck disable=SC1091
		eval "$(conda shell.bash hook)"
		conda activate travel || echo "Warning: failed to activate 'travel' conda env"
	else
		echo "Warning: conda not found in PATH; skipping conda activation"
	fi
elif [ "$ENV_CHOICE" = "venv" ]; then
	if [ -f "$BACKEND_DIR/.venv/bin/activate" ]; then
		# shellcheck disable=SC1090
		source "$BACKEND_DIR/.venv/bin/activate"
		echo "Activated venv $BACKEND_DIR/.venv"
	else
		echo "Warning: venv not found at $BACKEND_DIR/.venv"
	fi
else
	echo "No environment activation requested; using system Python."
fi

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

cd "$FRONTEND_DIR"
bun run dev &

wait
