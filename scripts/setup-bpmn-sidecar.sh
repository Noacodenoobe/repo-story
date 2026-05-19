#!/usr/bin/env bash
# Clone (if needed), configure ports, and start bpmn-assistant sidecar.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIDECAR_DIR="${BPMN_ASSISTANT_DIR:-/mnt/ollama/projekty/bpmn-assistant}"
REPO_URL="https://github.com/jtlicardo/bpmn-assistant.git"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

if ! command -v docker >/dev/null 2>&1; then
  log "ERROR: docker not found"
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  log "ERROR: need 'docker compose' (plugin) or docker-compose"
  exit 1
fi

if [[ ! -d "$SIDECAR_DIR/.git" ]]; then
  log "Cloning bpmn-assistant → $SIDECAR_DIR"
  git clone "$REPO_URL" "$SIDECAR_DIR"
fi

cd "$SIDECAR_DIR"

ENV_FILE="src/bpmn_assistant/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp src/bpmn_assistant/.env.example "$ENV_FILE"
  log "Created $ENV_FILE — add at least one API key before generating diagrams."
fi

# Patch host ports in docker-compose.yml (override merge keeps default 8000 otherwise).
if grep -q '"8000:8000"' docker-compose.yml 2>/dev/null; then
  sed -i 's/"8000:8000"/"9748:8000"/' docker-compose.yml
  sed -i 's/"8080:80"/"9749:80"/' docker-compose.yml
  sed -i 's/"3001:3001"/"3017:3001"/' docker-compose.yml
  log "Patched docker-compose.yml → API :9748, UI :9749, layout :3017"
fi

log "Building and starting containers (may take several minutes)…"
"${COMPOSE[@]}" up --build -d

log "Waiting for API…"
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:9748/" >/dev/null 2>&1; then
    log "Sidecar API OK on :9748"
    "${PROJECT_ROOT}/scripts/check-bpmn-sidecar.sh"
    exit 0
  fi
  sleep 2
done

log "WARN: API not responding yet — check: cd $SIDECAR_DIR && docker compose logs"
exit 1
