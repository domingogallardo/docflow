#!/usr/bin/env bash
set -euo pipefail

# Unified wrapper for pipeline execution.
# - Loads ~/.docflow_env if it exists
# - Runs process_documents.py
# - Rebuilds local intranet browse/reading/working/done outputs

ENV_FILE="${HOME}/.docflow_env"
if [ -f "${ENV_FILE}" ]; then
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULT_INTRASITE_BASE_DIR="$(${PYTHON_BIN} - <<'PY' 2>/dev/null || true
import config as cfg
print(cfg.BASE_DIR)
PY
)"
INTRANET_BASE_DIR="${INTRANET_BASE_DIR:-${DEFAULT_INTRASITE_BASE_DIR}}"

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

intranet_browse_status=0
intranet_reading_status=0
intranet_working_status=0
intranet_done_status=0
intranet_status=0
if [ "${status}" -eq 0 ]; then
  if [ -n "${INTRANET_BASE_DIR}" ] && [ -d "${INTRANET_BASE_DIR}" ]; then
    set +e
    "${PYTHON_BIN}" utils/build_browse_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_browse_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: intranet browse build exit=${intranet_browse_status}"

    set +e
    "${PYTHON_BIN}" utils/build_reading_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_reading_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: intranet reading build exit=${intranet_reading_status}"

    set +e
    "${PYTHON_BIN}" utils/build_working_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_working_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: intranet working build exit=${intranet_working_status}"

    set +e
    "${PYTHON_BIN}" utils/build_done_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_done_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: intranet done build exit=${intranet_done_status}"

    if [ "${intranet_browse_status}" -ne 0 ] || [ "${intranet_reading_status}" -ne 0 ] || [ "${intranet_working_status}" -ne 0 ] || [ "${intranet_done_status}" -ne 0 ]; then
      intranet_status=1
    fi
  else
    intranet_status=1
    echo "[$(date -Iseconds)] Docflow: intranet build skipped (invalid INTRANET_BASE_DIR='${INTRANET_BASE_DIR}')"
  fi
else
  echo "[$(date -Iseconds)] Docflow: intranet build skipped (process exit=${status})"
fi

final_status="${status}"
if [ "${final_status}" -eq 0 ] && [ "${intranet_status}" -ne 0 ]; then
  final_status="${intranet_status}"
fi

exit "${final_status}"
