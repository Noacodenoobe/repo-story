"""
Extract practical hints from README without LLM.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


def read_readme_text(repo_path: Path, max_chars: int = 12000) -> str:
    """Return README content if present."""
    for name in ("README.md", "README.MD", "readme.md", "Readme.md"):
        path = repo_path / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    return ""


def extract_shell_commands(readme: str, max_commands: int = 12) -> List[str]:
    """Pull shell commands from fenced code blocks."""
    commands: List[str] = []
    for block in re.findall(r"```(?:bash|sh|shell)?\s*([\s\S]*?)```", readme, re.I):
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("$"):
                line = line[1:].strip()
            if len(line) > 3 and not line.startswith("<!--"):
                commands.append(line)
            if len(commands) >= max_commands:
                return commands
    return commands


def extract_feature_bullets(readme: str, max_items: int = 8) -> List[str]:
    """Extract bullet points that look like features."""
    items: List[str] = []
    for line in readme.splitlines():
        m = re.match(r"^[\s]*[-*•]\s+(.+)$", line)
        if m and 20 < len(m.group(1)) < 200:
            items.append(m.group(1).strip())
        if len(items) >= max_items:
            break
    return items


def classify_file_roles(repo_path: Path, languages: Dict[str, int]) -> Dict[str, int]:
    """Group files into code, docs, config for charts."""
    code_ext = {".py", ".go", ".js", ".ts", ".tsx", ".jsx", ".c", ".cpp", ".h", ".rs", ".java"}
    doc_ext = {".md", ".rst", ".txt"}
    config_ext = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}

    counts = {"Kod": 0, "Dokumentacja": 0, "Konfiguracja": 0, "Inne": 0}
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(p.startswith(".") for p in path.parts):
            continue
        if "node_modules" in path.parts or "__pycache__" in path.parts:
            continue
        ext = path.suffix.lower()
        if ext in code_ext:
            counts["Kod"] += 1
        elif ext in doc_ext:
            counts["Dokumentacja"] += 1
        elif ext in config_ext:
            counts["Konfiguracja"] += 1
        else:
            counts["Inne"] += 1
    return {k: v for k, v in counts.items() if v > 0}


_SKIP_CMD_PREFIXES = ("if [", "elif ", "else", "fi", "then", "export ", "#")
_SETUP_KEYWORDS = (
    ("git clone", "Sklonuj repozytorium", "Pobierz kod źródłowy z GitHub."),
    ("cd ", "Wejdź do katalogu projektu", "Przejdź do folderu ze sklonowanym kodem."),
    ("make", "Zbuduj program", "Skompiluj projekt poleceniem make (wymaga narzędzi deweloperskich)."),
    ("cmake", "Zbuduj program", "Skonfiguruj i zbuduj projekt przez CMake."),
    ("go build", "Zbuduj program Go", "Skompiluj binarkę Go."),
    ("go install", "Zainstaluj binarkę Go", "Zainstaluj program do GOPATH lub bin."),
    ("pip install", "Zainstaluj zależności Python", "Zainstaluj wymagane pakiety Python."),
    ("npm install", "Zainstaluj zależności Node", "Pobierz biblioteki JavaScript."),
    ("docker", "Uruchom w Dockerze", "Zbuduj lub uruchom kontener Docker."),
    ("install", "Zainstaluj program", "Skopiuj pliki do katalogu systemowego użytkownika."),
    ("cp ", "Skopiuj pliki", "Skopiuj zbudowany program do folderu w PATH."),
    ("mkdir", "Utwórz katalog", "Przygotuj folder docelowy instalacji."),
)


def _is_setup_fragment(line: str) -> bool:
    """True if line is bash control flow, not a standalone user command."""
    s = line.strip().lower()
    return any(s.startswith(p) for p in _SKIP_CMD_PREFIXES)


def _intent_for_command(cmd: str) -> tuple[str, str]:
    """Map command to Polish title and body."""
    lower = cmd.lower()
    for prefix, title, body in _SETUP_KEYWORDS:
        if prefix in lower:
            return title, body
    return "Wykonaj polecenie", "Otwórz terminal i wpisz poniższą komendę. Poczekaj na zakończenie."


def group_install_commands(commands: List[str]) -> List[Dict[str, Any]]:
    """
    Group raw README shell lines into logical howto steps with Polish titles.
    """
    grouped: List[Dict[str, Any]] = []
    path_lines: List[str] = []
    step_num = 0

    def flush_path_step() -> None:
        nonlocal step_num, path_lines
        if not path_lines:
            return
        step_num += 1
        grouped.append({
            "step": step_num,
            "title": "Przygotuj ścieżkę PATH",
            "body": "Dodaj katalog lokalnych programów do PATH (jednorazowo lub w ~/.bashrc).",
            "commands": path_lines[:],
        })
        path_lines = []

    for raw in commands:
        cmd = raw.strip()
        if not cmd or _is_setup_fragment(cmd):
            if "path" in cmd.lower() or "local/bin" in cmd.lower():
                path_lines.append(cmd)
            continue
        if path_lines and not cmd.lower().startswith("export"):
            flush_path_step()
        title, body = _intent_for_command(cmd)
        step_num += 1
        grouped.append({
            "step": step_num,
            "title": title,
            "body": body,
            "commands": [cmd],
        })

    flush_path_step()
    return grouped[:8]


def build_readme_context(repo_path: Path, languages: Dict[str, int]) -> Dict[str, Any]:
    """Aggregate heuristic README data for prompts and fallbacks."""
    readme = read_readme_text(repo_path)
    commands = extract_shell_commands(readme)
    return {
        "readme_excerpt": readme[:8000],
        "commands": commands,
        "howto_grouped": group_install_commands(commands),
        "features": extract_feature_bullets(readme),
        "composition": classify_file_roles(repo_path, languages),
    }
