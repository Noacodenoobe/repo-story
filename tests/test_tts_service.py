"""
Unit tests for TTS service (Phase 3).
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.tts_service import TtsError, TtsService


class TestTtsService(unittest.TestCase):
    """TtsService with mocked Piper subprocess."""

    def setUp(self) -> None:
        self.service = TtsService(
            piper_bin=Path("/fake/piper"),
            model_path=Path("/fake/model.onnx"),
        )

    def test_normalize_strips_markdown(self) -> None:
        out = self.service._normalize_text("## Tytuł\n`apt install` **bold**")
        self.assertNotIn("##", out)
        self.assertIn("apt install", out)

    @patch("backend.app.tts_service.subprocess.run")
    def test_synthesize_wav_success(self, mock_run: MagicMock) -> None:
        fake_bin = MagicMock()
        fake_bin.is_file.return_value = True
        fake_model = MagicMock()
        fake_model.is_file.return_value = True
        self.service.piper_bin = fake_bin
        self.service.model_path = fake_model

        def touch_wav(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_bytes(b"RIFF" + b"\0" * 200)
            result = MagicMock()
            result.returncode = 0
            return result

        mock_run.side_effect = touch_wav
        path = self.service.synthesize_wav("Cześć świecie")
        self.assertTrue(path.is_file())
        path.unlink(missing_ok=True)

    def test_synthesize_empty_text(self) -> None:
        with self.assertRaises(TtsError):
            self.service.synthesize_wav("   ")


if __name__ == "__main__":
    unittest.main()
