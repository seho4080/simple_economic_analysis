from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze_macro_regime as regime  # noqa: E402


def metric(value: float, pct_3m: float | None = None) -> regime.Metric:
    return regime.Metric(
        indicator_id="test",
        latest_value=value,
        latest_date="2026-06-01",
        age_days=0,
        unit="",
        change_1_obs=None,
        pct_change_3m=pct_3m,
        pct_change_6m=None,
        pct_change_12m=None,
        freshness_status="ok",
        source="test",
    )


class AnalyzeMacroRegimeSupplementalTest(unittest.TestCase):
    def test_market_stress_score_rises_with_stress_inputs(self) -> None:
        calm = {
            "vix": metric(13),
            "kospi_vs_sp500": metric(1.0, 4),
            "sox_vs_sp500": metric(1.0, 6),
            "russell_2000": metric(2000, 5),
            "copper_gold_ratio": metric(0.0015, 5),
        }
        stressed = {
            "vix": metric(35),
            "kospi_vs_sp500": metric(1.0, -15),
            "sox_vs_sp500": metric(1.0, -12),
            "russell_2000": metric(2000, -12),
            "copper_gold_ratio": metric(0.0015, -12),
        }

        self.assertGreater(
            regime.calc_market_stress_risk(stressed),
            regime.calc_market_stress_risk(calm),
        )

    def test_global_rate_divergence_score_rises_with_wide_gaps(self) -> None:
        low_pressure = {
            "us_japan_10y_gap": metric(0.5),
            "us_germany_10y_gap": metric(0.2),
            "us_korea_10y_gap": metric(-0.2),
            "us_treasury_10y": metric(2.0),
            "germany_gov_bond_10y": metric(1.5),
            "uk_gov_bond_10y": metric(2.0),
            "canada_gov_bond_10y": metric(2.0),
            "australia_gov_bond_10y": metric(2.5),
        }
        high_pressure = {
            "us_japan_10y_gap": metric(3.8),
            "us_germany_10y_gap": metric(3.0),
            "us_korea_10y_gap": metric(1.5),
            "us_treasury_10y": metric(5.0),
            "germany_gov_bond_10y": metric(4.0),
            "uk_gov_bond_10y": metric(5.0),
            "canada_gov_bond_10y": metric(4.5),
            "australia_gov_bond_10y": metric(4.8),
        }

        self.assertGreater(
            regime.calc_global_rate_divergence_risk(high_pressure),
            regime.calc_global_rate_divergence_risk(low_pressure),
        )


if __name__ == "__main__":
    unittest.main()
