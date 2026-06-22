from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_scenario_matrix as matrix  # noqa: E402


class GenerateScenarioMatrixTest(unittest.TestCase):
    def test_load_scenarios_overrides_only_provided_scores(self) -> None:
        baseline = {
            "Inflation Risk": 5.0,
            "Liquidity Bubble Risk": 4.0,
            "Credit Stress Risk": 2.0,
            "FX Risk": 3.0,
            "Climate Supply Shock Risk": 1.0,
            "Growth Slowdown Risk": 4.0,
            "Market Stress Risk": 2.0,
            "Global Rate Divergence Risk": 3.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenarios.csv"
            path.write_text(
                "slug,title,description,inflation_risk,fx_risk\n"
                "shock,Shock,Test scenario,7.5,\n",
                encoding="utf-8",
            )

            scenarios = matrix.load_scenarios(path, baseline)

        self.assertEqual(scenarios[0].scores["Inflation Risk"], 7.5)
        self.assertEqual(scenarios[0].scores["FX Risk"], 3.0)

    def test_portfolio_forward_return_uses_krw_proxy_assets_and_cash(self) -> None:
        series = {
            "usd_krw": [
                matrix.ObservationPoint(date(2020, 1, 1), 1000),
                matrix.ObservationPoint(date(2020, 2, 1), 1100),
            ],
            "korea_short_rate_3m": [matrix.ObservationPoint(date(2020, 1, 1), 12.0)],
            "gold_futures": [
                matrix.ObservationPoint(date(2020, 1, 1), 100),
                matrix.ObservationPoint(date(2020, 2, 1), 110),
            ],
            "silver_futures": [
                matrix.ObservationPoint(date(2020, 1, 1), 50),
                matrix.ObservationPoint(date(2020, 2, 1), 50),
            ],
            "sp500": [
                matrix.ObservationPoint(date(2020, 1, 1), 1000),
                matrix.ObservationPoint(date(2020, 2, 1), 1050),
            ],
        }
        allocation = {"cash": 25, "gold": 40, "silver": 20, "equity": 65}

        result = matrix.portfolio_forward_return(allocation, series, date(2020, 1, 1), 1)

        self.assertIsNotNone(result)
        self.assertGreater(result or 0, 0.10)

    def test_build_outputs_creates_summary_and_analogs(self) -> None:
        baseline = {
            "Inflation Risk": 5.0,
            "Liquidity Bubble Risk": 4.0,
            "Credit Stress Risk": 2.0,
            "FX Risk": 3.0,
            "Climate Supply Shock Risk": 1.0,
            "Growth Slowdown Risk": 4.0,
            "Market Stress Risk": 2.0,
            "Global Rate Divergence Risk": 3.0,
        }
        monthly_rows = [
            {
                "report_date": "2020-01-06",
                "current_regime": "Defensive Waiting Mode",
                "supporting_regime": "Defensive Waiting Mode",
                "inflation_risk": "5",
                "liquidity_bubble_risk": "4",
                "credit_stress_risk": "2",
                "fx_risk": "3",
                "climate_supply_shock_risk": "1",
                "growth_slowdown_risk": "4",
                "market_stress_risk": "2",
                "global_rate_divergence_risk": "3",
                "cash_amount": "25",
                "gold_amount": "40",
                "silver_amount": "20",
                "equity_amount": "65",
            }
        ]
        series = {
            "usd_krw": [
                matrix.ObservationPoint(date(2020, 1, 1), 1000),
                matrix.ObservationPoint(date(2022, 1, 1), 1000),
            ],
            "korea_short_rate_3m": [matrix.ObservationPoint(date(2020, 1, 1), 2.0)],
            "gold_futures": [
                matrix.ObservationPoint(date(2020, 1, 1), 100),
                matrix.ObservationPoint(date(2022, 1, 1), 120),
            ],
            "silver_futures": [
                matrix.ObservationPoint(date(2020, 1, 1), 50),
                matrix.ObservationPoint(date(2022, 1, 1), 55),
            ],
            "sp500": [
                matrix.ObservationPoint(date(2020, 1, 1), 1000),
                matrix.ObservationPoint(date(2022, 1, 1), 1300),
            ],
        }
        scenarios = [matrix.Scenario("baseline", "Baseline", "Test", baseline)]

        summary, analogs = matrix.build_outputs(scenarios, baseline, monthly_rows, series)

        self.assertEqual(summary[0]["scenario_slug"], "baseline")
        self.assertEqual(summary[0]["cash_amount"] + summary[0]["gold_amount"] + summary[0]["silver_amount"] + summary[0]["equity_amount"], 150)
        self.assertEqual(analogs[0]["analog_date"], "2020-01-06")

    def test_render_html_escapes_scenario_text(self) -> None:
        html = matrix.render_html(
            [
                {
                    "scenario_slug": "x",
                    "title": "Bad </script>",
                    "description": "<b>desc</b>",
                    "current_regime": "Regime",
                    "supporting_regime": "Support",
                    "cash_amount": 25,
                    "gold_amount": 40,
                    "silver_amount": 20,
                    "equity_amount": 65,
                    "cash_delta": 0,
                    "gold_delta": 0,
                    "silver_delta": 0,
                    "equity_delta": 0,
                    "nearest_analog_date": "2020-01-06",
                    "nearest_distance": 0.1,
                    "avg_forward_1m": 0.01,
                    "avg_forward_3m": 0.02,
                    "avg_forward_6m": 0.03,
                    "avg_forward_12m": 0.04,
                }
            ],
            [],
            "2026-06-21T12:00:00",
        )

        self.assertIn("Bad &lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;desc&lt;/b&gt;", html)


if __name__ == "__main__":
    unittest.main()
