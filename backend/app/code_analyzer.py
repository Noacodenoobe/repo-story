"""
Statyczna i LLM-owa analiza kodu.

Zawiera dwa rodzaje analizy:
1. **Static analysis** — szybkie liczenie linii, plików, wykrywanie języka
   i bibliotek na podstawie nazw plików (bez uruchamiania LLM).
2. **LLM analysis** — wykorzystuje model koderski (``qwen3-coder``) i RAG
   do generowania opisów architektury, oceny jakości i wykrywania wzorców.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .embeddings import CodeEmbedder, VectorIndex
from .llm_client import OllamaClient, get_client
from .repo_fetcher import RepoInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapowanie rozszerzeń na języki - przyjazne nazwy dla raportu
# ---------------------------------------------------------------------------
EXT_TO_LANG: Dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript (JSX)",
    ".ts": "TypeScript", ".tsx": "TypeScript (TSX)",
    ".java": "Java", ".kt": "Kotlin", ".scala": "Scala",
    ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".hpp": "C++ header", ".cc": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C++",
    ".lua": "Lua", ".pl": "Perl", ".pm": "Perl",
    ".sh": "Bash", ".bash": "Bash", ".zsh": "Zsh", ".ps1": "PowerShell",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "SASS", ".less": "LESS",
    ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro",
    ".sql": "SQL", ".graphql": "GraphQL", ".proto": "Protobuf",
    ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML",
    ".md": "Markdown", ".rst": "reStructuredText", ".txt": "Text",
}


# Pliki, które jednoznacznie wskazują na konkretne narzędzie/framework
FRAMEWORK_FILES: Dict[str, str] = {
    "package.json": "Node.js / npm",
    "requirements.txt": "Python (pip)",
    "pyproject.toml": "Python (Poetry/PEP 621)",
    "Pipfile": "Python (Pipenv)",
    "setup.py": "Python (setuptools)",
    "go.mod": "Go modules",
    "cargo.toml": "Rust (Cargo)",
    "build.gradle": "Java/Kotlin (Gradle)",
    "pom.xml": "Java (Maven)",
    "composer.json": "PHP (Composer)",
    "Gemfile": "Ruby (Bundler)",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    ".gitlab-ci.yml": "GitLab CI",
    "next.config.js": "Next.js",
    "nuxt.config.js": "Nuxt.js",
    "vite.config.js": "Vite",
    "vite.config.ts": "Vite",
    "webpack.config.js": "Webpack",
    "tailwind.config.js": "Tailwind CSS",
}


# Bardziej miękkie wskazówki - zawartość pliku
_MANIFEST_FILENAMES = frozenset({
    "go.mod", "go.sum", "package.json", "package-lock.json",
    "requirements.txt", "pyproject.toml", "Pipfile", "Cargo.toml",
    "composer.json", "Gemfile", "pom.xml", "build.gradle",
})

DEPENDENCY_PATTERNS: Dict[str, str] = {
    r"\bdjango\b": "Django",
    r"\bflask\b": "Flask",
    r"\bfastapi\b": "FastAPI",
    r"\bpyramid\b": "Pyramid",
    r"\bexpress\b": "Express.js",
    r"\bkoa\b": "Koa.js",
    r"\bnestjs\b": "NestJS",
    r"\breact\b": "React",
    r"\bvue\b": "Vue.js",
    r"\bangular\b": "Angular",
    r"\bspring-boot\b": "Spring Boot",
    r"\btensorflow\b": "TensorFlow",
    r"\btorch\b": "PyTorch",
    r"\bscikit-learn\b": "scikit-learn",
    r"\bnumpy\b": "NumPy",
    r"\bpandas\b": "pandas",
    r"\bsqlalchemy\b": "SQLAlchemy",
    r"\bredis\b": "Redis",
    r"\bpostgresql\b": "PostgreSQL",
}


@dataclass
class StaticAnalysis:
    """Wynik statycznej analizy (bez LLM)."""
    languages: Dict[str, int] = field(default_factory=dict)      # nazwa -> liczba plików
    file_counts: Dict[str, int] = field(default_factory=dict)    # rozszerzenie -> liczba
    total_files: int = 0
    total_lines: int = 0
    frameworks: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    structure: Dict[str, List[str]] = field(default_factory=dict)   # katalog -> próbka plików
    largest_files: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "languages": self.languages,
            "file_counts": self.file_counts,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "frameworks": self.frameworks,
            "dependencies": self.dependencies,
            "structure": self.structure,
            "largest_files": self.largest_files,
        }


@dataclass
class LlmAnalysis:
    """Wynik analizy LLM."""
    architecture: str = ""
    main_modules: str = ""
    quality_assessment: str = ""
    design_patterns: str = ""
    potential_issues: str = ""

    def to_dict(self) -> dict:
        return {
            "architecture": self.architecture,
            "main_modules": self.main_modules,
            "quality_assessment": self.quality_assessment,
            "design_patterns": self.design_patterns,
            "potential_issues": self.potential_issues,
        }


# ---------------------------------------------------------------------------
# Statyczna analiza
# ---------------------------------------------------------------------------
class StaticAnalyzer:
    """Szybka analiza bez LLM - statystyki i wykrywanie frameworków."""

    def analyze(self, repo_path: Path) -> StaticAnalysis:
        repo_path = Path(repo_path)
        result = StaticAnalysis()

        lang_counter: Counter[str] = Counter()
        ext_counter: Counter[str] = Counter()
        framework_set: set[str] = set()
        dep_set: set[str] = set()
        dir_samples: Dict[str, List[str]] = defaultdict(list)
        sizes: List[tuple[int, str]] = []
        total_lines = 0

        for p in repo_path.rglob("*"):
            if any(part in config.IGNORE_DIRS for part in p.parts):
                continue
            if p.is_dir() or not p.is_file():
                continue

            ext = p.suffix.lower()
            name = p.name

            # Framework po nazwie pliku
            for key, label in FRAMEWORK_FILES.items():
                if name == key:
                    framework_set.add(label)

            try:
                size = p.stat().st_size
            except OSError:
                continue
            sizes.append((size, str(p.relative_to(repo_path))))

            if ext not in config.CODE_EXTENSIONS:
                continue

            lang_counter[EXT_TO_LANG.get(ext, ext)] += 1
            ext_counter[ext] += 1
            result.total_files += 1

            # Próbujemy policzyć linie
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue

            total_lines += text.count("\n") + 1

            # Zależności tylko z manifestów (nie vendor / cały kod)
            if name in _MANIFEST_FILENAMES or name.endswith(".mod"):
                lower = text.lower()
                for pattern, label in DEPENDENCY_PATTERNS.items():
                    if re.search(pattern, lower):
                        dep_set.add(label)

            # Próbka pierwszego poziomu katalogu (do "structure")
            rel = p.relative_to(repo_path)
            top_dir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            if len(dir_samples[top_dir]) < 5:
                dir_samples[top_dir].append(str(rel))

        result.languages = dict(lang_counter.most_common())
        result.file_counts = dict(ext_counter.most_common())
        result.total_lines = total_lines
        result.frameworks = sorted(framework_set)
        result.dependencies = sorted(dep_set)
        result.structure = dict(dir_samples)
        sizes.sort(reverse=True)
        result.largest_files = [
            {"path": path, "size_kb": int(s / 1024)} for s, path in sizes[:10]
        ]
        return result


# ---------------------------------------------------------------------------
# Analiza LLM - z użyciem RAG
# ---------------------------------------------------------------------------
_SYSTEM_CODER = (
    "Jesteś doświadczonym programistą i recenzentem kodu. "
    "Analizujesz repozytoria pod kątem architektury, jakości i wzorców projektowych. "
    "Odpowiadaj zwięźle, technicznie i konkretnie. "
    "Jeżeli czegoś nie wiesz na pewno, napisz to wprost."
)


class LlmAnalyzer:
    """Analiza kodu z użyciem RAG + model koderski."""

    def __init__(self, embedder: Optional[CodeEmbedder] = None,
                 client: Optional[OllamaClient] = None) -> None:
        self.client = client or get_client()
        self.embedder = embedder or CodeEmbedder(self.client)

    # ---------------------------------------- helper
    def _retrieve_context(self, index: VectorIndex, query: str, k: int = config.TOP_K_RETRIEVAL) -> str:
        hits = self.embedder.search(index, query, top_k=k)
        if not hits:
            return "(brak dopasowań w indeksie)"
        parts = []
        for chunk, score in hits:
            parts.append(
                f"### {chunk.file_path} (fragment {chunk.chunk_index}, podobieństwo={score:.2f})\n"
                f"```\n{chunk.text}\n```"
            )
        return "\n\n".join(parts)

    def _ask(self, prompt: str) -> str:
        result = self.client.generate(
            prompt=prompt,
            model=config.MODEL_CODER,
            system=_SYSTEM_CODER,
        )
        return result.response

    # ---------------------------------------- składowe analizy
    def analyze_architecture(self, index: VectorIndex, repo_info: RepoInfo) -> str:
        ctx = self._retrieve_context(
            index,
            "główna struktura projektu, punkty wejścia, organizacja modułów"
        )
        prompt = (
            f"Repozytorium: {repo_info.url or repo_info.slug}\n"
            f"Główne pliki: {', '.join(repo_info.main_files[:10]) or 'brak danych'}\n\n"
            f"Na podstawie poniższych fragmentów kodu opisz architekturę projektu w 5-8 punktach.\n"
            f"Skup się na: warstwach, modułach, sposobie komunikacji, frameworkach.\n\n"
            f"FRAGMENTY:\n{ctx}\n"
        )
        return self._ask(prompt)

    def analyze_main_modules(self, index: VectorIndex) -> str:
        ctx = self._retrieve_context(index, "kluczowe klasy, funkcje, punkty wejścia, API")
        prompt = (
            "Wymień i krótko opisz najważniejsze moduły/klasy/funkcje tego projektu.\n"
            "Dla każdego podaj: nazwę, ścieżkę, w 1-2 zdaniach co robi.\n"
            "Format listy markdown.\n\n"
            f"FRAGMENTY:\n{ctx}\n"
        )
        return self._ask(prompt)

    def analyze_quality(self, index: VectorIndex, static: StaticAnalysis) -> str:
        ctx = self._retrieve_context(
            index,
            "obsługa błędów, testy, dokumentacja, czytelność, modularność"
        )
        prompt = (
            f"Statystyki: {static.total_files} plików, {static.total_lines} linii.\n"
            f"Wykryte frameworki: {', '.join(static.frameworks) or 'brak'}.\n\n"
            "Oceń jakość kodu w 4 wymiarach (każdy 1-5 + krótkie uzasadnienie):\n"
            "1. Czytelność\n2. Obsługa błędów\n3. Pokrycie testami (jeśli widać)\n4. Dokumentacja\n\n"
            f"FRAGMENTY:\n{ctx}\n"
        )
        return self._ask(prompt)

    def analyze_patterns(self, index: VectorIndex) -> str:
        ctx = self._retrieve_context(index, "wzorce projektowe, abstrakcje, klasy bazowe, dependency injection")
        prompt = (
            "Czy w kodzie widać znane wzorce projektowe (Factory, Singleton, Observer, Strategy, MVC, Repository, itp.)?\n"
            "Wymień najważniejsze obserwacje. Jeśli wzorzec jest tylko sugestią, zaznacz to.\n\n"
            f"FRAGMENTY:\n{ctx}\n"
        )
        return self._ask(prompt)

    def analyze_issues(self, index: VectorIndex) -> str:
        ctx = self._retrieve_context(
            index,
            "potencjalne błędy, problemy bezpieczeństwa, antywzorce, hardcoded values"
        )
        prompt = (
            "Wymień potencjalne problemy w kodzie (max 7 pozycji).\n"
            "Dla każdego podaj: krótki tytuł, plik (jeśli wiadomo), ryzyko (niskie/średnie/wysokie) i sugestię poprawki.\n\n"
            f"FRAGMENTY:\n{ctx}\n"
        )
        return self._ask(prompt)

    # ---------------------------------------- całość
    def run_full(self, index: VectorIndex, repo_info: RepoInfo, static: StaticAnalysis) -> LlmAnalysis:
        """Uruchom wszystkie cztery zapytania do modelu po kolei."""
        out = LlmAnalysis()
        out.architecture = self.analyze_architecture(index, repo_info)
        out.main_modules = self.analyze_main_modules(index)
        out.quality_assessment = self.analyze_quality(index, static)
        out.design_patterns = self.analyze_patterns(index)
        out.potential_issues = self.analyze_issues(index)
        return out
