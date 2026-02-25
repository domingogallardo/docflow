#!/usr/bin/env bash
set -euo pipefail

# Daily tweet consolidation wrapper for automated/manual execution.
# - Loads ~/.docflow_env if it exists
# - Runs bin/build_tweet_consolidated.sh --yesterday
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
TWEET_CONSOLIDATE_SCRIPT="${TWEET_CONSOLIDATE_SCRIPT:-${REPO_DIR}/bin/build_tweet_consolidated.sh}"
DEFAULT_INTRASITE_BASE_DIR="$(${PYTHON_BIN} - <<'PY' 2>/dev/null || true
import config as cfg
print(cfg.BASE_DIR)
PY
)"
INTRANET_BASE_DIR="${INTRANET_BASE_DIR:-${DEFAULT_INTRASITE_BASE_DIR}}"

consolidate_status=0
if [ -x "${TWEET_CONSOLIDATE_SCRIPT}" ]; then
  set +e
  "${TWEET_CONSOLIDATE_SCRIPT}" --yesterday
  consolidate_status=$?
  set -e
  echo "[$(date -Iseconds)] Docflow tweet daily: consolidated exit=${consolidate_status}"
else
  consolidate_status=1
  echo "[$(date -Iseconds)] Docflow tweet daily: consolidated script not executable: ${TWEET_CONSOLIDATE_SCRIPT}"
fi

intranet_browse_status=0
intranet_reading_status=0
intranet_working_status=0
intranet_done_status=0
intranet_status=0
if [ "${consolidate_status}" -eq 0 ]; then
  if [ -n "${INTRANET_BASE_DIR}" ] && [ -d "${INTRANET_BASE_DIR}" ]; then
    set +e
    "${PYTHON_BIN}" utils/build_browse_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_browse_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow tweet daily: intranet browse build exit=${intranet_browse_status}"

    set +e
    "${PYTHON_BIN}" utils/build_reading_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_reading_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow tweet daily: intranet reading build exit=${intranet_reading_status}"

    set +e
    "${PYTHON_BIN}" utils/build_working_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_working_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow tweet daily: intranet working build exit=${intranet_working_status}"

    set +e
    "${PYTHON_BIN}" utils/build_done_index.py --base-dir "${INTRANET_BASE_DIR}"
    intranet_done_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow tweet daily: intranet done build exit=${intranet_done_status}"

    if [ "${intranet_browse_status}" -ne 0 ] || [ "${intranet_reading_status}" -ne 0 ] || [ "${intranet_working_status}" -ne 0 ] || [ "${intranet_done_status}" -ne 0 ]; then
      intranet_status=1
    fi
  else
    intranet_status=1
    echo "[$(date -Iseconds)] Docflow tweet daily: intranet build skipped (invalid INTRANET_BASE_DIR='${INTRANET_BASE_DIR}')"
  fi
else
  echo "[$(date -Iseconds)] Docflow tweet daily: intranet build skipped (tweet consolidation exit=${consolidate_status})"
fi

final_status="${consolidate_status}"
if [ "${final_status}" -eq 0 ] && [ "${intranet_status}" -ne 0 ]; then
  final_status="${intranet_status}"
fi

exit "${final_status}"
