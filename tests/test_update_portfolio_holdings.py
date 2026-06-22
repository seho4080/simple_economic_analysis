from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import update_portfolio_holdings as updater  # noqa: E402


class UpdatePortfolioHoldingsTest(unittest.TestCase):
    def test_calculated_market_value_uses_shares_and_price(self) -> None:
        self.assertEqual(updater.calculated_market_value("3.5", "10000"), "35000")

    def test_merge_defaults_keeps_existing_values_and_fills_missing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decision = root / "decision.csv"
            scenario_etf = root / "scenario_etf.csv"
            decision.write_text(
                "recommended_variant\nbest\n",
                encoding="utf-8",
            )
            scenario_etf.write_text(
                "scenario_slug,variant,cash_symbol,gold_symbol,silver_symbol,equity_symbol\n"
                "baseline,best,153130.KS,411060.KS,144600.KS,133690.KS\n",
                encoding="utf-8",
            )

            rows = updater.merge_defaults(
                [{"account": "isa", "asset": "equity", "symbol": "133690.KS", "shares": "7"}],
                decision,
                scenario_etf,
            )

        self.assertEqual(len(rows), 4)
        equity = next(row for row in rows if row["asset"] == "equity")
        self.assertEqual(equity["shares"], "7")
        self.assertEqual(equity["label"], "TIGER 미국나스닥100")

    def test_interactive_update_accepts_enter_to_keep_existing_values(self) -> None:
        rows = [
            {
                "account": "isa",
                "asset": "equity",
                "symbol": "133690.KS",
                "label": "TIGER 미국나스닥100",
                "shares": "10",
                "price_krw": "10000",
                "market_value_krw": "",
                "notes": "memo",
            }
        ]
        answers = iter(["", "", "", "", "", "", ""])

        with redirect_stdout(io.StringIO()):
            updated = updater.interactive_update(rows, prompt=lambda _message: next(answers))

        self.assertEqual(updated[0]["shares"], "10")
        self.assertEqual(updated[0]["market_value_krw"], "100000")

    def test_interactive_update_autocalculates_market_value_when_current_zero(self) -> None:
        rows = [
            {
                "account": "isa",
                "asset": "equity",
                "symbol": "133690.KS",
                "label": "TIGER 미국나스닥100",
                "shares": "10",
                "price_krw": "10000",
                "market_value_krw": "0",
                "notes": "memo",
            }
        ]
        answers = iter(["", "", "", "", "", "", ""])

        with redirect_stdout(io.StringIO()):
            updated = updater.interactive_update(rows, prompt=lambda _message: next(answers))

        self.assertEqual(updated[0]["market_value_krw"], "100000")

    def test_write_and_read_csv_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.csv"
            rows = [
                {
                    "account": "isa",
                    "asset": "cash",
                    "symbol": "153130.KS",
                    "label": "KODEX 단기채권",
                    "shares": "1",
                    "price_krw": "100000",
                    "market_value_krw": "100000",
                    "notes": "",
                }
            ]

            updater.write_csv(path, rows)
            loaded = updater.read_csv(path)

        self.assertEqual(loaded[0]["asset"], "cash")
        self.assertEqual(loaded[0]["market_value_krw"], "100000")


if __name__ == "__main__":
    unittest.main()
