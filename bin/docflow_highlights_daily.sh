#!/usr/bin/env bash
set -euo pipefail

# Daily highlights report wrapper for automated/manual execution.
# - Loads ~/.docflow_env if it exists
# - Builds the previous day's highlights report Markdown

ENV_FILE="${HOME}/.docflow_env"
if [ -f "${ENV_FILE}" ]; then
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HIGHLIGHTS_BUILDER="${HIGHLIGHTS_BUILDER:-${REPO_DIR}/utils/build_daily_highlights_report.py}"
HIGHLIGHTS_INTRASITE_BASE_URL="${HIGHLIGHTS_INTRASITE_BASE_URL:-http://localhost:8080}"

if [ ! -f "${HIGHLIGHTS_BUILDER}" ]; then
  echo "[$(date -Iseconds)] Docflow highlights daily: builder not found: ${HIGHLIGHTS_BUILDER}"
  exit 1
fi

if [ -z "${HIGHLIGHTS_DAILY_DIR:-}" ]; then
  echo "[$(date -Iseconds)] Docflow highlights daily: HIGHLIGHTS_DAILY_DIR is not set (define it in ~/.docflow_env)"
  exit 1
fi

day="$("${PYTHON_BIN}" - <<'PY'
from datetime import datetime, timedelta
print((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
PY
)"
output_path="${HIGHLIGHTS_DAILY_DIR}/Highlights ${day}.md"

mkdir -p "${HIGHLIGHTS_DAILY_DIR}"
set +e
"${PYTHON_BIN}" "${HIGHLIGHTS_BUILDER}" \
  --day "${day}" \
  --output "${output_path}" \
  --intranet-base-url "${HIGHLIGHTS_INTRASITE_BASE_URL}"
status=$?
set -e

echo "[$(date -Iseconds)] Docflow highlights daily: day=${day} output=${output_path} exit=${status}"
exit "${status}"
