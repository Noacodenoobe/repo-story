"""
Generator diagramów Mermaid.

Tworzy proste, ale czytelne diagramy:
- drzewo struktury katalogów,
- graf zależności na podstawie wykrytych frameworków,
- (opcjonalnie) diagram klas, gdy LLM zwróci listę modułów.

Wybór Mermaid jest celowy - to czysty tekst, nic nie trzeba renderować na
backendzie, frontend pociągnie bibliotekę przez CDN.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List

from .repo_fetcher import RepoInfo

logger = logging.getLogger(__name__)


def _sanitize_id(text: str) -> str:
    """ID węzła Mermaid musi być bezpieczne."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", text)
    return safe[:40] or "node"


def directory_tree_diagram(repo_path: Path, max_depth: int = 2, max_entries: int = 40) -> str:
    """
    Diagram drzewa katalogów (mermaid flowchart LR).

    Pokazuje strukturę do określonej głębokości.
    """
    repo_path = Path(repo_path)
    lines = ["flowchart LR", f"    root([\"{repo_path.name}/\"])"]

    seen: set[str] = set()
    count = 0

    for p in sorted(repo_path.rglob("*")):
        if count >= max_entries:
            lines.append("    more([\"...\"])")
            lines.append("    root --> more")
            break

        rel = p.relative_to(repo_path)
        if any(part.startswith(".") or part in {"node_modules", "__pycache__"} for part in rel.parts):
            continue
        if len(rel.parts) > max_depth:
            continue

        parent = rel.parent
        parent_id = "root" if str(parent) in (".", "") else _sanitize_id(str(parent))
        node_id = _sanitize_id(str(rel))

        if node_id in seen:
            continue
        seen.add(node_id)

        if p.is_dir():
            lines.append(f"    {node_id}[\"📁 {rel.name}/\"]")
        else:
            lines.append(f"    {node_id}([\"📄 {rel.name}\"])")
        lines.append(f"    {parent_id} --> {node_id}")
        count += 1

    return "\n".join(lines)


def language_pie_chart(languages: Dict[str, int]) -> str:
    """Wykres kołowy - udział języków programowania."""
    if not languages:
        return 'pie title Brak danych\n    "brak" : 1'

    lines = ["pie showData", "    title Języki programowania (liczba plików)"]
    for lang, count in languages.items():
        safe_lang = lang.replace('"', "'")
        lines.append(f'    "{safe_lang}" : {count}')
    return "\n".join(lines)


def framework_dependency_graph(frameworks: List[str], dependencies: List[str]) -> str:
    """Prosty graf: projekt -> framework -> biblioteka."""
    lines = ["flowchart TD", "    proj([\"Projekt\"])"]

    if frameworks:
        for f in frameworks:
            fid = _sanitize_id(f)
            lines.append(f"    {fid}[\"{f}\"]")
            lines.append(f"    proj --> {fid}")
    if dependencies:
        for d in dependencies:
            did = _sanitize_id(d)
            lines.append(f"    {did}([\"{d}\"])")
            # Łączymy z pierwszym frameworkiem albo bezpośrednio z projektem
            target = _sanitize_id(frameworks[0]) if frameworks else "proj"
            lines.append(f"    {target} --> {did}")

    if not frameworks and not dependencies:
        lines.append("    proj --> none([\"Brak wykrytych zależności\"])")

    return "\n".join(lines)


def repo_overview_diagram(repo_info: RepoInfo) -> str:
    """Podsumowujący diagram repo - drzewo głównych plików."""
    lines = ["flowchart LR", f"    repo([\"{repo_info.slug}\"])"]
    if repo_info.has_readme:
        lines.append("    readme[\"📄 README\"]")
        lines.append("    repo --> readme")
    if repo_info.has_license:
        lines.append("    lic[\"📄 LICENSE\"]")
        lines.append("    repo --> lic")
    if repo_info.has_dockerfile:
        lines.append("    dock[\"🐳 Dockerfile\"]")
        lines.append("    repo --> dock")
    if repo_info.has_ci:
        lines.append("    ci[\"⚙️ CI/CD\"]")
        lines.append("    repo --> ci")
    if repo_info.has_tests:
        lines.append("    tests[\"🧪 testy\"]")
        lines.append("    repo --> tests")

    for fname in repo_info.main_files[:6]:
        fid = _sanitize_id(fname)
        lines.append(f"    {fid}[\"📄 {fname}\"]")
        lines.append(f"    repo --> {fid}")

    return "\n".join(lines)


def build_all_diagrams(repo_info: RepoInfo, languages: Dict[str, int],
                       frameworks: List[str], dependencies: List[str]) -> Dict[str, str]:
    """Generuje słownik {nazwa_diagramu: kod_mermaid}."""
    out: Dict[str, str] = {}
    out["overview"] = repo_overview_diagram(repo_info)
    out["tree"] = directory_tree_diagram(repo_info.path)
    out["languages"] = language_pie_chart(languages)
    out["dependencies"] = framework_dependency_graph(frameworks, dependencies)
    return out
