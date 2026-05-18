#!/usr/bin/env bash
# =============================================================================
# Repo Opowieść — skrypt uruchomieniowy.
#
# Uruchamia serwer FastAPI z lokalnego .venv.
# Zgodnie z regulaminem - nie wymaga żadnych globalnych pakietów.
#
# Użycie:
#   ./run.sh                  - uruchom na 127.0.0.1:9743
#   ./run.sh --host 0.0.0.0   - dostęp z sieci LAN (UWAGA: brak uwierzytelnienia!)
#   ./run.sh --port 9001      - inny port
#   ./run.sh --reload         - auto-reload (dla developmentu)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

C_RED=$'\033[1;31m'
C_GRN=$'\033[1;32m'
C_YEL=$'\033[1;33m'
C_BLU=$'\033[1;34m'
C_RST=$'\033[0m'

log()  { echo "${C_BLU}==>${C_RST} $*"; }
ok()   { echo "${C_GRN}✓${C_RST} $*"; }
warn() { echo "${C_YEL}!${C_RST} $*"; }
err()  { echo "${C_RED}✗${C_RST} $*" >&2; }

# Parametry domyślne
HOST="${API_HOST:-127.0.0.1}"
PORT="${API_PORT:-9743}"
RELOAD=""

# Argumenty
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)   HOST="$2"; shift 2 ;;
    --port)   PORT="$2"; shift 2 ;;
    --reload) RELOAD="--reload"; shift ;;
    -h|--help)
      grep "^# " "$0" | sed 's/^# //'
      exit 0
      ;;
    *)
      err "Nieznany argument: $1"
      exit 1
      ;;
  esac
done

# Sprawdzenie .venv
if [[ ! -d ".venv" ]]; then
  err "Brak .venv. Uruchom najpierw: ./setup.sh"
  exit 1
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"

if ! python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  err "Brak zależności w .venv. Uruchom: ./setup.sh"
  exit 1
fi

# Sprawdzenie Ollamy (informacyjnie, nie blokujemy startu)
if command -v curl >/dev/null 2>&1; then
  if curl -sf "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    ok "Ollama odpowiada na localhost:11434"
  else
    warn "Ollama nie odpowiada na localhost:11434"
    warn "Uruchom w drugim terminalu: ollama serve"
    warn "Aplikacja wystartuje, ale funkcje LLM nie zadziałają."
  fi
fi

# Eksport zmiennych dla aplikacji
export API_HOST="$HOST"
export API_PORT="$PORT"

log "Startuję serwer na http://${HOST}:${PORT}"
exec python -m uvicorn backend.app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  $RELOAD
