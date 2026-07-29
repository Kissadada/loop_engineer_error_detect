#!/usr/bin/env bash
# Runs lint, then unit tests, then the smoke test, in that order.
# Stops on first failure; exits 0 only if everything passes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUFF="./.venv/bin/ruff"
PYTHON="./.venv/bin/python"

if [ ! -x "$RUFF" ] || [ ! -x "$PYTHON" ]; then
    echo "FAIL: .venv not set up (expected ./.venv/bin/ruff and ./.venv/bin/python)" >&2
    echo "Run: python3 -m venv .venv && ./.venv/bin/pip install ruff==0.16.0 pytest" >&2
    exit 1
fi

echo "== Lint =="
"$RUFF" check .
"$RUFF" format --check .

echo "== Unit tests =="
"$PYTHON" -m pytest -q

echo "== Smoke test =="
./smoke_test.sh

echo "ALL CHECKS PASSED"
