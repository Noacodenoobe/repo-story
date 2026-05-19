"""
Unit tests for deployment plan builder (Phase C0).
"""
from __future__ import annotations

import unittest

from backend.app.deployment_plan import build_deployment_plan, deployment_plan_summary_pl


class TestDeploymentPlan(unittest.TestCase):
    """DeploymentPlan from mock howto chunks."""

    def test_build_from_howto_chunks(self) -> None:
        citations = [
            {
                "guide_id": "g1",
                "guide_title": "Przewodnik: BPMN Asystent",
                "section": "howto:1",
                "score": 0.8,
            },
        ]
        context = [
            "[Przewodnik: BPMN Asystent / howto:1]\n"
            "Krok 1: Sklonuj repozytorium\n"
            "Komendy: git clone https://github.com/jtlicardo/bpmn-assistant.git\n"
            "Krok 2: Wejdź do katalogu\n"
            "Komendy: cd bpmn-assistant\n",
        ]
        plan = build_deployment_plan(
            "jak zainstalować bpmn-assistenta",
            citations,
            context,
            focus_guide_title="Przewodnik: BPMN Asystent",
            focus_guide_slug="bpmn-assistant",
        )
        self.assertGreaterEqual(len(plan.steps), 2)
        self.assertTrue(any("jtlicardo/bpmn-assistant" in c for s in plan.steps for c in s.commands))
        self.assertFalse(plan.visibility.get("live_disk_access"))

    def test_summary_pl_mentions_steps(self) -> None:
        citations = [{"guide_title": "BPMN Asystent", "section": "howto", "guide_id": "g1"}]
        context = [
            "[BPMN Asystent / howto]\n"
            "Krok 1: Clone\nKomendy: git clone https://github.com/jtlicardo/bpmn-assistant.git",
        ]
        plan = build_deployment_plan("instalacja", citations, context, focus_guide_title="BPMN Asystent")
        summary = deployment_plan_summary_pl(plan)
        self.assertIn("git clone", summary)


if __name__ == "__main__":
    unittest.main()
