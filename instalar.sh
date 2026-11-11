#!/usr/bin/env bash
# macOS / Linux: bash instalar.sh
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then echo "Instala Python 3.10+ desde https://www.python.org/downloads/"; exit 1; fi
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e .
.venv/bin/python -m yt_automizer setup
