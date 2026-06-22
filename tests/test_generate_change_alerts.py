from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_change_alerts as alerts  # noqa: E402


class GenerateChangeAlertsTest(unittest.TestCase):
    def test_build_risk_changes_marks_major_moves(self) -> None:
        latest = {
            "inflation_risk": "6.2",
            "fx_risk": "4.1",
        }
        previous = {
            "inflation_risk": "5.0",
            "fx_risk": "4.0",
        }

        changes = alerts.build_risk_changes(latest, previous, warn_threshold=0.7, major_threshold=1.0)
        by_field = {item.field: item for item in changes}

        self.assertEqual(by_field["inflation_risk"].severity, "major")
        self.assertAlmostEqual(by_field["inflation_risk"].delta or 0, 1.2)
        self.assertEqual(by_field["fx_risk"].severity, "info")

    def test_build_indicator_moves_excludes_stale_by_default(self) -> None:
        snapshot_rows = [
            {
                "indicator_id": "kospi",
                "name_ko": "KOSPI",
                "category": "market",
                "latest_date": "2026-06-19",
                "latest_value": "3000",
                "unit": "index",
                "pct_change_3m": "20",
                "pct_change_12m": "30",
                "freshness_status": "ok",
                "source": "Yahoo",
            },
            {
                "indicator_id": "old_cpi",
                "name_ko": "Old CPI",
                "category": "inflation",
                "latest_date": "2020-01-01",
                "latest_value": "100",
                "unit": "index",
                "pct_change_3m": "80",
                "pct_change_12m": "100",
                "freshness_status": "stale",
                "source": "FRED",
            },
        ]

        moves = alerts.build_indicator_moves(
            snapshot_rows,
            labels={},
            pct_threshold=15,
            major_pct_threshold=30,
            include_stale=False,
            limit=10,
        )

        self.assertEqual([item.indicator_id for item in moves], ["kospi"])

    def test_fmt_num_preserves_integer_zeroes(self) -> None:
        self.assertEqual(alerts.fmt_num(40, 0), "40")

    def test_build_report_emits_regime_and_alert_rows(self) -> None:
        risk_rows = [
            {
                "report_date": "2026-05-27",
                "current_regime": "Inflation Rebound",
                "inflation_risk": "5.0",
                "cash_amount": "25",
                "gold_amount": "40",
                "silver_amount": "20",
                "equity_amount": "65",
            },
            {
                "report_date": "2026-06-21",
                "current_regime": "Defensive Waiting Mode",
                "inflation_risk": "6.2",
                "cash_amount": "30",
                "gold_amount": "35",
                "silver_amount": "20",
                "equity_amount": "65",
            },
        ]
        snapshot_rows = [
            {
                "indicator_id": "kospi",
                "name_ko": "KOSPI",
                "category": "market",
                "latest_date": "2026-06-19",
                "latest_value": "3000",
                "unit": "index",
                "pct_change_3m": "20",
                "pct_change_12m": "30",
                "freshness_status": "ok",
                "source": "Yahoo",
            }
        ]

        report, rows, report_date = alerts.build_report(
            risk_rows,
            snapshot_rows,
            dashboard_rows=[],
            score_warn_threshold=0.7,
            score_major_threshold=1.0,
            pct_threshold=15,
            major_pct_threshold=30,
            include_stale=False,
            indicator_limit=10,
            watchlist_threshold=8,
        )

        self.assertEqual(report_date, "2026-06-21")
        self.assertIn("Regime changed", report)
        self.assertIn("Inflation Risk", report)
        self.assertIn("KOSPI", report)
        self.assertTrue(any(row["alert_type"] == "regime_change" for row in rows))
        self.assertTrue(any(row["item_id"] == "inflation_risk" for row in rows))


if __name__ == "__main__":
    unittest.main()
