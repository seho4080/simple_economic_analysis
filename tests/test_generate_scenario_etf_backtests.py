from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_scenario_etf_backtests as etf  # noqa: E402


class GenerateScenarioEtfBacktestsTest(unittest.TestCase):
    def test_scenario_allocations_loads_amounts(self) -> None:
        rows = [
            {
                "scenario_slug": "baseline",
                "title": "Baseline",
                "current_regime": "Defensive",
                "cash_amount": "25",
                "gold_amount": "40",
                "silver_amount": "20",
                "equity_amount": "65",
            }
        ]

        scenarios = etf.scenario_allocations(rows)

        self.assertEqual(scenarios[0]["scenario_slug"], "baseline")
        self.assertEqual(scenarios[0]["equity_amount"], 65)

    def test_trade_returns_by_date_groups_asset_returns(self) -> None:
        grouped = etf.trade_returns_by_date(
            [
                {
                    "report_date": "2020-01-06",
                    "asset": "equity",
                    "return": "0.25",
                    "label": "ETF",
                    "symbol": "000000.KS",
                }
            ]
        )

        self.assertEqual(grouped["2020-01-06"]["equity"]["return"], 0.25)
        self.assertEqual(grouped["2020-01-06"]["equity"]["symbol"], "000000.KS")

    def test_simulate_scenario_variant_reuses_reference_returns(self) -> None:
        scenario = {
            "scenario_slug": "baseline",
            "scenario_title": "Baseline",
            "current_regime": "Defensive",
            "cash_amount": 25,
            "gold_amount": 40,
            "silver_amount": 20,
            "equity_amount": 65,
        }
        variant = {
            "variant": "test_variant",
            "title": "Test Variant",
            "valuation_date": "2020-03-06",
            "simple_return": "0.05",
            "xirr": "0.10",
            "cash_symbol": "CASH",
            "gold_symbol": "GOLD",
            "silver_symbol": "SILVER",
            "equity_symbol": "EQUITY",
        }
        trades = []
        for report_date in ["2020-01-06", "2020-02-06"]:
            for asset in ["cash", "gold", "silver", "equity"]:
                trades.append(
                    {
                        "report_date": report_date,
                        "asset": asset,
                        "label": asset,
                        "symbol": asset.upper(),
                        "return": "0.10",
                        "buy_date": report_date,
                        "buy_price_krw": "100",
                        "final_price_krw": "110",
                    }
                )

        summary, lots = etf.simulate_scenario_variant(scenario, variant, trades)

        self.assertEqual(len(lots), 8)
        self.assertEqual(summary["contribution_krw"], 3_000_000)
        self.assertEqual(summary["final_value_krw"], 3_300_000)
        self.assertAlmostEqual(summary["simple_return"], 0.10)
        self.assertEqual(summary["missing_lots"], 0)

    def test_render_html_escapes_text(self) -> None:
        html = etf.render_html(
            [
                {
                    "scenario_slug": "x",
                    "scenario_title": "Bad </script>",
                    "current_regime": "<regime>",
                    "variant": "v",
                    "variant_title": "Variant <x>",
                    "start": "2020-01-06",
                    "end": "2020-02-06",
                    "valuation_date": "2020-03-06",
                    "cash_amount": 25,
                    "gold_amount": 40,
                    "silver_amount": 20,
                    "equity_amount": 65,
                    "cash_symbol": "C",
                    "gold_symbol": "G",
                    "silver_symbol": "S",
                    "equity_symbol": "E",
                    "contribution_krw": 3_000_000,
                    "final_value_krw": 3_300_000,
                    "profit_krw": 300_000,
                    "simple_return": 0.10,
                    "xirr": 0.10,
                    "reference_dynamic_xirr": 0.08,
                    "excess_xirr": 0.02,
                    "missing_lots": 0,
                }
            ],
            "2026-06-21T12:00:00",
        )

        self.assertIn("Bad &lt;/script&gt;", html)
        self.assertIn("Variant &lt;x&gt;", html)


if __name__ == "__main__":
    unittest.main()
