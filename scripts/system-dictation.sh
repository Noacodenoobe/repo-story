#!/usr/bin/env bash
# Push-to-talk dictation: record → STT (repo-story) → paste at cursor.
# Requires: pw-record, curl, jq, xdotool (X11) or wl-copy (Wayland paste).
#
# Usage:
#   ./scripts/system-dictation.sh              # record ~5s, transcribe, paste
#   ./scripts/system-dictation.sh --seconds 8
#
# Global hotkey (example, X11 + sxhkd or xbindkeys):
#   ctrl + shift + space
#       /mnt/ollama/projekty/repo-story/scripts/system-dictation.sh
#
set -euo pipefail

REPO_STORY_URL="${REPO_STORY_URL:-http://127.0.0.1:9743}"
SECONDS_RECORD=5
if [[ "${1:-}" == "--seconds" && -n "${2:-}" ]]; then
  SECONDS_RECORD="${2}"
fi

TMP_DIR="$(mktemp -d)"
RAW="${TMP_DIR}/raw.wav"
trap 'rm -rf "$TMP_DIR"' EXIT

if ! command -v pw-record >/dev/null 2>&1; then
  echo "Brak pw-record (PipeWire)." >&2
  exit 1
fi

echo "Nagrywam ${SECONDS_RECORD}s… mów teraz." >&2
pw-record --target "@DEFAULT_SOURCE@" "${RAW}" &
REC_PID=$!
sleep "${SECONDS_RECORD}"
kill "${REC_PID}" 2>/dev/null || true
wait "${REC_PID}" 2>/dev/null || true

if [[ ! -s "${RAW}" ]]; then
  echo "Puste nagranie." >&2
  exit 1
fi

RESP="$(curl -sf -F "audio=@${RAW}" "${REPO_STORY_URL}/api/stt/transcribe")" || {
  echo "STT nieudane — czy serwer działa na ${REPO_STORY_URL}?" >&2
  exit 1
}

TEXT="$(echo "${RESP}" | jq -r '.text // empty')"
if [[ -z "${TEXT}" ]]; then
  echo "Nie rozpoznano mowy." >&2
  exit 1
fi

echo "Tekst: ${TEXT}" >&2

if command -v wl-copy >/dev/null 2>&1; then
  printf '%s' "${TEXT}" | wl-copy
  if command -v wtype >/dev/null 2>&1; then
    wtype -M ctrl -k v
  elif command -v xdotool >/dev/null 2>&1; then
    xdotool key ctrl+v
  else
    echo "Skopiowano do schowka — wklej Ctrl+V." >&2
    exit 0
  fi
elif command -v xdotool >/dev/null 2>&1; then
  xdotool type --delay 12 -- "${TEXT}"
else
  printf '%s\n' "${TEXT}"
fi

echo "Wklejono." >&2
