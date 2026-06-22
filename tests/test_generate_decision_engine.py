from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_decision_engine as engine  # noqa: E402


class GenerateDecisionEngineTest(unittest.TestCase):
    def test_policy_pauses_when_quality_is_low(self) -> None:
        latest = {
            "inflation_risk": "4",
            "fx_risk": "4",
            "credit_stress_risk": "2",
            "growth_slowdown_risk": "3",
            "market_stress_risk": "2",
        }

        policy = engine.policy_from_inputs(latest, [], {"overall_score": "70", "grade": "C"})

        self.assertEqual(policy["action_level"], "Review only")
        self.assertEqual(policy["risk_posture"], "Data constrained")

    def test_policy_flags_confirm_when_regime_changed(self) -> None:
        latest = {
            "inflation_risk": "4",
            "fx_risk": "4",
            "credit_stress_risk": "2",
            "growth_slowdown_risk": "3",
            "market_stress_risk": "2",
        }
        alerts = [{"severity": "major", "alert_type": "regime_change"}]

        policy = engine.policy_from_inputs(latest, alerts, {"overall_score": "98", "grade": "A"})

        self.assertEqual(policy["action_level"], "Confirm before adding risk")
        self.assertTrue(policy["regime_changed"])

    def test_select_best_etf_rows_ranks_baseline_by_xirr(self) -> None:
        rows = [
            {"scenario_slug": "baseline", "variant": "a", "xirr": "0.10", "excess_xirr": "0.02", "simple_return": "0.2", "missing_lots": "0"},
            {"scenario_slug": "baseline", "variant": "b", "xirr": "0.20", "excess_xirr": "0.01", "simple_return": "0.1", "missing_lots": "0"},
            {"scenario_slug": "credit", "variant": "c", "xirr": "0.30", "excess_xirr": "0.05", "simple_return": "0.4", "missing_lots": "0"},
        ]

        best = engine.select_best_etf_rows(rows)

        self.assertEqual(best[0]["variant"], "b")

    def test_build_actions_includes_allocation_and_etf_candidate(self) -> None:
        latest = {"cash_amount": "25", "gold_amount": "40", "silver_amount": "20", "equity_amount": "65"}
        policy = {"action_level": "Proceed", "major_alerts": 0, "quality_score": 98.0, "quality_grade": "A"}
        etfs = [{"variant_title": "ETF", "xirr": "0.2", "excess_xirr": "0.01"}]
        context = {"downside_stress": {"title": "Shock", "worst_forward_3m": "-0.1"}}

        actions = engine.build_actions(latest, policy, etfs, context, [])

        self.assertIn("cash 25m", actions[0]["detail"])
        self.assertTrue(any(action["title"] == "Implementation candidate" for action in actions))

    def test_render_html_escapes_text(self) -> None:
        summary = {
            "generated_at": "2026-06-21T12:00:00",
            "report_date": "2026-06-21",
            "action_level": "Act </script>",
            "risk_posture": "Watch",
            "decision_confidence": "High",
            "quality_score": 98.0,
            "current_regime": "<regime>",
            "downside_stress_scenario": "Shock",
            "downside_stress_3m_worst": -0.1,
            "cash_amount": 25,
            "gold_amount": 40,
            "silver_amount": 20,
            "equity_amount": 65,
        }

        html = engine.render_html(summary, [], [], [])

        self.assertIn("Act &lt;/script&gt;", html)
        self.assertIn("&lt;regime&gt;", html)


if __name__ == "__main__":
    unittest.main()
