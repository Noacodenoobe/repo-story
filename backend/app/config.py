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

for _d in (DATA_DIR, REPOS_DIR, INDEXES_DIR, REPORTS_DIR, LOGS_DIR):
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
        "api": {"host": API_HOST, "port": API_PORT},
    }
