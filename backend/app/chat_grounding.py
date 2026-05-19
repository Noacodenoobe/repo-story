"""
Grounding helpers: extract allowed facts from RAG context and sanitize LLM output.
"""
from __future__ import annotations

import re
from typing import List, Set

# Substrings that must appear in context for a ```run``` command to be kept.
_CMD_LINE_RE = re.compile(
    r"^(git\s+clone\s+.+|cd\s+.+|npm\s+install.+|pip\s+install.+|"
    r"python3?\s+.+|make\b.*|cmake\s+.+|ollama\s+.+|pw-cli\s+.+)$",
    re.IGNORECASE | re.MULTILINE,
)

_RUN_BLOCK_RE = re.compile(r"```run\s*\n([\s\S]*?)```", re.IGNORECASE)


def is_meta_system_question(message: str) -> bool:
    """True when user asks what the assistant can see on their machine."""
    norm = message.lower()
    hints = (
        "pliki konfiguracyjne",
        "pliki konfig",
        "widzisz",
        "widzisz plik",
        "dostep do",
        "dostęp do",
        "mojego systemu",
        "moj system",
        "struktur",
        "folder",
        "katalog",
        "sciezk",
        "ścieżk",
        "na dysku",
    )
    return any(h in norm for h in hints)


def extract_commands_from_context(context_parts: List[str]) -> List[str]:
    """
  Extract shell commands explicitly present in retrieved context text.

    Returns:
        Deduplicated command strings in order of appearance.
    """
    blob = "\n".join(context_parts)
    found: List[str] = []
    seen: Set[str] = set()

    # "Komendy: git clone ... | cd ..."
    for segment in re.findall(r"Komendy:\s*([^\n]+)", blob, re.IGNORECASE):
        for part in re.split(r"\s*\|\s*", segment):
            cmd = part.strip()
            if cmd and cmd not in seen:
                seen.add(cmd)
                found.append(cmd)

    for pattern in (
        r"git clone\s+https?://\S+",
        r"git clone\s+\S+",
        r"cd\s+[/~\w][\w./-]*",
        r"npm install\b[^\n|]*",
        r"pip install\b[^\n|]*",
        r"python3?\s+[\w./-]+",
    ):
        for match in re.finditer(pattern, blob, re.IGNORECASE):
            cmd = match.group(0).strip().rstrip(".")
            if cmd and cmd not in seen:
                seen.add(cmd)
                found.append(cmd)

    return found


def build_grounding_instructions(
    message: str,
    context_parts: List[str],
) -> str:
    """
    Build extra prompt lines that constrain the model to retrieved facts.

    Returns:
        Instruction block (may be empty).
    """
    lines: List[str] = []
    commands = extract_commands_from_context(context_parts)

    if is_meta_system_question(message):
        lines.append(
            "CZĘŚĆ A (widoczność systemu): Nie przeglądasz dysku na żywo. "
            "Widzisz tylko: profil systemu i regulamin zindeksowany w bazie wiedzy "
            "(oraz ewentualnie notatki użytkownika). Napisz to wprost w 2–3 zdaniach."
        )
        lines.append(
            "CZĘŚĆ B (instalacja projektu): dopiero potem kroki instalacji z przewodnika "
            "(sekcja howto), jeśli są w kontekście."
        )

    if commands:
        lines.append("DOZWOLONE KOMENDY (kopiuj DOKŁADNIE, nie zmieniaj URL):")
        for cmd in commands[:12]:
            lines.append(f"- {cmd}")
        lines.append(
            "Zakaz: wymyślania innych komend (np. python main.py), innych adresów GitHub "
            "lub pustych punktów listy bez treści z kontekstu."
        )
    elif any(w in message.lower() for w in ("instal", "clone", "git")):
        lines.append(
            "Brak konkretnych komend w kontekście — nie podawaj git clone ani pip; "
            "powiedz, że w bazie brakuje sekcji howto dla tego projektu."
        )

    lines.append(
        "Format źródeł na końcu: [Tytuł przewodnika / sekcja] — dokładnie jak w kontekście."
    )
    return "\n".join(lines)


def _command_in_context(command: str, context_blob: str) -> bool:
    """Return True if command (or its URL) appears in context."""
    cmd = command.strip()
    if not cmd:
        return False
    if cmd in context_blob:
        return True
    norm_ctx = re.sub(r"\s+", " ", context_blob.lower())
    norm_cmd = re.sub(r"\s+", " ", cmd.lower())
    if norm_cmd in norm_ctx:
        return True
    url_match = re.search(r"https?://\S+", cmd)
    if url_match and url_match.group(0) in context_blob:
        return True
    return False


def sanitize_run_blocks(answer: str, context_parts: List[str]) -> str:
    """
    Remove ```run``` blocks whose commands are not grounded in RAG context.

    Args:
        answer: Raw LLM answer.
        context_parts: Context strings sent to the model.

    Returns:
        Sanitized answer text.
    """
    context_blob = "\n".join(context_parts)

    def replacer(match: re.Match[str]) -> str:
        cmd = match.group(1).strip()
        if _command_in_context(cmd, context_blob):
            return match.group(0)
        return ""

    return _RUN_BLOCK_RE.sub(replacer, answer).strip()
