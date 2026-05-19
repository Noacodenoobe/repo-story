"""
Unit tests for safe command runner (Phase B1).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.app.action_runner import assess_risk, run_command, validate_command


class TestActionRunner(unittest.TestCase):
    """Whitelist validation and execution."""

    def test_allows_ollama_list(self) -> None:
        ok, reason = validate_command("ollama list")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_blocks_rm(self) -> None:
        ok, reason = validate_command("rm -rf /tmp/foo")
        self.assertFalse(ok)

    def test_blocks_sudo(self) -> None:
        ok, _ = validate_command("sudo apt update")
        self.assertFalse(ok)

    def test_assess_without_confirm(self) -> None:
        result = assess_risk("ollama list")
        self.assertTrue(result["allowed"])

    def test_run_requires_whitelist(self) -> None:
        with self.assertRaises(ValueError):
            run_command("rm -rf /")

    @patch("backend.app.action_runner.subprocess.run")
    def test_run_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        out = run_command("ollama list")
        self.assertEqual(out["exit_code"], 0)
        self.assertIn("ok", out["stdout"])


if __name__ == "__main__":
    unittest.main()
