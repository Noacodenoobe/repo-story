"""
Tests for STT hallucination and silence filtering.
"""
from __future__ import annotations

import unittest

from backend.app.stt_quality import is_hallucination, validate_transcript


class TestSttQuality(unittest.TestCase):
    """STT post-processing rules."""

    def test_amara_hallucination(self) -> None:
        text = "Napisy stworzone przez społeczność Amara.org"
        self.assertTrue(is_hallucination(text))
        _, reason = validate_transcript(text, 2.0, 0.05)
        self.assertEqual(reason, "hallucination")

    def test_silence_rejected(self) -> None:
        _, reason = validate_transcript("cześć", 1.0, 0.001)
        self.assertEqual(reason, "silence")

    def test_valid_polish(self) -> None:
        text, reason = validate_transcript(
            "Jak zainstalować NoiseTorch na Ubuntu?",
            3.0,
            0.05,
        )
        self.assertIsNone(reason)
        self.assertIn("NoiseTorch", text)


if __name__ == "__main__":
    unittest.main()
