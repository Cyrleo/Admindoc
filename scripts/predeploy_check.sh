#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[1/5] Syntax check"
"$PYTHON_BIN" -m py_compile \
  cors/pages/admin_api/permissions.py \
  cors/pages/admin_api/serializers.py \
  cors/pages/admin_api/views.py \
  cors/pages/admin_api/urls.py

echo "[2/5] Django check"
"$PYTHON_BIN" manage.py check

echo "[3/5] Django deploy check"
"$PYTHON_BIN" manage.py check --deploy || true

echo "[4/5] Admin API tests"
"$PYTHON_BIN" manage.py test cors.tests -v 2

echo "[5/5] Role groups bootstrap check"
"$PYTHON_BIN" scripts/init_admin_roles.py

echo "Predeploy checks completed"
