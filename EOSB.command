#!/bin/bash
# Launcher for macOS and Linux. Always uses the folder it lives in.
cd "$(dirname "$0")"
if [ -x "./runtime/bin/python3" ]; then PY="./runtime/bin/python3"
elif command -v python3 >/dev/null 2>&1; then PY="python3"
else
  echo "Python 3 was not found. Install it, or run tools/setup_runtime.sh"; exit 1
fi
exec "$PY" "./app/main.py"
