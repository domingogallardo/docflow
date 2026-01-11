#!/usr/bin/env bash
set -euo pipefail

# Unified wrapper for cron and manual execution.
# - Loads ~/.docflow_env if it exists
# - Runs process_documents.py with the same defaults

ENV_FILE="${HOME}/.docflow_env"
if [ -f "${ENV_FILE}" ]; then
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

YEAR_SOURCE="system_year"
YEAR="$(date +%Y)"
if [ -n "${DOCPIPE_YEAR:-}" ]; then
  YEAR="${DOCPIPE_YEAR}"
  YEAR_SOURCE="DOCPIPE_YEAR"
fi

# If --year is provided via CLI, it takes precedence.
for ((i=1; i<=$#; i++)); do
  arg="${!i}"
  case "${arg}" in
    --year)
      next_index=$((i+1))
      if [ "${next_index}" -le "$#" ]; then
        YEAR="${!next_index}"
        YEAR_SOURCE="cli"
      fi
      ;;
    --year=*)
      YEAR="${arg#--year=}"
      YEAR_SOURCE="cli"
      ;;
  esac
done

echo "[$(date -Iseconds)] Docflow: year=${YEAR} (${YEAR_SOURCE})"

set +e
"${PYTHON_BIN}" process_documents.py "$@"
status=$?
set -e

echo "[$(date -Iseconds)] Docflow: finished exit=${status}"

set +e
"${PYTHON_BIN}" utils/sync_public_highlights.py --year "${YEAR}"
sync_status=$?
set -e

echo "[$(date -Iseconds)] Docflow: highlights sync exit=${sync_status}"

final_status="${status}"
if [ "${final_status}" -eq 0 ] && [ "${sync_status}" -ne 0 ]; then
  final_status="${sync_status}"
fi
exit "${final_status}"
