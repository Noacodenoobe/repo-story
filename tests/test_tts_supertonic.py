"""
Unit tests for Supertonic TTS path (Phase A1).
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.tts_service import TtsError, TtsService


class TestTtsSupertonic(unittest.TestCase):
    """Supertonic backend with mocked subprocess."""

    def setUp(self) -> None:
        self.service = TtsService(
            piper_bin=Path("/fake/piper"),
            model_path=Path("/fake/model.onnx"),
            backend="supertonic",
            supertonic_bin=Path("/fake/supertonic"),
        )

    @patch("backend.app.tts_service.subprocess.run")
    def test_supertonic_synthesize(self, mock_run: MagicMock) -> None:
        fake_st = MagicMock()
        fake_st.is_file.return_value = True
        self.service.supertonic_bin = fake_st

        def touch_wav(cmd, **kwargs):
            out = Path(cmd[cmd.index("-o") + 1])
            out.write_bytes(b"RIFF" + b"\0" * 200)
            return MagicMock(returncode=0)

        mock_run.side_effect = touch_wav
        path = self.service.synthesize_wav("Test polski", backend="supertonic")
        self.assertTrue(path.is_file())
        path.unlink(missing_ok=True)
        args = mock_run.call_args[0][0]
        self.assertIn("tts", args)
        self.assertIn("--lang", args)

    @patch.object(TtsService, "_synthesize_piper")
    @patch.object(TtsService, "_synthesize_supertonic")
    def test_fallback_to_piper(self, mock_st: MagicMock, mock_piper: MagicMock) -> None:
        mock_st.side_effect = TtsError("fail")
        mock_piper.return_value = Path("/tmp/x.wav")
        self.service.synthesize_wav("hello", backend="supertonic")
        mock_piper.assert_called_once()


if __name__ == "__main__":
    unittest.main()
