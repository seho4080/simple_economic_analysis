from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_data_quality_report as quality  # noqa: E402


class GenerateDataQualityReportTest(unittest.TestCase):
    def test_freshness_score_gives_partial_credit_for_stale_rows(self) -> None:
        rows = [
            {"freshness_status": "ok"},
            {"freshness_status": "ok"},
            {"freshness_status": "stale"},
        ]

        self.assertAlmostEqual(quality.freshness_score(rows), 78.3)

    def test_coverage_score_uses_driver_count_and_ok_share(self) -> None:
        rows = [
            {"risk_name": "FX Risk", "indicator_id": "usd_krw", "freshness_status": "ok"},
            {"risk_name": "FX Risk", "indicator_id": "dxy", "freshness_status": "ok"},
            {"risk_name": "FX Risk", "indicator_id": "trade", "freshness_status": "stale"},
            {"risk_name": "FX Risk", "indicator_id": "flows", "freshness_status": "ok"},
            {"risk_name": "FX Risk", "indicator_id": "gap", "freshness_status": "ok"},
        ]

        self.assertAlmostEqual(quality.coverage_score(rows), 91.0)

    def test_build_quality_rows_includes_overall_category_and_risk_scopes(self) -> None:
        snapshot_rows = [
            {"indicator_id": "usd_krw", "category": "fx", "freshness_status": "ok"},
            {"indicator_id": "dxy", "category": "fx", "freshness_status": "stale"},
        ]
        fetch_rows = [
            {"indicator_id": "usd_krw", "status": "ok"},
            {"indicator_id": "dxy", "status": "ok"},
        ]
        attribution_rows = [
            {"risk_name": "FX Risk", "indicator_id": "usd_krw", "freshness_status": "ok"},
            {"risk_name": "FX Risk", "indicator_id": "dxy", "freshness_status": "stale"},
        ]

        rows = quality.build_quality_rows(snapshot_rows, fetch_rows, attribution_rows)
        scopes = {(row["scope_type"], row["scope"]) for row in rows}

        self.assertIn(("overall", "macro_pipeline"), scopes)
        self.assertIn(("category", "fx"), scopes)
        self.assertIn(("risk", "FX Risk"), scopes)

    def test_category_scope_without_fetch_rows_is_not_penalized_as_failed_fetch(self) -> None:
        row = quality.build_scope_row(
            "category",
            "derived",
            [{"indicator_id": "ratio", "freshness_status": "ok"}],
            [],
            [],
        )

        self.assertEqual(row["fetch_score"], 100.0)
        self.assertEqual(row["coverage_score"], 100.0)
        self.assertEqual(row["grade"], "A")


if __name__ == "__main__":
    unittest.main()
