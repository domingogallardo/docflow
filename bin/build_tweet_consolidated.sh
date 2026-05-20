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
Usage: bin/build_tweet_consolidated.sh [--yesterday|--day YYYY-MM-DD|--all-days] [--force] [--cleanup-existing] [--capture-source liked|posted|all]

Modes:
  --yesterday         Build consolidated file for yesterday (default).
  --day YYYY-MM-DD    Build consolidated file for an explicit day.
  --all-days          Scan all tweet folders and build one consolidated per day.
                      By default it skips days that already have both .md and .html.
  --force             Rebuild even if consolidated files already exist.
  --cleanup-existing  Cleanup mode: remove source tweet HTML files only when a consolidated
                      pair already exists for the day. Keeps source Markdown and keeps
                      tweet HTML already in Reading or Done. Does not rebuild.
  --capture-source    Build/cleanup only liked tweets, only posted tweets, or both (`all`).
EOF
}

mode="yesterday"
day=""
force=0
cleanup_existing=0
capture_source="liked"

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
    --capture-source)
      if [ "$#" -lt 2 ]; then
        echo "❌ Missing value for --capture-source" >&2
        usage
        exit 2
      fi
      capture_source="$2"
      case "${capture_source}" in
        liked|posted|all)
          ;;
        *)
          echo "❌ Invalid value for --capture-source: ${capture_source}" >&2
          usage
          exit 2
          ;;
      esac
      shift 2
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

capture_sources() {
  if [ "${capture_source}" = "all" ]; then
    printf '%s\n' liked posted
    return
  fi
  printf '%s\n' "${capture_source}"
}

run_one_day() {
  local target_day="$1"
  local target_source="$2"
  local target_year="${3:-${target_day:0:4}}"
  PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}" \
    "${PYTHON_BIN}" "${BUILDER}" --day "${target_day}" --year "${target_year}" --capture-source "${target_source}"
}

cleanup_one_day_if_consolidated() {
  local target_day="$1"
  local target_source="$2"
  local target_year="${3:-${target_day:0:4}}"
  PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}" \
    "${PYTHON_BIN}" "${BUILDER}" --day "${target_day}" --year "${target_year}" --cleanup-if-consolidated --capture-source "${target_source}"
}

consolidated_exists() {
  local target_day="$1"
  local target_source="$2"
  local target_year="${3:-${target_day:0:4}}"
  local tweets_dir="${BASE_DIR}/Tweets/Tweets ${target_year}"
  local base_name=""
  local base_names=()
  if [ "${target_source}" = "posted" ]; then
    base_names=("Tweets posted ${target_day}")
  else
    base_names=("Tweets ${target_day}" "Consolidado Tweets ${target_day}" "Consolidados Tweets ${target_day}")
  fi
  for base_name in "${base_names[@]}"; do
    local md_path="${tweets_dir}/${base_name}.md"
    local html_path="${tweets_dir}/${base_name}.html"
    if [ -f "${md_path}" ] && [ -f "${html_path}" ]; then
      return 0
    fi
  done
  return 1
}

run_requested_sources_for_day() {
  local target_day="$1"
  local overall_status=0
  local target_source=""

  while IFS= read -r target_source; do
    if [ "${cleanup_existing}" -eq 1 ]; then
      if consolidated_exists "${target_day}" "${target_source}"; then
        set +e
        cleanup_one_day_if_consolidated "${target_day}" "${target_source}"
        rc=$?
        set -e
        if [ "${rc}" -ne 0 ]; then
          overall_status=1
          echo "❌ Cleanup failed for ${target_day} (${target_source})"
        fi
      else
        echo "⏭️  Cleanup skipped for ${target_day} (${target_source}): no consolidated files"
      fi
      continue
    fi

    if [ "${force}" -eq 0 ] && consolidated_exists "${target_day}" "${target_source}"; then
      echo "⏭️  Skip build for ${target_day} (${target_source}): consolidated files already exist"
      continue
    fi

    set +e
    run_one_day "${target_day}" "${target_source}"
    rc=$?
    set -e
    if [ "${rc}" -ne 0 ]; then
      overall_status=1
      echo "❌ Failed day ${target_day} (${target_source})"
    fi
  done < <(capture_sources)

  return "${overall_status}"
}

if [ "${mode}" = "yesterday" ]; then
  day="$("${PYTHON_BIN}" - <<'PY'
from datetime import datetime, timedelta
print((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
PY
)"
  echo "🧾 Building consolidated tweets for yesterday: ${day} (source=${capture_source})"
  run_requested_sources_for_day "${day}"
  exit $?
fi

if [ "${mode}" = "day" ]; then
  echo "🧾 Building consolidated tweets for day: ${day} (source=${capture_source})"
  run_requested_sources_for_day "${day}"
  exit $?
fi

# mode = all_days
echo "🧾 Scanning all tweet days (source=${capture_source})..."
rows_file="$(mktemp "${TMPDIR:-/tmp}/docflow_tweet_days.XXXXXX")"
cleanup_rows_file() {
  rm -f "${rows_file}"
}
trap cleanup_rows_file EXIT

DOCFLOW_CAPTURE_SOURCE="${capture_source}" "${PYTHON_BIN}" - <<'PY' > "${rows_file}"
from datetime import datetime, timedelta
import os
from pathlib import Path
import config as cfg
from utils.markdown_utils import split_front_matter

rollover_raw = os.getenv("DOCFLOW_TWEET_DAY_ROLLOVER_HOUR", "3").strip()
try:
    rollover_hour = int(rollover_raw)
except ValueError:
    rollover_hour = 3
if rollover_hour < 0 or rollover_hour > 23:
    rollover_hour = 3

def operational_day_from_mtime(mtime: float) -> str:
    dt = datetime.fromtimestamp(mtime)
    if rollover_hour > 0 and dt.hour < rollover_hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")

requested_source = os.getenv("DOCFLOW_CAPTURE_SOURCE", "liked").strip().lower()
requested_sources = {"liked", "posted"} if requested_source == "all" else {requested_source}

base = Path(cfg.BASE_DIR) / "Tweets"
seen: set[tuple[str, str, str]] = set()
for year_dir in sorted(base.glob("Tweets *")):
    if not year_dir.is_dir():
        continue
    year = "".join(ch for ch in year_dir.name if ch.isdigit())[-4:]
    if len(year) != 4:
        continue
    for md in year_dir.glob("*.md"):
        if not md.is_file():
            continue
        if md.name.startswith(("Tweets ", "Consolidado Tweets ", "Consolidados Tweets ", "Tweets posted ")):
            continue
        meta, _ = split_front_matter(md.read_text(encoding="utf-8", errors="ignore"))
        source = meta.get("tweet_capture_source", "").strip().lower()
        if source != "posted":
            source = "liked"
        if source not in requested_sources:
            continue
        day = operational_day_from_mtime(md.stat().st_mtime)
        seen.add((year, day, source))

for year, day, source in sorted(seen):
    print(f"{year}\t{day}\t{source}")
PY

built=0
skipped=0
cleaned=0
failed=0
while IFS=$'\t' read -r year day source; do
  if [ -z "${year}" ]; then
    continue
  fi
  if [ "${force}" -eq 0 ] && consolidated_exists "${day}" "${source}" "${year}"; then
    if [ "${cleanup_existing}" -eq 1 ]; then
      set +e
      cleanup_one_day_if_consolidated "${day}" "${source}" "${year}"
      rc=$?
      set -e
      if [ "${rc}" -eq 0 ]; then
        cleaned=$((cleaned + 1))
      else
        failed=$((failed + 1))
        echo "❌ Cleanup failed for ${day} (year=${year}, source=${source})"
      fi
    fi
    skipped=$((skipped + 1))
    continue
  fi

  if [ "${cleanup_existing}" -eq 1 ]; then
    skipped=$((skipped + 1))
    continue
  fi

  echo "▶️  ${day} (year=${year}, source=${source})"
  set +e
  run_one_day "${day}" "${source}" "${year}"
  rc=$?
  set -e
  if [ "${rc}" -eq 0 ]; then
    built=$((built + 1))
  else
    failed=$((failed + 1))
    echo "❌ Failed day ${day} (year=${year}, source=${source})"
  fi
done < "${rows_file}"

rm -f "${rows_file}"
trap - EXIT

if [ "${cleanup_existing}" -eq 1 ]; then
  echo "✅ Consolidated cleanup summary: cleaned=${cleaned} skipped=${skipped} failed=${failed}"
else
  echo "✅ Consolidated build summary: built=${built} skipped=${skipped} cleaned=${cleaned} failed=${failed}"
fi
[ "${failed}" -eq 0 ]
