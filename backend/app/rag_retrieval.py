"""
RAG retrieval helpers: query expansion, guide focus, chunk ranking.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from . import config
from .chat_grounding import is_meta_system_question
from .knowledge_store import KnowledgeStore
from .llm_client import OllamaClient

# Generic install words that skew embeddings toward unrelated guides.
_GENERIC_QUERY_WORDS = frozenset({
    "system", "systemie", "systemu", "instalować", "instalacja", "zainstalować",
    "mogę", "moj", "moje", "mojego", "komputerze", "linux", "ubuntu",
    "wykorzystać", "użyć", "uzywac", "pytanie", "odpowiedz",
})

_SOURCE_PRIORITY = {
    "guide": 0,
    "user_note": 1,
    "rules": 2,
    "system": 3,
    "technical": 4,
}

# User phrasing -> slug fragment (must match guides.slug).
_FOCUS_SLUG_ALIASES: List[Tuple[Tuple[str, ...], str]] = [
    (
        (
            "bpm-asystent",
            "bpm asystent",
            "bpm-assistant",
            "bpm assistanta",
            "bpmn asystent",
            "asystenta",
        ),
        "bpmn-assistant",
    ),
    (("layout generator", "bpmn-layout", "layout-generators"), "bpmn-layout-generators"),
    (("noisetorch",), "noisetorch"),
    (("openwhispr",), "openwhispr"),
]


def _normalize(text: str) -> str:
    """Lowercase and strip diacritics-ish for fuzzy match."""
    t = text.lower()
    for a, b in (("ą", "a"), ("ć", "c"), ("ę", "e"), ("ł", "l"), ("ń", "n"),
                 ("ó", "o"), ("ś", "s"), ("ź", "z"), ("ż", "z")):
        t = t.replace(a, b)
    return t


def _tokens(text: str) -> Set[str]:
    """Word tokens length >= 3 for overlap scoring."""
    norm = _normalize(text)
    return {w for w in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", norm) if w not in _GENERIC_QUERY_WORDS}


def build_retrieval_query(
    message: str,
    history: List[Dict[str, Any]],
    guides: List[Dict[str, Any]],
) -> str:
    """
    Build an embedding query from the current turn and recent dialogue.

    Args:
        message: Latest user message.
        history: Recent chat rows from SQLite.
        guides: Guide metadata for title boosting.

    Returns:
        Text to embed for vector search.
    """
    parts: List[str] = [message.strip()]
    for msg in history[-6:]:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = (msg.get("content") or "").strip()
        if content:
            parts.append(content[:500])

    combined = " ".join(parts)
    combined_norm = _normalize(combined)
    msg_tokens = _tokens(message)

    for guide in guides:
        title = guide.get("title") or ""
        title_norm = _normalize(title)
        # Strong match: user message mentions distinctive title words.
        title_words = [w for w in re.findall(r"[a-z0-9]{3,}", title_norm) if w not in ("przewodnik", "guide")]
        if len(title_words) >= 2 and sum(1 for w in title_words if w in combined_norm) >= 2:
            parts.append(title)
            continue
        if any(w in combined_norm for w in title_words if len(w) >= 5):
            parts.append(title)
            continue
        slug = (guide.get("slug") or "").replace("_", " ").replace("-", " ")
        for token in msg_tokens:
            if len(token) >= 5 and token in _normalize(slug):
                parts.append(title)
                break

    return " ".join(parts)[:3000]


def detect_focus_guide(
    message: str,
    history: List[Dict[str, Any]],
    guides: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Pick the guide most likely referenced in the current turn.

    Returns:
        Guide dict or None if ambiguous.
    """
    combined = _normalize(
        message + " " + " ".join(
            (m.get("content") or "")[:400]
            for m in history[-4:]
            if m.get("role") in ("user", "assistant")
        )
    )
    best: Optional[Dict[str, Any]] = None
    best_score = 0

    for guide in guides:
        title = guide.get("title") or ""
        title_norm = _normalize(title)
        slug_norm = _normalize((guide.get("slug") or "").replace("_", " "))
        score = 0
        for word in re.findall(r"[a-z0-9]{4,}", title_norm):
            if word in ("przewodnik", "guide", "asystent", "assistant"):
                continue
            if word in combined:
                score += 3 if len(word) >= 6 else 2
        for word in re.findall(r"[a-z0-9]{4,}", slug_norm):
            if word in combined:
                score += 2
        for needles, slug_hint in _FOCUS_SLUG_ALIASES:
            if any(n in combined for n in needles) and slug_hint in slug_norm:
                score += 20
        if "bpm" in combined and "asyst" in combined and "bpmn-assistant" in slug_norm:
            score += 18
        # "BPM" alone matches many guides — prefer slug alias, penalize wrong BPM project.
        if ("asystent" in combined or "assistant" in combined) and "asystent" not in title_norm:
            if "layout" in title_norm or "generator" in title_norm:
                score -= 15
        if "noisetorch" in combined and "noisetorch" in title_norm:
            score += 4
        if score > best_score:
            best_score = score
            best = guide

    return best if best_score >= 4 else None


def _chunk_key(chunk: Dict[str, Any]) -> str:
    return str(chunk.get("chunk_id") or id(chunk))


def merge_hits(
    primary: List[Tuple[float, Dict[str, Any]]],
    secondary: List[Tuple[float, Dict[str, Any]]],
) -> List[Tuple[float, Dict[str, Any]]]:
    """Merge search results by chunk id, keeping max score."""
    merged: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    for score, chunk in primary + secondary:
        cid = _chunk_key(chunk)
        if cid not in merged or score > merged[cid][0]:
            merged[cid] = (score, chunk)
    return sorted(merged.values(), key=lambda x: -x[0])


def rank_and_filter_hits(
    hits: List[Tuple[float, Dict[str, Any]]],
    focus_guide_id: Optional[str],
    min_score: float,
    top_k: int,
    message: str = "",
) -> List[Tuple[float, Dict[str, Any]]]:
    """
    Apply score threshold, optional guide focus, and per-source limits.

    Returns:
        Filtered ranked hits.
    """
    filtered: List[Tuple[float, Dict[str, Any]]] = []
    for score, chunk in hits:
        if score < min_score:
            continue
        filtered.append((score, chunk))

    if focus_guide_id:
        focused = [(s, c) for s, c in filtered if c.get("guide_id") == focus_guide_id]
        other = [(s, c) for s, c in filtered if c.get("guide_id") != focus_guide_id]
        # Allow profile/rules chunks alongside the focused guide.
        extras = [
            (s, c) for s, c in other
            if (c.get("source_type") or "") in ("rules", "system", "user_note")
        ][:2]
        if focused:
            filtered = focused + extras
        elif other:
            filtered = other

    msg_norm = _normalize(message)
    install_intent = any(w in msg_norm for w in ("instal", "sciezk", "folder", "katalog", "clone", "git"))

    # Prefer howto/flow sections when present in focused guide.
    def sort_key(item: Tuple[float, Dict[str, Any]]) -> Tuple[float, float, float]:
        score, chunk = item
        section = (chunk.get("section") or "").lower()
        section_boost = 0.0
        if section.startswith("howto"):
            section_boost = 0.12 if install_intent else 0.06
        elif section.startswith("overview"):
            section_boost = 0.04
        elif section == "flow" and not install_intent:
            section_boost = 0.05
        stype = chunk.get("source_type") or "guide"
        type_rank = _SOURCE_PRIORITY.get(stype, 5)
        return (-(score + section_boost), type_rank, -score)

    filtered.sort(key=sort_key)

    # Cap chunks per guide for diversity unless focused.
    if not focus_guide_id:
        per_guide: Dict[str, int] = {}
        limited: List[Tuple[float, Dict[str, Any]]] = []
        for item in filtered:
            gid = str(item[1].get("guide_id") or "global")
            if per_guide.get(gid, 0) >= 2:
                continue
            per_guide[gid] = per_guide.get(gid, 0) + 1
            limited.append(item)
        filtered = limited

    return filtered[:top_k]


def retrieve_for_chat(
    store: KnowledgeStore,
    client: OllamaClient,
    message: str,
    session_id: str,
    *,
    include_profile: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str], Optional[str]]:
    """
    Run expanded RAG retrieval for a chat turn.

    Returns:
        (citations, context_parts, focus_guide_title or None)
    """
    history = store.get_chat_history(session_id, limit=config.CHAT_HISTORY_LIMIT)
    guides = store.list_guides()
    query = build_retrieval_query(message, history, guides)
    focus_guide = detect_focus_guide(message, history, guides)
    focus_id = focus_guide.get("id") if focus_guide else None

    q_emb = client.embed(query[:2000])
    hits = store.search_chunks(q_emb, top_k=config.TOP_K_RETRIEVAL + 4)

    # Second pass with guide title when focus detected.
    if focus_guide and focus_guide.get("title") and focus_id:
        title_query = (
            f"{focus_guide['title']} instalacja howto git clone ścieżki katalog komendy readme"
        )
        t_emb = client.embed(title_query[:2000])
        focused_hits = [
            (score, chunk)
            for score, chunk in store.search_chunks(
                t_emb, top_k=config.TOP_K_RETRIEVAL + 8
            )
            if chunk.get("guide_id") == focus_id
        ]
        hits = merge_hits(hits, focused_hits)

    if is_meta_system_question(message):
        meta_query = (
            "regulamin standard projektu ścieżki /mnt/ollama struktura folderów profil systemu"
        )
        meta_emb = client.embed(meta_query[:2000])
        meta_hits = [
            (score, chunk)
            for score, chunk in store.search_chunks(meta_emb, top_k=8)
            if (chunk.get("source_type") or "") in ("rules", "system")
        ]
        hits = merge_hits(hits, meta_hits)

    min_score = float(getattr(config, "RAG_MIN_SCORE", 0.35))
    ranked = rank_and_filter_hits(
        hits,
        focus_guide_id=focus_id,
        min_score=min_score,
        top_k=config.TOP_K_RETRIEVAL,
        message=message,
    )

    citations: List[Dict[str, Any]] = []
    context_parts: List[str] = []

    for score, chunk in ranked:
        label = chunk.get("guide_title") or "Baza wiedzy"
        section = chunk.get("section") or ""
        citations.append({
            "guide_id": chunk.get("guide_id"),
            "guide_title": label,
            "section": section,
            "excerpt": chunk["text"][:300],
            "score": round(score, 3),
        })
        context_parts.append(f"[{label} / {section}]\n{chunk['text'][:900]}")

    if include_profile:
        profile = store.get_system_profile()
        if profile and profile.get("summary_text"):
            context_parts.append(
                f"[Profil systemu / podsumowanie]\n{profile['summary_text'][:1200]}"
            )

    focus_title = focus_guide.get("title") if focus_guide else None
    return citations, context_parts, focus_title
