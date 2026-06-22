from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_rebalance_orders as rebalance  # noqa: E402


class GenerateRebalanceOrdersTest(unittest.TestCase):
    def test_selected_variant_uses_recommended_baseline_variant(self) -> None:
        decision = {"recommended_variant": "best"}
        rows = [
            {"scenario_slug": "baseline", "variant": "other", "equity_symbol": "A"},
            {"scenario_slug": "baseline", "variant": "best", "equity_symbol": "B"},
        ]

        result = rebalance.selected_variant(decision, rows)

        self.assertEqual(result["equity_symbol"], "B")

    def test_load_holdings_calculates_value_from_shares_and_price(self) -> None:
        rows = [{"asset": "equity", "symbol": "133690.KS", "label": "ETF", "shares": "10", "price_krw": "20000"}]
        holdings = rebalance.load_holdings(rows, {"equity": "133690.KS"})

        self.assertEqual(holdings["equity"]["market_value_krw"], 200000)
        self.assertEqual(holdings["equity"]["price_krw"], 20000)

    def test_build_targets_and_orders_defaults_to_monthly_allocation_when_empty(self) -> None:
        decision = {
            "cash_amount": "25",
            "gold_amount": "40",
            "silver_amount": "20",
            "equity_amount": "65",
            "recommended_variant": "v",
        }
        variant = {
            "cash_symbol": "153130.KS",
            "gold_symbol": "411060.KS",
            "silver_symbol": "144600.KS",
            "equity_symbol": "133690.KS",
        }

        targets, orders, summary = rebalance.build_targets_and_orders(decision, variant, [], 1_500_000, 50_000)

        self.assertEqual(sum(row["estimated_order_value_krw"] for row in orders), 1_500_000)
        self.assertEqual({row["asset"]: row["order_budget_krw"] for row in orders}["equity"], 650000)
        self.assertEqual(summary["unallocated_cash_krw"], 0)
        self.assertEqual(len(targets), 4)

    def test_build_targets_and_orders_calculates_estimated_units_when_price_exists(self) -> None:
        decision = {"cash_amount": "0", "gold_amount": "0", "silver_amount": "0", "equity_amount": "150"}
        variant = {"equity_symbol": "133690.KS"}
        holdings = [{"asset": "equity", "symbol": "133690.KS", "shares": "0", "price_krw": "123000", "market_value_krw": "0"}]

        _targets, orders, _summary = rebalance.build_targets_and_orders(decision, variant, holdings, 500_000, 50_000)

        equity_order = next(row for row in orders if row["asset"] == "equity")
        self.assertEqual(equity_order["estimated_units"], 4)
        self.assertEqual(equity_order["estimated_order_value_krw"], 492000)

    def test_render_html_escapes_decision_text(self) -> None:
        summary = {
            "generated_at": "2026-06-21T12:00:00",
            "report_date": "2026-06-21",
            "action_level": "Act </script>",
            "recommended_variant_title": "Variant <x>",
            "monthly_contribution_krw": 1_500_000,
            "unallocated_cash_krw": 0,
        }

        html = rebalance.render_html(summary, [], [])

        self.assertIn("Act &lt;/script&gt;", html)
        self.assertIn("Variant &lt;x&gt;", html)


if __name__ == "__main__":
    unittest.main()
