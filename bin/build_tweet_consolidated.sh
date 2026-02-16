#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.docflow_env"
if [ -f "${ENV_FILE}" ]; then
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILDER="${BUILDER:-${REPO_DIR}/utils/build_daily_tweet_consolidated.py}"
BASE_DIR="$("${PYTHON_BIN}" - <<'PY'
import config as cfg
print(cfg.BASE_DIR)
PY
)"

if [ ! -f "${BUILDER}" ]; then
  echo "❌ Builder not found: ${BUILDER}" >&2
  exit 1
fi

usage() {
  cat <<'EOF'
Usage: bin/build_tweet_consolidated.sh [--yesterday|--day YYYY-MM-DD|--all-days] [--force] [--cleanup-existing]

Modes:
  --yesterday         Build consolidated file for yesterday (default).
  --day YYYY-MM-DD    Build consolidated file for an explicit day.
  --all-days          Scan all tweet folders and build one consolidated per day.
                      By default it skips days that already have both .md and .html.
  --force             Rebuild even if consolidated files already exist.
  --cleanup-existing  Cleanup mode: remove source tweet files only when a consolidated
                      pair already exists for the day. Does not rebuild.
EOF
}

mode="yesterday"
day=""
force=0
cleanup_existing=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yesterday)
      mode="yesterday"
      shift
      ;;
    --day)
      if [ "$#" -lt 2 ]; then
        echo "❌ Missing value for --day" >&2
        usage
        exit 2
      fi
      mode="day"
      day="$2"
      shift 2
      ;;
    --all-days)
      mode="all_days"
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    --cleanup-existing)
      cleanup_existing=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

run_one_day() {
  local target_day="$1"
  local target_year="${target_day:0:4}"
  PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}" \
    "${PYTHON_BIN}" "${BUILDER}" --day "${target_day}" --year "${target_year}"
}

cleanup_one_day_if_consolidated() {
  local target_day="$1"
  local target_year="${target_day:0:4}"
  PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}" \
    "${PYTHON_BIN}" "${BUILDER}" --day "${target_day}" --year "${target_year}" --cleanup-if-consolidated
}

consolidated_exists() {
  local target_day="$1"
  local target_year="${target_day:0:4}"
  local tweets_dir="${BASE_DIR}/Tweets/Tweets ${target_year}"
  local base_name=""
  for base_name in "Tweets ${target_day}" "Consolidado Tweets ${target_day}" "Consolidados Tweets ${target_day}"; do
    local md_path="${tweets_dir}/${base_name}.md"
    local html_path="${tweets_dir}/${base_name}.html"
    if [ -f "${md_path}" ] && [ -f "${html_path}" ]; then
      return 0
    fi
  done
  return 1
}

if [ "${mode}" = "yesterday" ]; then
  day="$("${PYTHON_BIN}" - <<'PY'
from datetime import datetime, timedelta
print((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
PY
)"
  echo "🧾 Building consolidated tweets for yesterday: ${day}"
  if [ "${cleanup_existing}" -eq 1 ]; then
    if consolidated_exists "${day}"; then
      cleanup_one_day_if_consolidated "${day}"
    else
      echo "⏭️  Cleanup skipped for ${day}: no consolidated files"
    fi
    exit 0
  fi
  if [ "${force}" -eq 0 ] && consolidated_exists "${day}"; then
    echo "⏭️  Skip build for ${day}: consolidated files already exist"
    exit 0
  fi
  run_one_day "${day}"
  exit 0
fi

if [ "${mode}" = "day" ]; then
  echo "🧾 Building consolidated tweets for day: ${day}"
  if [ "${cleanup_existing}" -eq 1 ]; then
    if consolidated_exists "${day}"; then
      cleanup_one_day_if_consolidated "${day}"
    else
      echo "⏭️  Cleanup skipped for ${day}: no consolidated files"
    fi
    exit 0
  fi
  if [ "${force}" -eq 0 ] && consolidated_exists "${day}"; then
    echo "⏭️  Skip build for ${day}: consolidated files already exist"
    exit 0
  fi
  run_one_day "${day}"
  exit 0
fi

# mode = all_days
echo "🧾 Scanning all tweet days..."
mapfile -t rows < <("${PYTHON_BIN}" - <<'PY'
from datetime import datetime
from pathlib import Path
import config as cfg

base = Path(cfg.BASE_DIR) / "Tweets"
seen: set[tuple[str, str]] = set()
for year_dir in sorted(base.glob("Tweets *")):
    if not year_dir.is_dir():
        continue
    year = "".join(ch for ch in year_dir.name if ch.isdigit())[-4:]
    if len(year) != 4:
        continue
    for md in year_dir.glob("*.md"):
        if not md.is_file():
            continue
        if md.name.startswith(("Tweets ", "Consolidado Tweets ", "Consolidados Tweets ")):
            continue
        day = datetime.fromtimestamp(md.stat().st_mtime).strftime("%Y-%m-%d")
        seen.add((year, day))

for year, day in sorted(seen):
    print(f"{year}\t{day}")
PY
)

built=0
skipped=0
cleaned=0
failed=0
for row in "${rows[@]}"; do
  IFS=$'\t' read -r year day <<<"${row}"
  if [ "${force}" -eq 0 ] && consolidated_exists "${day}"; then
    if [ "${cleanup_existing}" -eq 1 ]; then
      set +e
      cleanup_one_day_if_consolidated "${day}"
      rc=$?
      set -e
      if [ "${rc}" -eq 0 ]; then
        cleaned=$((cleaned + 1))
      else
        failed=$((failed + 1))
        echo "❌ Cleanup failed for ${day} (year=${year})"
      fi
    fi
    skipped=$((skipped + 1))
    continue
  fi

  if [ "${cleanup_existing}" -eq 1 ]; then
    skipped=$((skipped + 1))
    continue
  fi

  echo "▶️  ${day} (year=${year})"
  set +e
  PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}" \
    "${PYTHON_BIN}" "${BUILDER}" --day "${day}" --year "${year}"
  rc=$?
  set -e
  if [ "${rc}" -eq 0 ]; then
    built=$((built + 1))
  else
    failed=$((failed + 1))
    echo "❌ Failed day ${day} (year=${year})"
  fi
done

if [ "${cleanup_existing}" -eq 1 ]; then
  echo "✅ Consolidated cleanup summary: cleaned=${cleaned} skipped=${skipped} failed=${failed}"
else
  echo "✅ Consolidated build summary: built=${built} skipped=${skipped} cleaned=${cleaned} failed=${failed}"
fi
[ "${failed}" -eq 0 ]
