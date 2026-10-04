#!/usr/bin/env bash
set -euo pipefail
if [ -f "${HOME}/.docflow_env" ]; then
  source "${HOME}/.docflow_env"
fi
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/remotecontrol"
mkdir -p "${LOG_DIR}"
# Use the same lock as the installed full-pipeline cron, including manual runs.
exec /usr/bin/lockf -k -t 0 "${LOG_DIR}/docflow-all.lock" \
  "${PYTHON_BIN:-python3}" "${REPO_DIR}/capture_queue.py" "$@"
