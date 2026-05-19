"""
Konfiguracja aplikacji Repo Opowieść.

Wszystkie ścieżki, modele i parametry w jednym miejscu.
Wartości można nadpisać przez zmienne środowiskowe.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Ścieżki katalogowe (zgodne z regulaminem: wszystko na /mnt/ollama)
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]  # .../repo-analyzer
DATA_DIR: Path = Path(os.getenv("REPO_ANALYZER_DATA", PROJECT_ROOT / "data"))
REPOS_DIR: Path = DATA_DIR / "repos"
INDEXES_DIR: Path = Path(os.getenv("REPO_ANALYZER_INDEXES", PROJECT_ROOT / "indexes"))
REPORTS_DIR: Path = Path(os.getenv("REPO_ANALYZER_REPORTS", PROJECT_ROOT / "reports"))
LOGS_DIR: Path = Path(os.getenv("REPO_ANALYZER_LOGS", PROJECT_ROOT / "logs"))
KNOWLEDGE_DB: Path = Path(os.getenv("KNOWLEDGE_DB", DATA_DIR / "knowledge.db"))
EXPORTS_DIR: Path = REPORTS_DIR / "exports"

for _d in (DATA_DIR, REPOS_DIR, INDEXES_DIR, REPORTS_DIR, LOGS_DIR, EXPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

FRONTEND_DIR: Path = PROJECT_ROOT / "frontend" / "public"


# ---------------------------------------------------------------------------
# Konfiguracja Ollama
# ---------------------------------------------------------------------------
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "300"))

# Modele - zgodnie z analizą project_setup_analysis.md (TOP 3)
MODEL_CODER: str = os.getenv("MODEL_CODER", "qwen3-coder:latest")
MODEL_POLISH: str = os.getenv("MODEL_POLISH", "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M")
MODEL_EMBED: str = os.getenv("MODEL_EMBED", "nomic-embed-text:latest")
MODEL_VISION: str = os.getenv("MODEL_VISION", "qwen3-vl:8b")  # opcjonalny

# Parametry generowania
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_NUM_CTX: int = int(os.getenv("LLM_NUM_CTX", "8192"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))


# ---------------------------------------------------------------------------
# Konfiguracja indeksowania
# ---------------------------------------------------------------------------
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))   # znaki w fragmencie
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))
MAX_FILE_SIZE_KB: int = int(os.getenv("MAX_FILE_SIZE_KB", "500"))  # pomijaj duże pliki
TOP_K_RETRIEVAL: int = int(os.getenv("TOP_K_RETRIEVAL", "6"))
CHAT_HISTORY_LIMIT: int = int(os.getenv("CHAT_HISTORY_LIMIT", "10"))
RAG_MIN_SCORE: float = float(os.getenv("RAG_MIN_SCORE", "0.35"))
CHAT_TEMPERATURE: float = float(os.getenv("CHAT_TEMPERATURE", "0.15"))

# Rozszerzenia plików, które analizujemy
CODE_EXTENSIONS: List[str] = [
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".go", ".rs", ".rb",
    ".php", ".swift", ".m", ".mm", ".lua", ".pl", ".pm",
    ".sh", ".bash", ".zsh", ".ps1",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".astro",
    ".sql", ".graphql", ".proto",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".json", ".xml",
    ".md", ".rst", ".txt",
    ".dockerfile", ".tf",
]

# Pliki/katalogi do pominięcia podczas indeksowania
IGNORE_DIRS: List[str] = [
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", "env", ".env",
    "dist", "build", "target", ".idea", ".vscode", ".gradle",
    "vendor", "Pods", ".next", ".nuxt", ".cache", "coverage",
    ".tox", ".eggs", "*.egg-info",
]

IGNORE_FILES: List[str] = [
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock",
    "*.min.js", "*.min.css", "*.map",
]


# ---------------------------------------------------------------------------
# Konfiguracja serwera FastAPI
# ---------------------------------------------------------------------------
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "9743"))
API_RELOAD: bool = os.getenv("API_RELOAD", "false").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Konfiguracja klonowania repozytoriów
# ---------------------------------------------------------------------------
CLONE_TIMEOUT: int = int(os.getenv("CLONE_TIMEOUT", "300"))  # sekundy
CLONE_DEPTH: int = int(os.getenv("CLONE_DEPTH", "1"))         # shallow clone
MAX_REPO_SIZE_MB: int = int(os.getenv("MAX_REPO_SIZE_MB", "500"))


# ---------------------------------------------------------------------------
# Limity bezpieczeństwa
# ---------------------------------------------------------------------------
MAX_FILES_TO_ANALYZE: int = int(os.getenv("MAX_FILES_TO_ANALYZE", "2000"))
AUTO_EXPORT_HTML: bool = os.getenv("AUTO_EXPORT_HTML", "true").lower() in ("1", "true", "yes")
AUTO_INDEX_GUIDES: bool = os.getenv("AUTO_INDEX_GUIDES", "true").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# STT (Faza 2) — subprocess do audio-core, nie instaluj torch w repo-story
# ---------------------------------------------------------------------------
AUDIO_CORE_PYTHON: Path = Path(
    os.getenv("AUDIO_CORE_PYTHON", "/mnt/ollama/ai-envs/audio-core/.venv/bin/python")
)
TRANSCRIBE_SCRIPT: Path = PROJECT_ROOT / "scripts" / "transcribe_file.py"
WHISPER_MODELS_DIR: Path = Path(
    os.getenv("WHISPER_MODELS_DIR", "/mnt/ollama/whisper_models")
)
STT_MODEL: str = os.getenv("STT_MODEL", "medium")
STT_FALLBACK_MODEL: str = os.getenv("STT_FALLBACK_MODEL", "base")
STT_MAX_AUDIO_MB: int = int(os.getenv("STT_MAX_AUDIO_MB", "25"))
STT_TIMEOUT_S: int = int(os.getenv("STT_TIMEOUT_S", "120"))
STT_MIN_DURATION_S: float = float(os.getenv("STT_MIN_DURATION_S", "0.35"))
STT_MIN_RMS: float = float(os.getenv("STT_MIN_RMS", "0.008"))

# TTS (Faza 3) — Piper CLI + modele na /mnt/ollama
PIPER_BIN: Path = Path(os.getenv("PIPER_BIN", "/home/zarou/.local/bin/piper"))
PIPER_MODEL: Path = Path(
    os.getenv("PIPER_MODEL", "/mnt/ollama/modele/piper/pl_PL-gosia-medium.onnx")
)
TTS_MAX_CHARS: int = int(os.getenv("TTS_MAX_CHARS", "1500"))
TTS_TIMEOUT_S: int = int(os.getenv("TTS_TIMEOUT_S", "60"))
TTS_VENV_PYTHON: Path = Path(
    os.getenv("TTS_VENV_PYTHON", "/mnt/ollama/ai-envs/tts/.venv/bin/python")
)

# Supertonic TTS (Phase A1) — separate venv on /mnt/ollama
TTS_BACKEND: str = os.getenv("TTS_BACKEND", "piper")  # piper | supertonic
SUPERTONIC_BIN: Path = Path(
    os.getenv(
        "SUPERTONIC_BIN",
        "/mnt/ollama/ai-envs/tts-supertonic/.venv/bin/supertonic",
    )
)
SUPERTONIC_MODEL: str = os.getenv("SUPERTONIC_MODEL", "supertonic-3")
SUPERTONIC_LANG: str = os.getenv("SUPERTONIC_LANG", "pl")
SUPERTONIC_VOICE: str = os.getenv("SUPERTONIC_VOICE", "M1")
SUPERTONIC_URL: str = os.getenv("SUPERTONIC_URL", "http://127.0.0.1:7788")

# Safe command execution (Phase B1)
ACTION_TIMEOUT_S: int = int(os.getenv("ACTION_TIMEOUT_S", "60"))
ACTIONS_LOG: Path = LOGS_DIR / "actions.log"

# Knowledge onboarding threshold (Phase A4)
KB_EMPTY_CHUNK_THRESHOLD: int = int(os.getenv("KB_EMPTY_CHUNK_THRESHOLD", "5"))

# Conversation: balanced | voice | detailed
CHAT_CONVERSATION_MODE: str = os.getenv("CHAT_CONVERSATION_MODE", "balanced")

# BPMN Assistant sidecar (Phase C)
BPMN_ASSISTANT_ENABLED: bool = os.getenv(
    "BPMN_ASSISTANT_ENABLED", "true"
).lower() in ("1", "true", "yes")
BPMN_ASSISTANT_URL: str = os.getenv("BPMN_ASSISTANT_URL", "http://127.0.0.1:9748")
BPMN_ASSISTANT_FRONTEND_URL: str = os.getenv(
    "BPMN_ASSISTANT_FRONTEND_URL", "http://127.0.0.1:9749"
)
BPMN_ASSISTANT_MODEL: str = os.getenv("BPMN_ASSISTANT_MODEL", "gpt-4.1")
BPMN_ASSISTANT_TIMEOUT_S: float = float(os.getenv("BPMN_ASSISTANT_TIMEOUT_S", "120"))
BPMN_ASSISTANT_ENV_FILE: str = os.getenv(
    "BPMN_ASSISTANT_ENV_FILE",
    "/mnt/ollama/projekty/bpmn-assistant/src/bpmn_assistant/.env",
)
BPMN_ASSISTANT_API_KEYS_JSON: str = os.getenv("BPMN_ASSISTANT_API_KEYS_JSON", "")

# Phase C5: local BPMN via Ollama (default — no cloud keys required)
BPMN_USE_OLLAMA: bool = os.getenv("BPMN_USE_OLLAMA", "true").lower() in (
    "1",
    "true",
    "yes",
)
BPMN_OLLAMA_MODEL: str = os.getenv(
    "BPMN_OLLAMA_MODEL",
    os.getenv("MODEL_CODER", "qwen3-coder:latest"),
)


def summary() -> dict:
    """Zwraca podsumowanie konfiguracji - przydatne do debug i UI."""
    return {
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(DATA_DIR),
        "indexes_dir": str(INDEXES_DIR),
        "reports_dir": str(REPORTS_DIR),
        "logs_dir": str(LOGS_DIR),
        "ollama_host": OLLAMA_HOST,
        "models": {
            "coder": MODEL_CODER,
            "polish": MODEL_POLISH,
            "embed": MODEL_EMBED,
            "vision": MODEL_VISION,
        },
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "top_k_retrieval": TOP_K_RETRIEVAL,
        "chat_history_limit": CHAT_HISTORY_LIMIT,
        "api": {"host": API_HOST, "port": API_PORT},
        "knowledge_db": str(KNOWLEDGE_DB),
        "auto_export_html": AUTO_EXPORT_HTML,
        "auto_index_guides": AUTO_INDEX_GUIDES,
        "stt": {
            "audio_core_python": str(AUDIO_CORE_PYTHON),
            "model": STT_MODEL,
            "whisper_models_dir": str(WHISPER_MODELS_DIR),
        },
        "tts": {
            "backend": TTS_BACKEND,
            "piper_bin": str(PIPER_BIN),
            "supertonic_bin": str(SUPERTONIC_BIN),
            "supertonic_lang": SUPERTONIC_LANG,
        },
        "kb_empty_chunk_threshold": KB_EMPTY_CHUNK_THRESHOLD,
        "bpmn_assistant": {
            "enabled": BPMN_ASSISTANT_ENABLED,
            "url": BPMN_ASSISTANT_URL,
            "frontend_url": BPMN_ASSISTANT_FRONTEND_URL,
            "use_ollama": BPMN_USE_OLLAMA,
            "ollama_model": BPMN_OLLAMA_MODEL,
        },
    }
