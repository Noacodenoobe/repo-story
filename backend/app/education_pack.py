"""
Structured education pack for interactive zero-tech guides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class UseCaseCard:
    """When and why to use the project."""

    emoji: str
    title: str
    scenario: str
    benefit: str

    def to_dict(self) -> dict:
        return {
            "emoji": self.emoji,
            "title": self.title,
            "scenario": self.scenario,
            "benefit": self.benefit,
        }


@dataclass
class FlowStep:
    """One step in the usage flow diagram."""

    id: str
    title: str
    description: str
    tip: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tip": self.tip,
        }


@dataclass
class HowToStep:
    """Installation or setup instruction step."""

    step: int
    title: str
    body: str
    commands: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "title": self.title,
            "body": self.body,
            "commands": self.commands,
        }


@dataclass
class ModifyItem:
    """What can be changed and how."""

    title: str
    body: str
    difficulty: str = "easy"

    def to_dict(self) -> dict:
        return {"title": self.title, "body": self.body, "difficulty": self.difficulty}


@dataclass
class GraphNode:
    """Node in the interactive dependency map."""

    id: str
    label: str
    role: str
    description: str
    group: str = "default"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "role": self.role,
            "description": self.description,
            "group": self.group,
        }


@dataclass
class GraphEdge:
    """Connection between graph nodes."""

    from_id: str
    to_id: str
    label: str = ""

    def to_dict(self) -> dict:
        return {"from": self.from_id, "to": self.to_id, "label": self.label}


@dataclass
class EducationPack:
    """Full interactive educational guide for one repository."""

    title: str
    essence: str
    summary_3: List[str]
    overview: Dict[str, str] = field(default_factory=dict)
    use_cases: List[UseCaseCard] = field(default_factory=list)
    flow_steps: List[FlowStep] = field(default_factory=list)
    flow_mermaid: str = ""
    install_flow_mermaid: str = ""
    howto: List[HowToStep] = field(default_factory=list)
    modify_guide: Dict[str, Any] = field(default_factory=dict)
    charts: Dict[str, Any] = field(default_factory=dict)
    dependency_graph: Dict[str, Any] = field(default_factory=dict)
    story_slides: List[Dict[str, Any]] = field(default_factory=list)
    quiz: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "essence": self.essence,
            "summary_3": self.summary_3,
            "overview": self.overview,
            "use_cases": [u.to_dict() for u in self.use_cases],
            "flow_steps": [f.to_dict() for f in self.flow_steps],
            "flow_mermaid": self.flow_mermaid,
            "install_flow_mermaid": self.install_flow_mermaid,
            "howto": [h.to_dict() for h in self.howto],
            "modify_guide": self.modify_guide,
            "charts": self.charts,
            "dependency_graph": self.dependency_graph,
            "story_slides": self.story_slides,
            "quiz": self.quiz,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EducationPack":
        """Build pack from stored JSON or LLM output."""
        use_cases = [
            UseCaseCard(
                emoji=str(u.get("emoji", "📌")),
                title=str(u.get("title", "")),
                scenario=str(u.get("scenario", "")),
                benefit=str(u.get("benefit", "")),
            )
            for u in data.get("use_cases") or []
        ]
        flow_steps = [
            FlowStep(
                id=str(f.get("id", f"step{i}")),
                title=str(f.get("title", "")),
                description=str(f.get("description", "")),
                tip=str(f.get("tip", "")),
            )
            for i, f in enumerate(data.get("flow_steps") or [])
        ]
        howto = [
            HowToStep(
                step=int(h.get("step", i + 1)),
                title=str(h.get("title", "")),
                body=str(h.get("body", "")),
                commands=list(h.get("commands") or []),
            )
            for i, h in enumerate(data.get("howto") or [])
        ]
        summary = list(data.get("summary_3") or [])[:3]
        while len(summary) < 3:
            summary.append("")
        return cls(
            title=str(data.get("title", "Przewodnik")),
            essence=str(data.get("essence", "")),
            summary_3=summary,
            overview=dict(data.get("overview") or {}),
            use_cases=use_cases,
            flow_steps=flow_steps,
            flow_mermaid=str(data.get("flow_mermaid", "")),
            install_flow_mermaid=str(data.get("install_flow_mermaid", "")),
            howto=howto,
            modify_guide=dict(data.get("modify_guide") or {}),
            charts=dict(data.get("charts") or {}),
            dependency_graph=dict(data.get("dependency_graph") or {}),
            story_slides=list(data.get("story_slides") or []),
            quiz=list(data.get("quiz") or []),
        )
