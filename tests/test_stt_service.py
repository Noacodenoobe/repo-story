"""
Unit tests for STT service (Phase 2).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.stt_service import SttError, SttService


class TestSttService(unittest.TestCase):
    """SttService with mocked ffmpeg and whisper subprocess."""

    def setUp(self) -> None:
        self.service = SttService(
            audio_core_python=Path("/fake/audio-core/bin/python"),
            transcribe_script=Path("/fake/scripts/transcribe_file.py"),
        )
        self.service.max_bytes = 1024 * 1024

    @patch("backend.app.stt_service._which", return_value="/usr/bin/ffmpeg")
    @patch("backend.app.stt_service.subprocess.run")
    def test_transcribe_bytes_success(
        self,
        mock_run: MagicMock,
        _mock_which: MagicMock,
    ) -> None:
        fake_py = MagicMock()
        fake_py.is_file.return_value = True
        fake_script = MagicMock()
        fake_script.is_file.return_value = True
        self.service.audio_core_python = fake_py
        self.service.transcribe_script = fake_script

        whisper_json = json.dumps({
            "text": "Jak zainstalować NoiseTorch",
            "language": "pl",
            "duration_s": 3.5,
            "model": "medium",
        })

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[0] == "ffmpeg":
                wav = Path(cmd[-1])
                wav.write_bytes(b"RIFF" + b"\0" * 200)
                result.returncode = 0
            else:
                result.returncode = 0
                result.stdout = whisper_json
                result.stderr = ""
            return result

        mock_run.side_effect = run_side_effect

        with patch("backend.app.stt_service.wav_rms", return_value=0.05):
            out = self.service.transcribe_bytes(b"\x00" * 500, filename="test.webm")
        self.assertEqual(out["text"], "Jak zainstalować NoiseTorch")
        self.assertEqual(out["language"], "pl")
        self.assertEqual(mock_run.call_count, 2)

    @patch("backend.app.stt_service._which", return_value="/usr/bin/ffmpeg")
    def test_transcribe_rejects_oversized(self, _mock_which: MagicMock) -> None:
        with self.assertRaises(SttError) as ctx:
            self.service.transcribe_bytes(b"x" * (self.service.max_bytes + 1))
        self.assertIn("za duży", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
