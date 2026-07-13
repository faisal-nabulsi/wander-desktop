#!/usr/bin/env bash
# Wander Desktop — set up a venv (first run) and launch the app.
#   ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First run: creating virtualenv + installing dependencies…"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

# On macOS the developer-service tunnel needs root (like Xcode). If not root,
# re-run under sudo so pymobiledevice3 can start the tunnel.
if [ "$(uname)" = "Darwin" ] && [ "$(id -u)" != "0" ]; then
  echo "The device tunnel needs admin — re-launching with sudo (enter your Mac password)…"
  exec sudo ./.venv/bin/python src/main.py "$@"
fi

exec ./.venv/bin/python src/main.py "$@"
