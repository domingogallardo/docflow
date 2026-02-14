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
DEPLOY_SCRIPT="${DEPLOY_SCRIPT:-${REPO_DIR}/web/deploy.sh}"
TWEET_CONSOLIDATE_SCRIPT="${TWEET_CONSOLIDATE_SCRIPT:-${REPO_DIR}/bin/build_tweet_consolidated.sh}"

file_hash() {
  local path="$1"
  if [ ! -f "${path}" ]; then
    echo ""
    return 0
  fi
  "${PYTHON_BIN}" - "${path}" <<'PY' || true
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(0)
h = hashlib.sha256()
with path.open("rb") as fh:
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
}

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

run_tweet_consolidated=0
for arg in "$@"; do
  if [ "${arg}" = "all" ]; then
    run_tweet_consolidated=1
    break
  fi
done

set +e
"${PYTHON_BIN}" process_documents.py "$@"
status=$?
set -e

echo "[$(date -Iseconds)] Docflow: finished exit=${status}"

tweet_consolidated_status=0
if [ "${status}" -eq 0 ] && [ "${run_tweet_consolidated}" -eq 1 ]; then
  if [ -x "${TWEET_CONSOLIDATE_SCRIPT}" ]; then
    set +e
    "${TWEET_CONSOLIDATE_SCRIPT}" --yesterday
    tweet_consolidated_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: tweet consolidated exit=${tweet_consolidated_status}"
  else
    tweet_consolidated_status=1
    echo "[$(date -Iseconds)] Docflow: tweet consolidated script not executable: ${TWEET_CONSOLIDATE_SCRIPT}"
  fi
elif [ "${run_tweet_consolidated}" -eq 1 ]; then
  echo "[$(date -Iseconds)] Docflow: tweet consolidated skipped (process exit=${status})"
else
  echo "[$(date -Iseconds)] Docflow: tweet consolidated skipped (target is not 'all')"
fi

set +e
"${PYTHON_BIN}" utils/sync_public_highlights.py --year "${YEAR}"
sync_status=$?
set -e

echo "[$(date -Iseconds)] Docflow: highlights sync exit=${sync_status}"

should_deploy=0
if [ "${status}" -eq 0 ] && [ "${sync_status}" -eq 0 ]; then
  should_deploy=1
else
  echo "[$(date -Iseconds)] Docflow: skip deploy (process exit=${status}, highlights exit=${sync_status})"
fi

build_status=0
read_changed=0
if [ "${should_deploy}" -eq 1 ]; then
  if [ -d "web/public/read" ]; then
    read_html="web/public/read/read.html"
    prev_hash="$(file_hash "${read_html}")"
    set +e
    "${PYTHON_BIN}" utils/build_read_index.py "web/public/read"
    build_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: read.html build exit=${build_status}"
    if [ "${build_status}" -eq 0 ]; then
      next_hash="$(file_hash "${read_html}")"
      if [ "${prev_hash}" != "${next_hash}" ]; then
        read_changed=1
        echo "[$(date -Iseconds)] Docflow: read.html changed"
      else
        echo "[$(date -Iseconds)] Docflow: read.html unchanged"
      fi
    fi
  else
    build_status=1
    echo "[$(date -Iseconds)] Docflow: read.html build skipped (missing web/public/read)"
  fi
else
  echo "[$(date -Iseconds)] Docflow: read.html build skipped (process exit=${status}, highlights exit=${sync_status})"
fi

deploy_status=0
if [ "${should_deploy}" -eq 1 ] && [ "${build_status}" -eq 0 ] && [ "${read_changed}" -eq 1 ]; then
  if [ -x "${DEPLOY_SCRIPT}" ]; then
    set +e
    "${DEPLOY_SCRIPT}"
    deploy_status=$?
    set -e
    echo "[$(date -Iseconds)] Docflow: deploy exit=${deploy_status}"
  else
    deploy_status=1
    echo "[$(date -Iseconds)] Docflow: deploy script not executable: ${DEPLOY_SCRIPT}"
  fi
elif [ "${should_deploy}" -eq 1 ] && [ "${build_status}" -ne 0 ]; then
  echo "[$(date -Iseconds)] Docflow: deploy skipped (read.html build exit=${build_status})"
elif [ "${should_deploy}" -eq 1 ]; then
  echo "[$(date -Iseconds)] Docflow: deploy skipped (read.html unchanged)"
else
  echo "[$(date -Iseconds)] Docflow: deploy skipped (process exit=${status}, highlights exit=${sync_status})"
fi

final_status="${status}"
if [ "${final_status}" -eq 0 ] && [ "${tweet_consolidated_status}" -ne 0 ]; then
  final_status="${tweet_consolidated_status}"
fi
if [ "${final_status}" -eq 0 ] && [ "${sync_status}" -ne 0 ]; then
  final_status="${sync_status}"
fi
if [ "${final_status}" -eq 0 ] && [ "${build_status}" -ne 0 ]; then
  final_status="${build_status}"
fi
if [ "${final_status}" -eq 0 ] && [ "${deploy_status}" -ne 0 ]; then
  final_status="${deploy_status}"
fi
exit "${final_status}"
