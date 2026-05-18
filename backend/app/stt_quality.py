"""
STT quality checks: silence detection and Whisper hallucination filtering.
"""
from __future__ import annotations

import re
import wave
from pathlib import Path
from typing import Optional, Tuple

# Common Whisper hallucinations on silence/noise (especially Polish YouTube subs).
_HALLUCINATION_PATTERNS: Tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"amara\.org",
        r"napisy stworzone",
        r"subtitles? by",
        r"subskrybuj",
        r"dzi[eę]kuj[eę] za ogl[aą]danie",
        r"www\.",
        r"napisy:",
        r"tlumaczenie",
        r"tłumaczenie",
        r"copyright",
        r"all rights reserved",
    )
)


def wav_rms(path: Path) -> float:
    """
    Compute RMS amplitude of a mono 16-bit WAV file.

    Returns:
        RMS in 0.0–1.0 range, or 0.0 if unreadable.
    """
    try:
        with wave.open(str(path), "rb") as wf:
            nch = wf.getnchannels()
            width = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
        if width != 2 or not frames:
            return 0.0
        import struct

        count = len(frames) // 2
        samples = struct.unpack(f"<{count}h", frames[: count * 2])
        if nch > 1:
            samples = samples[::nch]
        if not samples:
            return 0.0
        mean_sq = sum(s * s for s in samples) / len(samples)
        return (mean_sq ** 0.5) / 32768.0
    except Exception:
        return 0.0


def is_hallucination(text: str) -> bool:
    """Return True if transcript matches known silence hallucinations."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return True
    if len(cleaned) < 3:
        return True
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False


def validate_transcript(
    text: str,
    duration_s: float,
    rms: float,
    *,
    min_duration_s: float = 0.35,
    min_rms: float = 0.008,
) -> Tuple[str, Optional[str]]:
    """
    Validate STT output.

    Returns:
        (accepted_text, reject_reason). reason is None when accepted.
    """
    if duration_s < min_duration_s:
        return "", "too_short"
    if rms < min_rms:
        return "", "silence"
    cleaned = (text or "").strip()
    if not cleaned:
        return "", "empty"
    if is_hallucination(cleaned):
        return "", "hallucination"
    return cleaned, None


REJECT_MESSAGES = {
    "too_short": "Nagranie za krótkie — kliknij 🎤, poczekaj chwilę i mów wyraźniej.",
    "silence": "Wykryto ciszę lub sam szum — nie wysyłam fałszywego tekstu. Spróbuj ponownie.",
    "hallucination": "Whisper zgadywał napisy z szumu (np. Amara.org) — powtórz pytanie.",
    "empty": "Nie rozpoznano mowy — mów bliżej mikrofonu.",
}
