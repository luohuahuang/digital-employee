#!/usr/bin/env bash
# Run from the app/ directory.

# Install/sync Python dependencies (fast no-op if already up to date):
pip install -q -r requirements.txt

# Build HTML documentation portal (regenerates ../docs/index.html from markdown sources):
python ../docs/build.py

# Build frontend (first run or when source changes):
(cd web/frontend && npm install && npm run build)

# Start server
python web/server.py
