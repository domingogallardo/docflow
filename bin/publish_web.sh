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

DEPLOY_SCRIPT="${DEPLOY_SCRIPT:-${REPO_DIR}/web/deploy.sh}"

if [ ! -x "${DEPLOY_SCRIPT}" ]; then
  echo "❌ Publish: deploy script not executable: ${DEPLOY_SCRIPT}"
  exit 1
fi

if [ -z "${REMOTE_USER:-}" ] || [ -z "${REMOTE_HOST:-}" ]; then
  echo "❌ Publish: REMOTE_USER and REMOTE_HOST must be set."
  echo "Set them in ~/.docflow_env or pass them in the environment."
  exit 1
fi

if [ -n "${PERSONAL_WEB_DIR:-}" ] && [ ! -d "${PERSONAL_WEB_DIR}/public" ]; then
  echo "❌ Publish: PERSONAL_WEB_DIR must point to a repo with public/."
  echo "PERSONAL_WEB_DIR=${PERSONAL_WEB_DIR}"
  exit 1
fi

if [ -n "${PERSONAL_WEB_DIR:-}" ]; then
  echo "📁 Publish: base site from ${PERSONAL_WEB_DIR}/public"
else
  echo "📁 Publish: base site from ${REPO_DIR}/web/public"
fi

echo "🚀 Publish: deploying web (base site + /read)..."
"${DEPLOY_SCRIPT}"
echo "✅ Publish: done."
