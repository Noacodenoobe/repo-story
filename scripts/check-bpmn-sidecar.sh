#!/usr/bin/env bash
# Check bpmn-assistant Docker sidecar health (Phase C1).
set -euo pipefail

API_URL="${BPMN_ASSISTANT_URL:-http://127.0.0.1:9748}"
FE_URL="${BPMN_ASSISTANT_FRONTEND_URL:-http://127.0.0.1:9749}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

check_url() {
  local label="$1"
  local url="$2"
  if curl -sf "$url" >/dev/null 2>&1; then
    log "OK  $label → $url"
    return 0
  fi
  log "FAIL $label → $url"
  return 1
}

failed=0
check_url "API" "$API_URL/" || failed=1
check_url "Frontend" "$FE_URL/" || failed=1

if [[ "$failed" -eq 0 ]]; then
  log "Sidecar bpmn-assistant działa."
  exit 0
fi

log "Sidecar niedostępny. Uruchom:"
log "  cd /mnt/ollama/projekty/bpmn-assistant && docker compose up -d"
exit 1
