"""
Speech-to-text via faster-whisper subprocess (audio-core venv).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from . import config
from .stt_quality import REJECT_MESSAGES, validate_transcript, wav_rms

logger = logging.getLogger(__name__)


class SttError(RuntimeError):
    """STT pipeline failure."""


class SttService:
    """Convert uploaded audio to text using external Whisper venv."""

    def __init__(
        self,
        audio_core_python: Optional[Path] = None,
        transcribe_script: Optional[Path] = None,
    ) -> None:
        self.audio_core_python = audio_core_python or config.AUDIO_CORE_PYTHON
        self.transcribe_script = transcribe_script or config.TRANSCRIBE_SCRIPT
        self.max_bytes = config.STT_MAX_AUDIO_MB * 1024 * 1024
        self.timeout_s = config.STT_TIMEOUT_S

    def _check_prerequisites(self) -> None:
        if not self.audio_core_python.is_file():
            raise SttError(
                f"Brak Pythona audio-core: {self.audio_core_python}. "
                "Sprawdź /mnt/ollama/ai-envs/audio-core/.venv"
            )
        if not self.transcribe_script.is_file():
            raise SttError(f"Brak skryptu transkrypcji: {self.transcribe_script}")
        if not _which("ffmpeg"):
            raise SttError(
                "Brak ffmpeg — zainstaluj: sudo apt install ffmpeg"
            )

    def _convert_to_wav(self, source: Path, dest: Path) -> None:
        """Normalize input to 16 kHz mono WAV for Whisper."""
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(dest),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "ffmpeg failed")[-500:]
            raise SttError(f"Konwersja audio nieudana: {err}")

    def _run_whisper(self, wav_path: Path) -> Dict[str, Any]:
        env = os.environ.copy()
        env["HF_HOME"] = str(config.WHISPER_MODELS_DIR)
        env["WHISPER_MODELS_DIR"] = str(config.WHISPER_MODELS_DIR)
        env["STT_MODEL"] = config.STT_MODEL
        env["STT_FALLBACK_MODEL"] = config.STT_FALLBACK_MODEL

        proc = subprocess.run(
            [
                str(self.audio_core_python),
                str(self.transcribe_script),
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            env=env,
        )
        stdout = (proc.stdout or "").strip()
        if proc.returncode != 0:
            detail = stdout or (proc.stderr or "")[-500:]
            try:
                payload = json.loads(stdout)
                detail = payload.get("error", detail)
            except json.JSONDecodeError:
                pass
            raise SttError(detail or "Transkrypcja nieudana.")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SttError(f"Nieprawidłowa odpowiedź STT: {stdout[:200]}") from exc

    def transcribe_bytes(
        self,
        data: bytes,
        filename: str = "audio.webm",
    ) -> Dict[str, Any]:
        """
        Transcribe raw upload bytes (webm, wav, ogg, etc.).

        Args:
            data: Raw file content.
            filename: Original filename (for extension hint).

        Returns:
            JSON-serializable dict with text, language, duration_s, model.
        """
        if len(data) > self.max_bytes:
            raise SttError(
                f"Plik za duży (max {config.STT_MAX_AUDIO_MB} MB)."
            )
        if len(data) < 100:
            raise SttError("Nagranie jest puste lub za krótkie.")

        self._check_prerequisites()
        suffix = Path(filename).suffix or ".webm"

        with tempfile.TemporaryDirectory(prefix="repo-story-stt-") as tmp:
            tmp_dir = Path(tmp)
            raw_path = tmp_dir / f"upload{suffix}"
            wav_path = tmp_dir / "audio.wav"
            raw_path.write_bytes(data)
            self._convert_to_wav(raw_path, wav_path)
            if not wav_path.is_file() or wav_path.stat().st_size < 100:
                raise SttError("Po konwersji brak dźwięku — sprawdź mikrofon.")

            rms = wav_rms(wav_path)
            result = self._run_whisper(wav_path)
            duration_s = float(result.get("duration_s") or 0)
            text, reason = validate_transcript(
                result.get("text", ""),
                duration_s,
                rms,
                min_duration_s=config.STT_MIN_DURATION_S,
                min_rms=config.STT_MIN_RMS,
            )
            if reason:
                msg = REJECT_MESSAGES.get(reason, "Nie rozpoznano mowy.")
                logger.info(
                    "STT rejected (%s): rms=%.4f dur=%.2fs raw=%r",
                    reason,
                    rms,
                    duration_s,
                    (result.get("text") or "")[:80],
                )
                raise SttError(msg)
            result["text"] = text
            result["rms"] = round(rms, 5)
            return result


def _which(cmd: str) -> Optional[str]:
    from shutil import which

    return which(cmd)
