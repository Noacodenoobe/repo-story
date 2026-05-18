"""
Comprehensive education pack generator with heuristics + LLM.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .code_analyzer import StaticAnalysis
from .education_pack import EducationPack
from .graph_builder import (
    build_charts,
    build_dependency_graph,
    flow_steps_to_mermaid,
    howto_to_mermaid,
)
from .polish_validator import (
    ensure_polish,
    polish_flow_steps,
    polish_howto,
    polish_overview,
    polish_use_cases,
)
from .lesson_deck import Slide
from .llm_client import OllamaClient, get_client
from .readme_heuristics import build_readme_context
from .repo_fetcher import RepoInfo
from .story_generator import StoryGenerator, _parse_json_blob, _sanitize_plain, _trim_words

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "education"


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


class EducationGenerator:
    """Builds a full EducationPack for interactive UI."""

    def __init__(self, client: Optional[OllamaClient] = None) -> None:
        self.client = client or get_client()
        self._system = _load_prompt("system.txt")
        self._story = StoryGenerator(client=self.client)

    def _build_context(self, repo: RepoInfo, static: StaticAnalysis) -> str:
        ctx = build_readme_context(repo.path, static.languages or {})
        langs = ", ".join(f"{k} ({v} plików)" for k, v in list(static.languages.items())[:8])
        parts = [
            f"URL: {repo.url}",
            f"Nazwa robocza: {repo.slug}",
            f"Plików: {static.total_files}, linii: {static.total_lines}",
            f"Języki: {langs or 'nieznane'}",
            f"Technologie: {', '.join(static.frameworks) or 'brak'}",
            f"Biblioteki: {', '.join(static.dependencies[:10]) or 'brak'}",
            f"README:\n{ctx.get('readme_excerpt', '')[:6000]}",
        ]
        return "\n".join(parts)

    def _llm_json(self, prompt: str) -> Dict[str, Any]:
        """Single small LLM call returning JSON."""
        extra = ""
        last_exc: Optional[Exception] = None
        for _ in range(2):
            result = self.client.generate(
                prompt=prompt + extra,
                model=config.MODEL_POLISH,
                system=self._system,
            )
            try:
                return _parse_json_blob(result.response)
            except (ValueError, json.JSONDecodeError) as exc:
                last_exc = exc
                extra = "\n\nTylko poprawny JSON, bez komentarzy."
                logger.warning("LLM JSON retry: %s", exc)
        raise ValueError(str(last_exc))

    def _generate_sections(self, repo: RepoInfo, static: StaticAnalysis) -> Dict[str, Any]:
        """Multi-step generation for more reliable JSON."""
        ctx = build_readme_context(repo.path, static.languages or {})
        context = self._build_context(repo, static)
        merged: Dict[str, Any] = {
            "title": repo.slug.split("_")[-1].replace("-", " ").title(),
            "essence": "",
            "summary_3": [],
        }

        try:
            uc = self._llm_json(_load_prompt("use_cases.txt").format(context=context))
            merged["use_cases"] = uc.get("use_cases", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("use_cases LLM: %s", exc)

        try:
            fh = self._llm_json(
                _load_prompt("flow_howto.txt").format(
                    context=context,
                    commands=json.dumps(ctx.get("commands") or [], ensure_ascii=False),
                )
            )
            merged["flow_steps"] = fh.get("flow_steps", [])
            merged["howto"] = fh.get("howto", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("flow_howto LLM: %s", exc)

        try:
            mo = self._llm_json(_load_prompt("modify_overview.txt").format(context=context))
            merged["overview"] = mo.get("overview", {})
            merged["modify_guide"] = mo.get("modify_guide", {})
            merged["graph_node_descriptions"] = mo.get("graph_node_descriptions", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("modify_overview LLM: %s", exc)

        try:
            tf = self._llm_json(
                _load_prompt("technical_flow.txt").format(
                    context=context,
                    commands=json.dumps(ctx.get("commands") or [], ensure_ascii=False),
                )
            )
            if tf.get("flow_steps"):
                merged["flow_steps"] = tf["flow_steps"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("technical_flow LLM: %s", exc)

        return merged

    def _fallback_sections(
        self, repo: RepoInfo, static: StaticAnalysis, facts: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        ctx = build_readme_context(repo.path, static.languages or {})
        facts = facts or {}
        name = facts.get("project_name") or repo.slug.split("_")[-1].replace("-", " ").title()
        one = facts.get("one_line") or f"Projekt dostępny pod adresem {repo.url}"
        commands = ctx.get("commands") or []
        features = ctx.get("features") or []

        howto = list(ctx.get("howto_grouped") or [])
        if not howto:
            for i, cmd in enumerate(commands[:6], start=1):
                howto.append({
                    "step": i,
                    "title": f"Wykonaj polecenie {i}",
                    "body": "Otwórz terminal i wpisz poniższą komendę. Poczekaj na zakończenie.",
                    "commands": [cmd],
                })
        if not howto:
            howto = [
                {"step": 1, "title": "Pobierz", "body": "Wejdź na stronę GitHub projektu i pobierz paczkę.", "commands": []},
                {"step": 2, "title": "Zainstaluj", "body": "Rozpakuj i postępuj według instrukcji w README.", "commands": []},
                {"step": 3, "title": "Uruchom", "body": "Otwórz program z menu aplikacji lub terminala.", "commands": []},
            ]

        use_cases = []
        templates = [
            ("🎧", "Rozmowy online", "Wideokonferencje, Discord, Zoom", "Czystszy głos bez szumu tła"),
            ("🎙️", "Nagrywanie", "Podcast, notatki głosowe", "Lepsza jakość nagrania"),
            ("🎮", "Streaming / gry", "Gdy mikrofon przeszkadza innym", "Mniej irytujących dźwięków"),
            ("🏠", "Praca zdalna", "Domowe biuro z hałasem", "Profesjonalniejsze brzmienie"),
        ]
        while len(use_cases) < 4:
            t = templates[len(use_cases)]
            use_cases.append({"emoji": t[0], "title": t[1], "scenario": t[2], "benefit": t[3]})
        if not use_cases:
            use_cases = [
                {
                    "emoji": "🎯",
                    "title": "Główne zastosowanie",
                    "scenario": str(facts.get("who_is_it_for", "Gdy potrzebujesz tego narzędzia")),
                    "benefit": str(facts.get("problem_solved", "Rozwiązuje konkretny problem")),
                },
            ]

        parts = facts.get("main_parts") or []
        flow_steps = [
            {"id": "start", "title": "Pobierz program", "description": "Ściągnij projekt ze strony GitHub.", "tip": "Użyj stabilnej wersji."},
            {"id": "install", "title": "Zainstaluj", "description": "Wykonaj kroki instalacji z instrukcji.", "tip": "Czytaj komunikaty w terminalu."},
            {"id": "configure", "title": "Skonfiguruj", "description": "Ustaw mikrofon lub opcje według przewodnika.", "tip": ""},
            {"id": "use", "title": "Używaj na co dzień", "description": str(facts.get("how_it_works_simple", "Wybierz program w aplikacjach.")), "tip": ""},
        ]
        for i, part in enumerate(parts[:3]):
            flow_steps.insert(2 + i, {
                "id": f"part{i}",
                "title": f"Część: {str(part)[:40]}",
                "description": f"Projekt zawiera element odpowiedzialny za: {part}.",
                "tip": "",
            })

        return {
            "title": f"Przewodnik: {name}",
            "essence": one,
            "summary_3": [
                one,
                str(facts.get("problem_solved", "")),
                str(facts.get("who_is_it_for", "")),
            ],
            "overview": {
                "what": one,
                "why": str(facts.get("problem_solved", "")),
                "how_it_works": str(facts.get("how_it_works_simple", "")),
                "limitations": str(facts.get("caution", "Sprawdź wymagania systemowe w dokumentacji.")),
            },
            "use_cases": use_cases,
            "flow_steps": flow_steps,
            "howto": howto,
            "modify_guide": {
                "easy": [
                    {"title": "Ustawienia w programie", "body": "Zmieniaj suwaki i opcje w interfejsie.", "difficulty": "easy"},
                    {"title": "Wybór mikrofonu", "body": "W aplikacjach wybierz wirtualny mikrofon z filtra.", "difficulty": "easy"},
                ],
                "advanced": [
                    {"title": "Modyfikacja kodu", "body": "Wymaga znajomości programowania i kompilacji.", "difficulty": "advanced"},
                    {"title": "Własne modele AI", "body": "Zaawansowana zmiana zachowania filtra.", "difficulty": "advanced"},
                ],
                "warning": "Zrób kopię zapasową przed zmianami w systemie.",
            },
            "graph_node_descriptions": {},
            "story_slides": [],
            "quiz": [],
        }

    def _merge_sections(self, base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        """Fill missing keys from partial LLM responses."""
        for key, val in extra.items():
            if not base.get(key) and val:
                base[key] = val
            elif key == "overview" and isinstance(val, dict):
                base.setdefault("overview", {})
                for k, v in val.items():
                    if v and not base["overview"].get(k):
                        base["overview"][k] = v
        return base

    def generate(self, repo: RepoInfo, static: StaticAnalysis) -> EducationPack:
        """Full pipeline: LLM sections + charts + graph + sanitization."""
        facts: Optional[Dict[str, Any]] = None
        try:
            facts = self._story._extract_facts(repo, static)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Facts extraction failed: %s", exc)

        raw = self._fallback_sections(repo, static, facts)
        try:
            llm_parts = self._generate_sections(repo, static)
            raw = self._merge_sections(raw, llm_parts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Education sections LLM failed: %s", exc)

        if facts:
            if not raw.get("essence"):
                raw["essence"] = facts.get("one_line", "")
            pname = facts.get("project_name") or repo.slug.split("_")[-1]
            raw["title"] = raw.get("title") or f"Przewodnik: {pname}"

        raw = self._apply_polish_gate(raw)

        pack = EducationPack.from_dict(raw)
        charts = build_charts(repo, static)
        node_desc = raw.get("graph_node_descriptions") or {}
        graph = build_dependency_graph(repo, static, node_descriptions=node_desc)

        pack.charts = charts
        pack.dependency_graph = graph
        if not pack.flow_mermaid and pack.flow_steps:
            pack.flow_mermaid = flow_steps_to_mermaid([s.to_dict() for s in pack.flow_steps])
        if pack.howto and not pack.install_flow_mermaid:
            pack.install_flow_mermaid = howto_to_mermaid([h.to_dict() for h in pack.howto])

        if not pack.story_slides:
            try:
                deck = self._story.generate(repo, static)
                pack.story_slides = [s.to_dict() for s in deck.slides]
                if not pack.quiz:
                    pack.quiz = [q.to_dict() for q in deck.quiz]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Story slides fallback failed: %s", exc)

        pack = self._sanitize_pack(pack)
        return pack

    def _apply_polish_gate(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure user-facing education fields are Polish."""
        raw["title"] = ensure_polish(str(raw.get("title", "")), context="title")
        raw["essence"] = ensure_polish(str(raw.get("essence", "")), context="essence")
        raw["summary_3"] = [
            ensure_polish(str(s), context="summary") for s in (raw.get("summary_3") or []) if s
        ]
        while len(raw.get("summary_3") or []) < 3:
            raw.setdefault("summary_3", []).append("")
        raw["overview"] = polish_overview(dict(raw.get("overview") or {}))
        raw["use_cases"] = polish_use_cases(list(raw.get("use_cases") or []))
        raw["flow_steps"] = polish_flow_steps(list(raw.get("flow_steps") or []))
        raw["howto"] = polish_howto(list(raw.get("howto") or []))
        return raw

    def _sanitize_pack(self, pack: EducationPack) -> EducationPack:
        """Light sanitization of user-facing strings."""
        pack.title = _sanitize_plain(pack.title) or "Przewodnik po projekcie"
        pack.essence = _sanitize_plain(pack.essence)
        pack.summary_3 = [_sanitize_plain(s) for s in pack.summary_3]
        for key in list(pack.overview.keys()):
            pack.overview[key] = _sanitize_plain(str(pack.overview[key]))
        for uc in pack.use_cases:
            uc.title = _sanitize_plain(uc.title)
            uc.scenario = _sanitize_plain(uc.scenario)
            uc.benefit = _sanitize_plain(uc.benefit)
        for fs in pack.flow_steps:
            fs.title = _sanitize_plain(fs.title)
            fs.description = _sanitize_plain(fs.description)
            fs.tip = _sanitize_plain(fs.tip)
        for ht in pack.howto:
            ht.title = _sanitize_plain(ht.title)
            ht.body = _sanitize_plain(ht.body)
        mg = pack.modify_guide
        for item in mg.get("easy", []) + mg.get("advanced", []):
            if isinstance(item, dict):
                item["title"] = _sanitize_plain(str(item.get("title", "")))
                item["body"] = _sanitize_plain(str(item.get("body", "")))
        if mg.get("warning"):
            mg["warning"] = _sanitize_plain(str(mg["warning"]))
        return pack
