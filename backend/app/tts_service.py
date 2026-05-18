"""
Text-to-speech via Piper CLI (offline, Polish voice on /mnt/ollama).
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class TtsError(RuntimeError):
    """TTS pipeline failure."""


class TtsService:
    """Synthesize Polish speech using Piper subprocess."""

    def __init__(
        self,
        piper_bin: Optional[Path] = None,
        model_path: Optional[Path] = None,
    ) -> None:
        self.piper_bin = piper_bin or config.PIPER_BIN
        self.model_path = model_path or config.PIPER_MODEL
        self.max_chars = config.TTS_MAX_CHARS

    def _normalize_text(self, text: str) -> str:
        """Strip markdown noise for more natural speech."""
        cleaned = text.strip()
        cleaned = re.sub(r"```[\s\S]*?```", " ", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"\*+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > self.max_chars:
            cleaned = cleaned[: self.max_chars].rsplit(" ", 1)[0] + "…"
        return cleaned

    def synthesize_wav(self, text: str) -> Path:
        """
        Generate a temporary WAV file from text.

        Returns:
            Path to WAV file (caller may delete after sending).
        """
        normalized = self._normalize_text(text)
        if not normalized:
            raise TtsError("Brak tekstu do odczytania.")

        if not self.piper_bin.is_file():
            raise TtsError(f"Brak Piper: {self.piper_bin}")
        if not self.model_path.is_file():
            raise TtsError(f"Brak modelu głosu: {self.model_path}")

        fd, out_name = tempfile.mkstemp(suffix=".wav", prefix="repo-story-tts-")
        os.close(fd)
        out_path = Path(out_name)
        proc = subprocess.run(
            [
                str(self.piper_bin),
                "--model",
                str(self.model_path),
                "--output_file",
                str(out_path),
            ],
            input=normalized,
            capture_output=True,
            text=True,
            timeout=config.TTS_TIMEOUT_S,
        )
        if proc.returncode != 0 or not out_path.is_file() or out_path.stat().st_size < 100:
            err = (proc.stderr or proc.stdout or "piper failed")[-400:]
            if out_path.is_file():
                out_path.unlink(missing_ok=True)
            raise TtsError(f"Synteza mowy nieudana: {err}")

        return out_path
