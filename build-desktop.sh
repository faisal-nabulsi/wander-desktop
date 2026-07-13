#!/usr/bin/env bash
# Package Wander Desktop into a standalone macOS .app (beta, for on-device testing).
set -euo pipefail
cd "$(dirname "$0")"

PY=python3.11
echo "== venv + deps (Python 3.11) =="
[ -d .venv-build ] || "$PY" -m venv .venv-build
source .venv-build/bin/activate
python -m pip install --upgrade pip wheel >/dev/null
python -m pip install -r requirements.txt pyinstaller

echo "== pyinstaller build =="
rm -rf build "dist/Wander Desktop" "dist/Wander Desktop.app"
# Explicitly hidden-import every pymobiledevice3 submodule main.py references
# (--collect-submodules misses some deep ones like services.dvt.*).
HIDDEN=$(grep -oE "pymobiledevice3(\.[a-zA-Z0-9_]+)+" src/main.py | sort -u | sed 's/^/--hidden-import=/' | tr '\n' ' ')
echo "hidden imports: $HIDDEN"
pyinstaller --noconfirm --name "Wander Desktop" --windowed \
  --icon wander.icns \
  --add-data "src/templates:templates" \
  --add-data "src/data:data" \
  --add-data "src/static:static" \
  --collect-all pymobiledevice3 \
  --collect-submodules pymobiledevice3 \
  --recursive-copy-metadata pymobiledevice3 \
  --collect-all inquirer3 \
  --collect-all readchar \
  --collect-all pywebview \
  --collect-data pycountry \
  $HIDDEN \
  src/main.py

echo "== result =="
if [ -d "dist/Wander Desktop.app" ]; then
  echo "APP BUILT: dist/Wander Desktop.app"
  du -sh "dist/Wander Desktop.app"
else
  echo "NO .app produced — listing dist/:"; ls -la dist/ || true
fi
