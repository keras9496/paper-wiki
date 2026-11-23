#!/usr/bin/env sh
# Paper Wiki installer for macOS / Linux.
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "Python 3.10 or newer is required (https://www.python.org/downloads/)."
  exit 1
fi

[ -x .venv/bin/python ] || "$PY" -m venv .venv
echo "Installing packages (this can take a minute) ..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e .

echo
echo "Installation finished. Start Paper Wiki with:"
echo "  $(pwd)/.venv/bin/paperwiki"
