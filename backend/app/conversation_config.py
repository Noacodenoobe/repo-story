"""
Conversation behavior presets for text and voice chat.
"""
from __future__ import annotations

from . import config

_BASE = (
    "Jesteś asystentem konfiguracji Linux i narzędzi open source. "
    "Odpowiadasz po polsku, konkretnie, z komendami gdy to potrzebne. "
    "Uwzględniaj profil sprzętu i zainstalowanych narzędzi użytkownika z kontekstu. "
    "Na końcu wymień źródła w formacie [guide:Tytuł / sekcja]."
)

_VOICE = (
    "Tryb rozmowy głosowej: mów naturalnie i zwięźle. "
    "Zacznij od 2–4 zdań treści, potem szczegóły tylko jeśli potrzebne. "
    "Unikaj długich list i nagłówków markdown — zamiast tego krótkie akapity. "
    "Komendy podawaj pojedynczo, w osobnych liniach. "
    "Jeśli pytanie jest proste, odpowiedz jednym akapitem."
)

_DETAILED = (
    "Tryb szczegółowy: możesz używać list, kroków i dłuższych wyjaśnień, "
    "gdy użytkownik prosi o instrukcję krok po kroku."
)


def build_system_prompt(voice_mode: bool = False) -> str:
    """
    Build LLM system prompt for the active conversation mode.

    Args:
        voice_mode: Shorter, speech-friendly answers (Phase 3).

    Returns:
        Full system string for Ollama.
    """
    mode = (config.CHAT_CONVERSATION_MODE or "balanced").lower()
    parts = [_BASE]
    if voice_mode or mode == "voice":
        parts.append(_VOICE)
    elif mode == "detailed":
        parts.append(_DETAILED)
    return " ".join(parts)
