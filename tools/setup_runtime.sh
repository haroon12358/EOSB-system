#!/bin/bash
# On macOS and Linux the system python3 is used directly; no runtime download
# is needed. This script only checks that it is present.
if command -v python3 >/dev/null 2>&1; then
  echo "python3 found: $(python3 --version). You can run ./EOSB.command"
else
  echo "Install Python 3 (python.org or your package manager), then run ./EOSB.command"
fi
