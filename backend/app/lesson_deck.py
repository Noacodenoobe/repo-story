"""
Structured lesson deck for zero-tech educational presentations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GlossaryEntry:
    """Optional term explained on demand."""

    term: str
    definition: str

    def to_dict(self) -> dict:
        return {"term": self.term, "definition": self.definition}


@dataclass
class Slide:
    """One screen in the interactive presentation."""

    id: str
    emoji: str
    title: str
    body: str
    analogy: str = ""
    for_you: str = ""
    more_detail: str = ""
    glossary: List[GlossaryEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "emoji": self.emoji,
            "title": self.title,
            "body": self.body,
            "analogy": self.analogy,
            "for_you": self.for_you,
            "more_detail": self.more_detail,
            "glossary": [g.to_dict() for g in self.glossary],
        }


@dataclass
class QuizQuestion:
    """Short comprehension check after the deck."""

    question: str
    options: List[str]
    correct_index: int

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "options": self.options,
            "correct_index": self.correct_index,
        }


@dataclass
class LessonDeck:
    """Full educational presentation payload."""

    title: str
    essence: str
    summary_3: List[str]
    slides: List[Slide]
    quiz: List[QuizQuestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "essence": self.essence,
            "summary_3": self.summary_3,
            "slides": [s.to_dict() for s in self.slides],
            "quiz": [q.to_dict() for q in self.quiz],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LessonDeck":
        """Build a deck from LLM JSON or stored record."""
        slides = []
        for raw in data.get("slides") or []:
            glossary = [
                GlossaryEntry(term=g.get("term", ""), definition=g.get("definition", ""))
                for g in (raw.get("glossary") or [])
                if g.get("term")
            ]
            slides.append(
                Slide(
                    id=str(raw.get("id", "slide")),
                    emoji=str(raw.get("emoji", "📖")),
                    title=str(raw.get("title", "")),
                    body=str(raw.get("body", "")),
                    analogy=str(raw.get("analogy", "")),
                    for_you=str(raw.get("for_you", "")),
                    more_detail=str(raw.get("more_detail", "")),
                    glossary=glossary,
                )
            )
        quiz = []
        for raw in data.get("quiz") or []:
            opts = list(raw.get("options") or [])
            if len(opts) >= 2:
                quiz.append(
                    QuizQuestion(
                        question=str(raw.get("question", "")),
                        options=opts[:4],
                        correct_index=int(raw.get("correct_index", 0)),
                    )
                )
        summary = list(data.get("summary_3") or [])[:3]
        while len(summary) < 3:
            summary.append("")
        return cls(
            title=str(data.get("title", "Prezentacja projektu")),
            essence=str(data.get("essence", "")),
            summary_3=summary,
            slides=slides,
            quiz=quiz,
        )
