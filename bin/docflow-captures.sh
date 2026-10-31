#!/usr/bin/env bash
set -euo pipefail
if [ -f "${HOME}/.docflow_env" ]; then
  source "${HOME}/.docflow_env"
fi
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Shared lock covers processing and index rebuilds, including nested captures.
source "${DOCFLOW_LOCK_HELPER:-/Users/domingo/Programacion/computer-ops/ops/bin/docflow_lock.sh}"
exec "${PYTHON_BIN:-python3}" "${REPO_DIR}/capture_queue.py" "$@"
