#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-venv}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Virtualenv '$VENV_DIR' missing, creating it"
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m ensurepip --upgrade
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

echo "Venv tools fixed: use 'source $VENV_DIR/bin/activate'"
