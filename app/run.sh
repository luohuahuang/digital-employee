#!/usr/bin/env bash
# Run from the app/ directory.
# Creates a Python venv on first run; subsequent runs reuse it.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/venv"

# ── Create venv if missing ─────────────────────────────────────────────────────
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# ── Activate venv ─────────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Install / sync Python dependencies ────────────────────────────────────────
pip install -q -r requirements.txt

# ── Build HTML documentation portal ───────────────────────────────────────────
python ../docs/build.py

# ── Build frontend ─────────────────────────────────────────────────────────────
(cd web/frontend && npm install --silent && npm run build)

# ── Start server ──────────────────────────────────────────────────────────────
python web/server.py
