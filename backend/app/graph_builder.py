"""
Build charts data and dependency graphs from static analysis + README.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .code_analyzer import StaticAnalysis
from .education_pack import GraphEdge, GraphNode
from .readme_heuristics import build_readme_context
from .repo_fetcher import RepoInfo


def build_charts(repo: RepoInfo, static: StaticAnalysis) -> Dict[str, Any]:
    """Chart.js-ready datasets."""
    langs = static.languages or {}
    top_langs = sorted(langs.items(), key=lambda x: -x[1])[:8]
    ctx = build_readme_context(repo.path, langs)
    composition = ctx.get("composition") or {"Kod": static.total_files}

    return {
        "languages": {
            "labels": [k for k, _ in top_langs],
            "values": [v for _, v in top_langs],
        },
        "composition": {
            "labels": list(composition.keys()),
            "values": list(composition.values()),
        },
        "metrics": {
            "files": static.total_files,
            "lines": static.total_lines,
        },
    }


def _infer_ecosystem_nodes(static: StaticAnalysis, project_name: str) -> List[GraphNode]:
    """Create default ecosystem nodes from detected tech."""
    nodes = [
        GraphNode(
            id="user",
            label="Ty (użytkownik)",
            role="Użytkownik",
            description="Osoba korzystająca z programu na swoim komputerze.",
            group="people",
        ),
        GraphNode(
            id="app",
            label=project_name,
            role="Główny program",
            description="Centralna aplikacja opisywanego projektu.",
            group="core",
        ),
    ]
    fw = static.frameworks or []
    deps = static.dependencies or []

    if any("docker" in f.lower() for f in fw):
        nodes.append(
            GraphNode(
                id="docker",
                label="Kontener / Docker",
                role="Środowisko uruchomienia",
                description="Program może działać w izolowanym środowisku kontenerowym.",
                group="infra",
            )
        )
    if any("node" in f.lower() or "npm" in f.lower() for f in fw):
        nodes.append(
            GraphNode(
                id="runtime",
                label="Środowisko Node.js",
                role="Silnik uruchomieniowy",
                description="Warstwa, na której działa wiele nowoczesnych aplikacji webowych.",
                group="infra",
            )
        )
    if any("go" in f.lower() for f in fw):
        nodes.append(
            GraphNode(
                id="go_runtime",
                label="Środowisko Go",
                role="Silnik uruchomieniowy",
                description="Skompilowany program działający bezpośrednio w systemie.",
                group="infra",
            )
        )
    if any("python" in f.lower() for f in fw):
        nodes.append(
            GraphNode(
                id="python_runtime",
                label="Środowisko Python",
                role="Silnik uruchomieniowy",
                description="Interpreter Pythona uruchamiający skrypty projektu.",
                group="infra",
            )
        )

    for i, dep in enumerate(deps[:6]):
        safe = re.sub(r"[^a-z0-9]", "_", dep.lower())[:20]
        nodes.append(
            GraphNode(
                id=f"dep_{i}_{safe}",
                label=dep[:40],
                role="Biblioteka pomocnicza",
                description=f"Zewnętrzny komponent, z którego korzysta projekt: {dep}.",
                group="library",
            )
        )

    nodes.append(
        GraphNode(
            id="os",
            label="System operacyjny",
            role="System",
            description="Linux, Windows lub inny system, na którym wszystko działa.",
            group="infra",
        )
    )
    return nodes


def _readme_extra_nodes(readme: str, project_name: str) -> List[GraphNode]:
    """Add nodes hinted by README keywords."""
    extra: List[GraphNode] = []
    lower = readme.lower()
    hints = [
        ("pulseaudio", "PulseAudio", "System dźwięku w Linuxie", "audio"),
        ("pipewire", "PipeWire", "Nowszy system dźwięku w Linuxie", "audio"),
        ("microphone", "Mikrofon", "Twoje urządzenie nagrywające głos", "hardware"),
        ("discord", "Aplikacje (Discord, Zoom…)", "Programy, które korzystają z mikrofonu", "apps"),
        ("ollama", "Serwer AI (Ollama)", "Lokalny silnik modeli językowych", "ai"),
        ("openai", "Usługa AI w chmurze", "Zewnętrzna usługa sztucznej inteligencji", "ai"),
        ("obsidian", "Obsidian", "Aplikacja notatek, z którą integruje się wtyczka", "apps"),
        ("github", "GitHub", "Miejsce publikacji i pobierania kodu", "cloud"),
    ]
    for key, label, desc, group in hints:
        if key in lower:
            nid = re.sub(r"[^a-z0-9]", "_", key)
            extra.append(GraphNode(id=nid, label=label, role="Powiązany element", description=desc, group=group))
    return extra


def build_dependency_graph(
    repo: RepoInfo,
    static: StaticAnalysis,
    node_descriptions: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Interactive graph nodes and edges."""
    ctx = build_readme_context(repo.path, static.languages or {})
    readme = ctx.get("readme_excerpt", "")
    name = repo.slug.split("_")[-1] if "_" in repo.slug else "Projekt"
    name = name.replace("-", " ").title()

    nodes = _infer_ecosystem_nodes(static, name)
    seen_ids = {n.id for n in nodes}
    for extra in _readme_extra_nodes(readme, name):
        if extra.id not in seen_ids:
            nodes.append(extra)
            seen_ids.add(extra.id)

    if node_descriptions:
        for node in nodes:
            if node.id in node_descriptions:
                node.description = node_descriptions[node.id][:400]

    edges: List[GraphEdge] = [
        GraphEdge("user", "app", "uruchamia / konfiguruje"),
        GraphEdge("app", "os", "działa na"),
    ]
    for node in nodes:
        if node.id.startswith("dep_"):
            edges.append(GraphEdge("app", node.id, "korzysta z"))
        if node.id in ("runtime", "go_runtime", "python_runtime", "docker"):
            edges.append(GraphEdge("app", node.id, "wymaga"))
            edges.append(GraphEdge(node.id, "os", "na"))
        if node.group == "audio":
            edges.append(GraphEdge("app", node.id, "podłącza się do"))
            edges.append(GraphEdge("user", node.id, "słyszy przez"))
        if node.group == "apps":
            edges.append(GraphEdge(node.id, "app", "korzysta z"))
        if node.group == "ai":
            edges.append(GraphEdge("app", node.id, "wysyła zapytania do"))

    return {
        "nodes": [n.to_dict() for n in nodes],
        "edges": [e.to_dict() for e in edges],
    }


def _mermaid_label(step: Dict[str, Any], max_len: int = 80) -> str:
    """Build node label with title and short description."""
    title = (step.get("title") or "Krok").replace('"', "'").replace("\n", " ")
    desc = (step.get("description") or "").replace('"', "'").replace("\n", " ")
    tip = (step.get("tip") or "").replace('"', "'")
    if desc:
        short = desc[:55] + ("…" if len(desc) > 55 else "")
        label = f"{title}\\n{short}"
    else:
        label = title[:max_len]
    if tip:
        label += f"\\n💡 {tip[:40]}"
    return label[:max_len]


def flow_steps_to_mermaid(steps: List[Dict[str, Any]]) -> str:
    """Convert flow steps to a Mermaid flowchart with descriptions."""
    if not steps:
        return "flowchart TD\n    A[Brak danych]"
    lines = ["flowchart TD"]
    prev = None
    for i, step in enumerate(steps):
        sid = f"s{i}"
        label = _mermaid_label(step)
        lines.append(f'    {sid}["{label}"]')
        if prev:
            lines.append(f"    {prev} --> {sid}")
        prev = sid
    return "\n".join(lines)


def howto_to_mermaid(howto_steps: List[Dict[str, Any]]) -> str:
    """Installation-only flowchart from howto steps."""
    if not howto_steps:
        return ""
    steps = []
    for h in howto_steps:
        cmds = h.get("commands") or []
        tip = (cmds[0][:60] + "…") if cmds and len(cmds[0]) > 60 else (cmds[0] if cmds else "")
        steps.append({
            "title": h.get("title") or f"Krok {h.get('step')}",
            "description": h.get("body") or "",
            "tip": tip,
        })
    return flow_steps_to_mermaid(steps)
