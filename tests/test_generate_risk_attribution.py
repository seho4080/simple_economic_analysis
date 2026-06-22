from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_risk_attribution as attribution  # noqa: E402


class GenerateRiskAttributionTest(unittest.TestCase):
    def test_pressure_uses_direction_for_risk_interpretation(self) -> None:
        latest = {"report_date": "2026-06-21", "fx_risk": "5.0"}
        previous = {"report_date": "2026-05-27", "fx_risk": "6.0"}
        snapshot_rows = [
            {
                "indicator_id": "usd_krw",
                "category": "fx",
                "latest_date": "2026-06-19",
                "latest_value": "1500",
                "unit": "krw_per_usd",
                "pct_change_3m": "10",
                "pct_change_12m": "20",
                "freshness_status": "ok",
            },
            {
                "indicator_id": "korea_trade_balance",
                "category": "fx",
                "latest_date": "2026-04-01",
                "latest_value": "20000",
                "unit": "million_usd",
                "pct_change_3m": "50",
                "pct_change_12m": "80",
                "freshness_status": "ok",
            },
        ]

        rows = attribution.build_attribution_rows(latest, previous, snapshot_rows, [], [])
        by_id = {row.indicator_id: row for row in rows if row.risk_name == "FX Risk"}

        self.assertEqual(by_id["usd_krw"].pressure, 10)
        self.assertEqual(by_id["korea_trade_balance"].pressure, -50)
        self.assertEqual(by_id["korea_trade_balance"].pressure_label, "risk_down_major")

    def test_alert_severity_is_joined_to_driver_rows(self) -> None:
        latest = {"report_date": "2026-06-21", "market_stress_risk": "2.0"}
        snapshot_rows = [
            {
                "indicator_id": "vix",
                "category": "market_stress",
                "latest_date": "2026-06-19",
                "latest_value": "30",
                "unit": "index",
                "pct_change_3m": "40",
                "pct_change_12m": "20",
                "freshness_status": "ok",
            }
        ]
        alert_rows = [{"item_id": "vix", "severity": "major"}]

        rows = attribution.build_attribution_rows(latest, {}, snapshot_rows, [], alert_rows)

        self.assertEqual(rows[0].indicator_id, "vix")
        self.assertEqual(rows[0].alert_severity, "major")

    def test_build_report_contains_driver_sections(self) -> None:
        latest = {"report_date": "2026-06-21", "current_regime": "Defensive", "fx_risk": "5.0"}
        previous = {"report_date": "2026-05-27", "current_regime": "Inflation", "fx_risk": "6.0"}
        row = attribution.AttributionRow(
            risk_name="FX Risk",
            risk_score=5.0,
            risk_score_delta=-1.0,
            indicator_id="usd_krw",
            indicator_label="USD/KRW",
            category="fx",
            latest_date="2026-06-19",
            latest_value=1500,
            unit="krw_per_usd",
            pct_change_3m=10,
            pct_change_12m=20,
            direction=1,
            pressure=10,
            pressure_label="risk_up",
            freshness_status="ok",
            alert_severity="watch",
        )

        report, report_date = attribution.build_report(latest, previous, [row])

        self.assertEqual(report_date, "2026-06-21")
        self.assertIn("FX Risk", report)
        self.assertIn("USD/KRW", report)
        self.assertIn("Risk-up pressure", report)


if __name__ == "__main__":
    unittest.main()
