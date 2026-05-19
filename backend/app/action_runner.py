"""
Safe command execution with whitelist (Phase B1).
"""
from __future__ import annotations

import logging
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config

logger = logging.getLogger(__name__)

# Allowed command prefixes (first token or full pattern match).
_WHITELIST_PREFIXES: Tuple[str, ...] = (
    "apt-cache",
    "apt",
    "systemctl",
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "pw-cli",
    "ollama",
    "which",
    "uname",
    "df",
    "free",
    "nvidia-smi",
    "git",
    "curl",
    "python3",
    "pip",
    "pip3",
)

_BLOCKED_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\brm\b", re.I),
    re.compile(r"\bdd\b", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r">\s*/etc/", re.I),
    re.compile(r">\s*/usr/", re.I),
    re.compile(r"\|\s*sh\b", re.I),
    re.compile(r"&&\s*rm\b", re.I),
    re.compile(r";\s*rm\b", re.I),
)


def _normalize_command(cmd: str) -> str:
    """Collapse whitespace and strip shell wrappers."""
    cleaned = cmd.strip()
    cleaned = re.sub(r"^```\w*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return " ".join(cleaned.split())


def validate_command(cmd: str) -> Tuple[bool, str]:
    """
    Check whether a command may run under the whitelist.

    Returns:
        (allowed, reason) — reason is empty when allowed.
    """
    normalized = _normalize_command(cmd)
    if not normalized:
        return False, "Pusta komenda."

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(normalized):
            return False, f"Zablokowane: wzorzec {pattern.pattern}"

    try:
        tokens = shlex.split(normalized)
    except ValueError as exc:
        return False, f"Niepoprawna składnia: {exc}"

    if not tokens:
        return False, "Brak tokenów komendy."

    base = tokens[0]
    if base.endswith(".sh") or "/" in base and not base.startswith("/usr/bin/"):
        if base not in ("/usr/bin/curl", "/usr/bin/git"):
            return False, f"Niedozwolona ścieżka: {base}"

    allowed = any(
        base == prefix or base.endswith(f"/{prefix}")
        for prefix in _WHITELIST_PREFIXES
    )
    if not allowed:
        return False, f"Komenda '{base}' nie jest na liście dozwolonych."

    if base == "apt" and len(tokens) > 1:
        sub = tokens[1]
        if sub not in ("install", "update", "upgrade", "search", "show", "list", "cache"):
            return False, f"Niedozwolone apt {sub}"

    return True, ""


def assess_risk(cmd: str) -> Dict[str, Any]:
    """
    Return risk analysis without executing (when confirmed=false).
    """
    ok, reason = validate_command(cmd)
    return {
        "allowed": ok,
        "reason": reason,
        "risk_level": "low" if ok else "blocked",
        "command": _normalize_command(cmd),
    }


def run_command(cmd: str, timeout_s: Optional[int] = None) -> Dict[str, Any]:
    """
    Execute a whitelisted command via subprocess.

    Returns:
        Dict with stdout, stderr, exit_code, duration_s.
    """
    normalized = _normalize_command(cmd)
    ok, reason = validate_command(normalized)
    if not ok:
        raise ValueError(reason)

    timeout = timeout_s or config.ACTION_TIMEOUT_S
    log_path = config.ACTIONS_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    proc = subprocess.run(
        normalized,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(config.PROJECT_ROOT),
    )
    duration = round(time.time() - started, 3)

    entry = (
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
        f"exit={proc.returncode} duration={duration}s cmd={normalized!r}\n"
    )
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(entry)

    logger.info("Action run exit=%s cmd=%s", proc.returncode, normalized[:80])

    return {
        "command": normalized,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "exit_code": proc.returncode,
        "duration_s": duration,
    }
