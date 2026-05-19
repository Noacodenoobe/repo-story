#!/usr/bin/env bash
# Refresh Repo Opowieść system profile via API (Phase B4 cron helper).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-9743}"
BASE_URL="http://${API_HOST}:${API_PORT}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

if ! command -v curl >/dev/null 2>&1; then
  log "ERROR: curl is required"
  exit 1
fi

if curl -sf "${BASE_URL}/api/health" >/dev/null 2>&1; then
  log "Refreshing profile via ${BASE_URL}/api/system-profile/refresh"
  curl -sf -X POST "${BASE_URL}/api/system-profile/refresh" | python3 -m json.tool 2>/dev/null || true
  exit 0
fi

log "Server offline — collecting profile locally"
PROFILE_JSON="${PROJECT_ROOT}/data/system-profile.json"
mkdir -p "${PROJECT_ROOT}/data"
bash "${PROJECT_ROOT}/scripts/collect-system-profile.sh" > "${PROFILE_JSON}"
log "Profile saved to ${PROFILE_JSON} (upload when server is running)"
