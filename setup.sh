#!/usr/bin/env bash
# =============================================================================
# Repo Analyzer — skrypt instalacyjny.
#
# Zgodnie z regulaminem:
#   - środowisko .venv ŻYJE W KATALOGU PROJEKTU (nie globalnie),
#   - nic nie jest instalowane przez pip --user ani pipx,
#   - skrypt sprawdza wstępne warunki przed startem,
#   - każda ryzykowna operacja jest jasno oznaczona.
#
# Co skrypt robi:
#   1. Sprawdza dostępność: python3, git, ollama.
#   2. Tworzy katalogi robocze (data/, indexes/, reports/, logs/).
#   3. Tworzy lokalne .venv.
#   4. Instaluje zależności z requirements.txt.
#   5. (opcjonalnie) Pobiera wymagane modele Ollamy.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Kolory ułatwiające czytanie
C_RED=$'\033[1;31m'
C_GRN=$'\033[1;32m'
C_YEL=$'\033[1;33m'
C_BLU=$'\033[1;34m'
C_DIM=$'\033[2m'
C_RST=$'\033[0m'

log()  { echo "${C_BLU}==>${C_RST} $*"; }
ok()   { echo "${C_GRN}✓${C_RST} $*"; }
warn() { echo "${C_YEL}!${C_RST} $*"; }
err()  { echo "${C_RED}✗${C_RST} $*" >&2; }

# ----------------------------------------------------------------------------
# 1. Wymagania systemowe
# ----------------------------------------------------------------------------
log "Sprawdzam wymagania systemowe…"

if ! command -v python3 >/dev/null 2>&1; then
  err "Brak 'python3'. Zainstaluj: sudo apt install python3 python3-venv"
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
ok "Python: ${PY_VERSION}"

if ! python3 -c "import venv" >/dev/null 2>&1; then
  err "Brak modułu 'venv'. Zainstaluj: sudo apt install python3-venv"
  exit 1
fi
ok "Moduł venv: dostępny"

if ! command -v git >/dev/null 2>&1; then
  err "Brak 'git'. Zainstaluj: sudo apt install git"
  exit 1
fi
ok "git: $(git --version | head -1)"

OLLAMA_BIN="$(command -v ollama || true)"
if [[ -z "$OLLAMA_BIN" ]]; then
  warn "Brak komendy 'ollama' w PATH."
  warn "Pobierz Ollamę ze strony https://ollama.com/download i uruchom 'ollama serve'."
  warn "Aplikacja uruchomi się BEZ Ollamy, ale funkcje LLM nie zadziałają."
else
  ok "Ollama: $(ollama --version 2>/dev/null | head -1 || echo "obecna")"
fi

# ----------------------------------------------------------------------------
# 2. Katalogi robocze
# ----------------------------------------------------------------------------
log "Tworzę katalogi robocze…"
mkdir -p data/repos indexes reports logs
ok "data/, indexes/, reports/, logs/ — gotowe"

# ----------------------------------------------------------------------------
# 3. Wirtualne środowisko
# ----------------------------------------------------------------------------
VENV_DIR=".venv"
if [[ -d "$VENV_DIR" ]]; then
  warn "Środowisko ${VENV_DIR} już istnieje — pomijam tworzenie."
else
  log "Tworzę środowisko ${VENV_DIR}…"
  python3 -m venv "$VENV_DIR"
  ok "Utworzono ${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Aktualizuję pip…"
pip install --upgrade pip --quiet
ok "pip: $(pip --version | awk '{print $2}')"

# ----------------------------------------------------------------------------
# 4. Zależności Python
# ----------------------------------------------------------------------------
if [[ ! -f requirements.txt ]]; then
  err "Brak pliku requirements.txt. Coś jest nie tak z archiwum."
  exit 1
fi

log "Instaluję zależności z requirements.txt…"
pip install -r requirements.txt --quiet
ok "Zależności zainstalowane w .venv"

# ----------------------------------------------------------------------------
# 5. Modele Ollamy
# ----------------------------------------------------------------------------
if [[ -n "${OLLAMA_BIN:-}" ]]; then
  echo
  log "Sprawdzam dostępne modele Ollamy…"

  REQUIRED_MODELS=(
    "qwen3-coder:latest"
    "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M"
    "nomic-embed-text:latest"
  )

  INSTALLED_LIST="$(ollama list 2>/dev/null || true)"

  MISSING=()
  for m in "${REQUIRED_MODELS[@]}"; do
    if echo "$INSTALLED_LIST" | awk '{print $1}' | grep -Fxq "$m"; then
      ok "Model dostępny: $m"
    else
      warn "Brakuje modelu: $m"
      MISSING+=("$m")
    fi
  done

  if (( ${#MISSING[@]} > 0 )); then
    echo
    warn "Brakujące modele wymagają pobrania (ŁĄCZNIE NAWET KILKA DZIESIĄTEK GB)."
    warn "Zostaną pobrane do ~/.ollama lub /mnt/ollama, NIE do partycji systemowej."
    read -r -p "Pobrać brakujące modele teraz? [t/N] " ans
    if [[ "${ans,,}" == "t" || "${ans,,}" == "tak" || "${ans,,}" == "y" ]]; then
      for m in "${MISSING[@]}"; do
        log "Pobieram model: $m"
        ollama pull "$m" || warn "Nie udało się pobrać $m — spróbuj ręcznie później."
      done
    else
      warn "Pominięto pobieranie. Możesz to zrobić później komendą:"
      for m in "${MISSING[@]}"; do
        echo "    ollama pull $m"
      done
    fi
  fi
fi

# ----------------------------------------------------------------------------
# Podsumowanie
# ----------------------------------------------------------------------------
echo
ok "Instalacja zakończona."
echo
echo "${C_DIM}Aby uruchomić aplikację, wpisz:${C_RST}"
echo "    ./run.sh"
echo
echo "${C_DIM}Aplikacja zostanie udostępniona pod adresem:${C_RST}"
echo "    http://127.0.0.1:8000"
echo
