from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_daily_brief as brief  # noqa: E402


class GenerateDailyBriefTest(unittest.TestCase):
    def test_top_alerts_prioritizes_major_severity_and_move_size(self) -> None:
        rows = [
            {"severity": "watch", "pct_change_3m": "100", "item_label": "watch"},
            {"severity": "major", "pct_change_3m": "5", "item_label": "major small"},
            {"severity": "major", "pct_change_3m": "50", "item_label": "major large"},
        ]

        result = brief.top_alerts(rows, limit=2)

        self.assertEqual([row["item_label"] for row in result], ["major large", "major small"])

    def test_action_lines_respond_to_quality_and_major_alerts(self) -> None:
        latest = {"fx_risk": "6.5", "inflation_risk": "5.0", "credit_stress_risk": "2.0"}
        alerts = [{"severity": "major"}, {"severity": "watch"}]
        quality = {"overall_score": "75"}

        lines = brief.action_lines(latest, alerts, quality)

        self.assertTrue(any("Data confidence" in line for line in lines))
        self.assertTrue(any("major change alerts" in line for line in lines))
        self.assertTrue(any("FX risk" in line for line in lines))

    def test_build_report_includes_links_and_allocation(self) -> None:
        risk_rows = [
            {
                "report_date": "2026-05-27",
                "current_regime": "Inflation",
                "fx_risk": "6",
                "cash_amount": "25",
                "gold_amount": "40",
                "silver_amount": "20",
                "equity_amount": "65",
            },
            {
                "report_date": "2026-06-21",
                "current_regime": "Defensive",
                "supporting_regime": "Defensive",
                "fx_risk": "5",
                "cash_amount": "30",
                "gold_amount": "35",
                "silver_amount": "20",
                "equity_amount": "65",
            },
        ]
        quality_rows = [{"scope_type": "overall", "overall_score": "98", "grade": "A"}]

        report, report_date = brief.build_report(risk_rows, [], [], quality_rows)

        self.assertEqual(report_date, "2026-06-21")
        self.assertIn("Sector dashboard", report)
        self.assertIn("Suggested Allocation", report)
        self.assertIn("Data confidence: 98 / 100", report)


if __name__ == "__main__":
    unittest.main()
