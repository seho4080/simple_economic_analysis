from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import portfolio_input_server as server  # noqa: E402


class PortfolioInputServerTest(unittest.TestCase):
    def test_save_rows_normalizes_and_autocalculates_market_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.csv"
            path.write_text(
                "account,asset,symbol,label,shares,price_krw,market_value_krw,notes\n"
                "isa,equity,133690.KS,TIGER 미국나스닥100,0,,0,\n",
                encoding="utf-8",
            )
            form = parse_qs(
                "equity_account=isa&equity_symbol=133690.KS&equity_label=TIGER+미국나스닥100"
                "&equity_shares=3.5&equity_price_krw=10000&equity_market_value_krw=0&equity_notes=memo",
                keep_blank_values=True,
            )

            rows = server.save_rows(path, form)

        equity = next(row for row in rows if row["asset"] == "equity")
        self.assertEqual(equity["shares"], "3.5")
        self.assertEqual(equity["market_value_krw"], "35000")

    def test_render_page_contains_form_and_rows(self) -> None:
        html = server.render_page(
            [
                {
                    "account": "isa",
                    "asset": "equity",
                    "symbol": "133690.KS",
                    "label": "TIGER 미국나스닥100",
                    "shares": "3",
                    "price_krw": "10000",
                    "market_value_krw": "30000",
                    "notes": "",
                }
            ],
            message="Saved",
        ).decode("utf-8")

        self.assertIn("Portfolio Holdings Input", html)
        self.assertIn("Save and Rebuild", html)
        self.assertIn("TIGER 미국나스닥100", html)
        self.assertIn("Saved", html)


if __name__ == "__main__":
    unittest.main()
