"""
Zero-tech educational story generator.

Two-stage pipeline: extract plain facts, then build a LessonDeck JSON
for slide-based UI. Uses local Polish model (Bielik) via Ollama.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .code_analyzer import StaticAnalysis
from .lesson_deck import GlossaryEntry, LessonDeck, QuizQuestion, Slide
from .llm_client import OllamaClient, get_client
from .repo_fetcher import RepoInfo

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "zero_tech"
_MAX_README_CHARS = 6000
_MAX_BODY_WORDS = 60

_FORBIDDEN_PATTERNS = [
    r"\bAPI\b",
    r"\bHTTP\b",
    r"\bREST\b",
    r"\bJSON\b",
    r"\bYAML\b",
    r"\bTypeScript\b",
    r"\bJavaScript\b",
    r"\bPython\b",
    r"\bframework\b",
    r"\bFramework\b",
    r"\bmoduł\b",
    r"\bModuł\b",
    r"\brepozytorium\b",
    r"\bRepozytorium\b",
    r"\bcommit\b",
    r"\bRAG\b",
    r"\bLLM\b",
    r"\bplugin\b",
    r"\bPlugin\b",
    r"`[^`]+`",
    r"\b\w+\.(ts|js|py|json|md|yml|yaml|css)\b",
    r"\b\w+Manager\b",
    r"\b\w+Modal\b",
]


def _load_prompt(name: str) -> str:
    """Load a prompt template from ``prompts/zero_tech/``."""
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


def _read_readme(repo_path: Path) -> str:
    """Return README text if present, truncated."""
    for candidate in ("README.md", "README.MD", "readme.md", "Readme.md"):
        path = repo_path / candidate
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            return text[:_MAX_README_CHARS]
    return ""


def _parse_json_blob(text: str) -> Dict[str, Any]:
    """Extract JSON object from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Brak obiektu JSON w odpowiedzi modelu.")
    return json.loads(cleaned[start : end + 1])


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _trim_words(text: str, limit: int) -> str:
    words = re.findall(r"\S+", text or "")
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]) + "…"


def _sanitize_plain(text: str) -> str:
    """Remove jargon patterns from user-facing copy."""
    result = text or ""
    for pattern in _FORBIDDEN_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s{2,}", " ", result).strip()
    return result


class StoryGenerator:
    """Builds a LessonDeck for non-technical audiences."""

    def __init__(self, client: Optional[OllamaClient] = None) -> None:
        self.client = client or get_client()
        self._system = _load_prompt("system.txt")

    def _build_context(self, repo: RepoInfo, static: StaticAnalysis) -> str:
        """Assemble human-readable context for fact extraction."""
        readme = _read_readme(repo.path)
        langs = ", ".join(list(static.languages.keys())[:6]) or "nieznane"
        frameworks = ", ".join(static.frameworks) or "brak"
        parts = [
            f"Adres projektu: {repo.url}",
            f"Liczba plików: {static.total_files}",
            f"Szacowana wielkość: około {static.total_lines} linii tekstu",
            f"Główne rodzaje plików: {langs}",
            f"Wykryte technologie (nie wymieniaj ich wprost użytkownikowi): {frameworks}",
            f"Opis z README:\n{readme if readme else '(brak README)'}",
        ]
        return "\n".join(parts)

    def _extract_facts(self, repo: RepoInfo, static: StaticAnalysis) -> Dict[str, Any]:
        """Stage 1: structured facts in JSON."""
        template = _load_prompt("facts.txt")
        prompt = template.format(context=self._build_context(repo, static))
        result = self.client.generate(
            prompt=prompt,
            model=config.MODEL_POLISH,
            system=self._system,
        )
        return _parse_json_blob(result.response)

    def _build_deck_from_facts(self, facts: Dict[str, Any]) -> LessonDeck:
        """Stage 2: lesson deck JSON from facts."""
        template = _load_prompt("story.txt")
        prompt = template.format(facts_json=json.dumps(facts, ensure_ascii=False, indent=2))
        result = self.client.generate(
            prompt=prompt,
            model=config.MODEL_POLISH,
            system=self._system,
        )
        return LessonDeck.from_dict(_parse_json_blob(result.response))

    def _postprocess_deck(self, deck: LessonDeck) -> LessonDeck:
        """Enforce length limits and jargon filtering."""
        deck.title = _sanitize_plain(deck.title) or "Opowieść o projekcie"
        deck.essence = _trim_words(_sanitize_plain(deck.essence), 35)
        deck.summary_3 = [
            _trim_words(_sanitize_plain(s), 40) for s in deck.summary_3[:3]
        ]
        while len(deck.summary_3) < 3:
            deck.summary_3.append("")

        cleaned_slides: List[Slide] = []
        for slide in deck.slides:
            body = _trim_words(_sanitize_plain(slide.body), _MAX_BODY_WORDS)
            if not body:
                continue
            glossary = [
                GlossaryEntry(
                    term=_sanitize_plain(g.term),
                    definition=_trim_words(_sanitize_plain(g.definition), 25),
                )
                for g in slide.glossary
                if g.term and g.definition
            ]
            cleaned_slides.append(
                Slide(
                    id=slide.id,
                    emoji=slide.emoji or "📖",
                    title=_sanitize_plain(slide.title) or "Scena",
                    body=body,
                    analogy=_trim_words(_sanitize_plain(slide.analogy), 35),
                    for_you=_trim_words(_sanitize_plain(slide.for_you), 30),
                    more_detail=_sanitize_plain(slide.more_detail),
                    glossary=glossary,
                )
            )
        deck.slides = cleaned_slides

        cleaned_quiz: List[QuizQuestion] = []
        for q in deck.quiz:
            opts = [_sanitize_plain(o) for o in q.options if _sanitize_plain(o)]
            if len(opts) >= 2 and q.question:
                idx = max(0, min(q.correct_index, len(opts) - 1))
                cleaned_quiz.append(
                    QuizQuestion(
                        question=_sanitize_plain(q.question),
                        options=opts[:4],
                        correct_index=idx,
                    )
                )
        deck.quiz = cleaned_quiz[:3]
        return deck

    def _fallback_deck(self, repo: RepoInfo, static: StaticAnalysis, facts: Optional[Dict[str, Any]]) -> LessonDeck:
        """Minimal deck when LLM is unavailable."""
        name = (facts or {}).get("project_name") or repo.slug.replace("_", " ")
        one_line = (facts or {}).get("one_line") or f"To projekt dostępny pod adresem {repo.url}."
        return LessonDeck(
            title=f"Co to jest: {name}?",
            essence=one_line,
            summary_3=[
                one_line,
                f"Projekt składa się z około {static.total_files} plików.",
                "Szczegóły wygenerujemy ponownie, gdy model językowy będzie dostępny.",
            ],
            slides=[
                Slide(
                    id="what",
                    emoji="🎯",
                    title="Co to jest?",
                    body=one_line,
                    for_you="Możesz traktować to jako gotowe narzędzie do pobrania z internetu.",
                ),
                Slide(
                    id="worth",
                    emoji="✨",
                    title="Czy warto?",
                    body="Jeśli opis brzmi jak coś, czego szukasz — warto zajrzeć do strony projektu.",
                    for_you="Decyzja zależy od tego, czego potrzebujesz na co dzień.",
                ),
            ],
        )

    def generate(self, repo: RepoInfo, static: StaticAnalysis) -> LessonDeck:
        """
        Run the full story pipeline and return a sanitized lesson deck.

        Falls back to a minimal deck if the model fails.
        """
        facts: Optional[Dict[str, Any]] = None
        try:
            facts = self._extract_facts(repo, static)
            deck = self._build_deck_from_facts(facts)
            if not deck.slides:
                raise ValueError("Model zwrócił pustą prezentację.")
            return self._postprocess_deck(deck)
        except Exception as exc:  # noqa: BLE001
            logger.warning("StoryGenerator fallback: %s", exc)
            return self._postprocess_deck(self._fallback_deck(repo, static, facts))
