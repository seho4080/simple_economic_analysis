from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_sector_dashboard as dashboard  # noqa: E402


class GenerateSectorDashboardTest(unittest.TestCase):
    def test_merge_indicator_rows_adds_labels_and_numeric_fields(self) -> None:
        snapshot_rows = [
            {
                "indicator_id": "kospi",
                "category": "market",
                "country": "KR",
                "latest_date": "2026-06-19",
                "latest_value": "2980.5",
                "pct_change_3m": "4.2",
                "pct_change_12m": "-1.5",
                "freshness_status": "ok",
                "source": "Yahoo",
            }
        ]
        dashboard_rows = [{"indicator_id": "kospi", "field_ko": "KOSPI", "status": "ok"}]

        rows = dashboard.merge_indicator_rows(snapshot_rows, dashboard_rows)

        self.assertEqual(rows[0]["label"], "KOSPI")
        self.assertEqual(rows[0]["categoryLabel"], "Market")
        self.assertEqual(rows[0]["latestDisplay"], "2,980")
        self.assertEqual(rows[0]["change3m"], 4.2)
        self.assertEqual(rows[0]["change12mDisplay"], "-1.5%")

    def test_format_number_keeps_small_ratios_readable(self) -> None:
        self.assertEqual(dashboard.format_number(0.001518), "0.0015")

    def test_format_number_preserves_integer_zeroes(self) -> None:
        self.assertEqual(dashboard.format_number(40, 0), "40")

    def test_discover_chart_assets_uses_latest_risk_report_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "reports" / "sector_dashboard.html"
            asset_root = root / "reports" / "assets"
            macro_dir = asset_root / "macro_regime_2026-06-21"
            macro_dir.mkdir(parents=True)
            (macro_dir / "global_market_indices.png").write_bytes(b"png")
            risk_history = root / "risk_score_history.csv"
            risk_history.write_text(
                "report_date,current_regime\n2026-06-21,Defensive Waiting Mode\n",
                encoding="utf-8",
            )

            assets = dashboard.discover_chart_assets(report_path, asset_root, risk_history)

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["title"], "Global equity indexes")
        self.assertEqual(
            assets[0]["path"],
            "assets/macro_regime_2026-06-21/global_market_indices.png",
        )

    def test_render_html_keeps_embedded_json_script_safe(self) -> None:
        data = dashboard.DashboardData(
            generated_at="2026-06-21T12:00:00",
            indicators=[{"label": "KOSPI </script>", "category": "market"}],
            categories=[],
            score_cards=[],
            fetch_health={"total": 0, "counts": {}, "problems": []},
            chart_assets=[],
            alert_summary={"total": 0, "severityCounts": {}, "top": []},
        )

        html = dashboard.render_html(data)

        self.assertIn("KOSPI <\\/script>", html)

    def test_enrich_indicators_adds_detail_path_and_alert_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indicators = [{"id": "kospi", "label": "KOSPI", "category": "market"}]
            enriched = dashboard.enrich_indicators_with_links_and_alerts(
                indicators,
                root / "reports" / "sector_dashboard.html",
                root / "reports" / "indicators",
                {"kospi": [{"severity": "major", "alert_type": "indicator_mover", "detail": "large move"}]},
            )

        self.assertEqual(enriched[0]["detailPath"], "indicators/kospi.html")
        self.assertEqual(enriched[0]["alertSeverity"], "major")
        self.assertEqual(enriched[0]["alertCount"], 1)

    def test_group_recent_observations_keeps_latest_rows(self) -> None:
        rows = [
            {"indicator_id": "kospi", "date": "2026-01-01", "value": "1"},
            {"indicator_id": "kospi", "date": "2026-02-01", "value": "2"},
            {"indicator_id": "kospi", "date": "2026-03-01", "value": "3"},
        ]

        grouped = dashboard.group_recent_observations(rows, limit=2)

        self.assertEqual([item["date"] for item in grouped["kospi"]], ["2026-02-01", "2026-03-01"])


if __name__ == "__main__":
    unittest.main()
