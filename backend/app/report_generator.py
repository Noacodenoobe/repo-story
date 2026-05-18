"""
Generator polskich raportów edukacyjnych.

Bierze wynik ``LlmAnalysis`` (po angielsku/technicznie z modelu koderskiego)
i przepuszcza go przez Bielika, żeby uzyskać przystępny język polski.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from . import config
from .code_analyzer import LlmAnalysis, StaticAnalysis
from .knowledge_base import AnalysisRecord
from .llm_client import OllamaClient, get_client
from .repo_fetcher import RepoInfo

logger = logging.getLogger(__name__)


_SYSTEM_POLISH = (
    "Jesteś polskim trenerem programowania. "
    "Tłumaczysz złożone tematy techniczne na przystępny język polski "
    "dla osób uczących się programowania. "
    "Piszesz krótko, jasno i bez nadmiernego żargonu. "
    "Wszystkie odpowiedzi piszesz po polsku."
)


class PolishReportGenerator:
    """Generuje finalny raport w języku polskim z użyciem modelu Bielik."""

    def __init__(self, client: Optional[OllamaClient] = None) -> None:
        self.client = client or get_client()

    # --------------------------------------------------------- helpers
    def _explain(self, technical_text: str, topic: str) -> str:
        """
        Bierze techniczny tekst i prosi Bielika o przepisanie go po polsku
        dla początkujących.
        """
        if not technical_text.strip():
            return f"_Brak danych do tematu: {topic}._"

        prompt = (
            f"Poniżej znajduje się techniczny opis tematu: **{topic}**.\n\n"
            "Przepisz go po polsku, w przystępny sposób, dla początkującego programisty.\n"
            "Zachowaj wszystkie konkretne nazwy bibliotek, plików i wzorców.\n"
            "Wyjaśnij trudne terminy w nawiasach.\n"
            "Używaj krótkich zdań i list punktowanych, jeśli to pomaga.\n\n"
            "TEKST DO PRZETŁUMACZENIA:\n"
            f"{technical_text}\n"
        )
        result = self.client.generate(
            prompt=prompt,
            model=config.MODEL_POLISH,
            system=_SYSTEM_POLISH,
        )
        return result.response.strip()

    def _summary_intro(self, repo: RepoInfo, static: StaticAnalysis) -> str:
        """Krótkie wprowadzenie po polsku."""
        langs = ", ".join(list(static.languages.keys())[:5]) or "nieznane"
        frameworks = ", ".join(static.frameworks) or "brak wykrytych"
        prompt = (
            "Napisz krótkie (3-5 zdań) wprowadzenie po polsku do raportu o repozytorium.\n"
            f"URL: {repo.url}\n"
            f"Liczba plików: {static.total_files}\n"
            f"Liczba linii kodu: {static.total_lines}\n"
            f"Główne języki: {langs}\n"
            f"Frameworki: {frameworks}\n\n"
            "Pisz przyjaźnie, jakbyś przedstawiał projekt początkującemu programiście."
        )
        result = self.client.generate(
            prompt=prompt,
            model=config.MODEL_POLISH,
            system=_SYSTEM_POLISH,
        )
        return result.response.strip()

    # --------------------------------------------------------- glowna metoda
    def generate(self, repo: RepoInfo, static: StaticAnalysis, llm: LlmAnalysis) -> str:
        """Składa pełny raport Markdown po polsku."""
        intro = self._summary_intro(repo, static)
        arch = self._explain(llm.architecture, "Architektura projektu")
        modules = self._explain(llm.main_modules, "Główne moduły")
        quality = self._explain(llm.quality_assessment, "Ocena jakości kodu")
        patterns = self._explain(llm.design_patterns, "Wzorce projektowe")
        issues = self._explain(llm.potential_issues, "Potencjalne problemy")

        languages_md = "\n".join(
            f"- **{lang}** — {count} plików"
            for lang, count in list(static.languages.items())[:10]
        ) or "_Brak rozpoznanych języków._"

        frameworks_md = "\n".join(f"- {f}" for f in static.frameworks) or "_Brak wykrytych frameworków._"
        deps_md = "\n".join(f"- {d}" for d in static.dependencies) or "_Brak wykrytych zależności._"

        report = f"""# Raport analizy repozytorium

> **URL:** {repo.url or "(lokalne repo)"}
> **Identyfikator:** `{repo.slug}`
> **Branch:** `{repo.branch or "?"}` · **HEAD:** `{repo.head_commit or "?"}`
> **Rozmiar:** {repo.size_kb} KB · **Plików:** {repo.file_count}

## Wprowadzenie

{intro}

## Podstawowe statystyki

| Metryka | Wartość |
|---|---|
| Liczba plików kodu | {static.total_files} |
| Liczba linii kodu | {static.total_lines} |
| Plik README | {"✅ obecny" if repo.has_readme else "❌ brak"} |
| Licencja | {"✅ obecna" if repo.has_license else "❌ brak"} |
| Testy | {"✅ wykryte" if repo.has_tests else "❌ nie wykryto"} |
| CI/CD | {"✅ skonfigurowane" if repo.has_ci else "❌ brak"} |
| Docker | {"✅ obecny" if repo.has_dockerfile else "❌ brak"} |

## Języki programowania

{languages_md}

## Frameworki

{frameworks_md}

## Zależności (wykryte heurystycznie)

{deps_md}

## Architektura

{arch}

## Główne moduły

{modules}

## Jakość kodu

{quality}

## Wzorce projektowe

{patterns}

## Potencjalne problemy

{issues}

---

_Raport wygenerowany automatycznie przez Repo Analyzer._
_Modele: {config.MODEL_CODER} (analiza techniczna) + {config.MODEL_POLISH} (tłumaczenie)._
"""
        return report

    # --------------------------------------------------------- pomocnik
    def save_to_file(self, content: str, slug: str,
                     directory: Path = config.REPORTS_DIR) -> Path:
        """Zapisuje gotowy raport jako .md."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{slug}_report.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Zapisano raport markdown: %s", path)
        return path


def attach_to_record(record: AnalysisRecord, repo: RepoInfo, static: StaticAnalysis,
                     llm: LlmAnalysis, diagrams: Dict[str, str],
                     polish_report: str) -> AnalysisRecord:
    """Wypełnia rekord wynikami - wygoda dla wywołującego."""
    record.repo_info = repo.to_dict()
    record.static = static.to_dict()
    record.llm = llm.to_dict()
    record.diagrams = diagrams
    record.polish_report = polish_report
    return record
