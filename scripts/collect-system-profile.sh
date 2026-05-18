#!/usr/bin/env bash
# Collect local system profile as JSON to stdout.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/collect_system_profile.py"
