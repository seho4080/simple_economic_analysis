from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_stock_watchlist as watchlist  # noqa: E402


class GenerateStockWatchlistTest(unittest.TestCase):
    def test_load_watchlist_parses_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stocks.csv"
            path.write_text(
                "watch_rank,symbol,label,company_name,market,country,sector,industry,style,risk_tags,macro_fit,watch_reason,source_url\n"
                "1,MSFT,Microsoft,Microsoft,NASDAQ,United States,Technology,Software,quality,quality;cloud;ai,Balanced,Reason,https://example.com\n",
                encoding="utf-8",
            )

            candidates = watchlist.load_watchlist(path)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].risk_tags, ("quality", "cloud", "ai"))
        self.assertEqual(candidates[0].watch_rank, 1)

    def test_score_candidate_prefers_defensive_stock_in_watch_context(self) -> None:
        context = watchlist.build_context(
            {"action_level": "Confirm before adding risk", "risk_posture": "Watch"},
            {"market_stress_risk": "7"},
        )
        defensive = watchlist.StockCandidate(
            1,
            "KO",
            "Coca-Cola",
            "The Coca-Cola Company",
            "NYSE",
            "United States",
            "Consumer Staples",
            "Beverages",
            "defensive",
            ("consumer_staples", "defensive", "dividend", "quality"),
            ("Defensive", "Watch"),
            "",
            "",
        )
        high_beta = watchlist.StockCandidate(
            1,
            "AMD",
            "AMD",
            "Advanced Micro Devices",
            "NASDAQ",
            "United States",
            "Information Technology",
            "Semiconductors",
            "growth",
            ("semiconductor", "high_beta", "growth"),
            ("Growth",),
            "",
            "",
        )

        defensive_score, _ = watchlist.score_candidate(defensive, context)
        high_beta_score, _ = watchlist.score_candidate(high_beta, context)

        self.assertGreater(defensive_score, high_beta_score)

    def test_rank_candidates_sorts_by_score(self) -> None:
        context = watchlist.build_context({"risk_posture": "Balanced"}, {})
        candidates = [
            watchlist.StockCandidate(2, "B", "B", "B", "X", "US", "Tech", "Semis", "growth", ("high_beta",), ("Growth",), "", ""),
            watchlist.StockCandidate(1, "A", "A", "A", "X", "US", "Staples", "Beverages", "defensive", ("quality", "dividend"), ("Balanced",), "", ""),
        ]

        rows = watchlist.rank_candidates(candidates, context)

        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["symbol"], "A")

    def test_parse_stock_price_payload_calculates_change(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {"currency": "USD"},
                        "timestamp": [1704067200, 1704153600],
                        "indicators": {"quote": [{"close": [100.0, 105.0]}]},
                    }
                ],
                "error": None,
            }
        }

        price = watchlist.parse_stock_price_payload("ABC", payload, "https://example.com", "2026-06-22T10:00:00")

        self.assertEqual(price.status, "ok")
        self.assertEqual(price.latest_price, 105.0)
        self.assertEqual(price.previous_close, 100.0)
        self.assertAlmostEqual(price.price_change_pct or 0, 0.05)
        self.assertEqual(price.history_rows, 2)
        self.assertEqual(price.history_start, "2024-01-01")

    def test_parse_stock_price_payload_calculates_trailing_return_and_drawdown(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {"currency": "USD"},
                        "timestamp": [1577836800, 1704067200, 1704153600],
                        "indicators": {"quote": [{"close": [50.0, 100.0, 90.0]}]},
                    }
                ],
                "error": None,
            }
        }

        price = watchlist.parse_stock_price_payload("ABC", payload, "https://example.com", "2026-06-22T10:00:00")

        self.assertAlmostEqual(price.return_3y or 0, 0.8)
        self.assertAlmostEqual(price.max_drawdown or 0, -0.1)

    def test_history_rows_from_payload_flattens_prices(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {"currency": "USD"},
                        "timestamp": [1704067200],
                        "indicators": {"quote": [{"close": [100.0]}]},
                    }
                ],
                "error": None,
            }
        }

        rows = watchlist.history_rows_from_payload("ABC", payload, "2026-06-22T10:00:00", "https://example.com")

        self.assertEqual(rows, [{"symbol": "ABC", "date": "2024-01-01", "close": 100.0, "currency": "USD", "fetched_at": "2026-06-22T10:00:00", "source_url": "https://example.com"}])

    def test_rank_candidates_merges_price_rows(self) -> None:
        context = watchlist.build_context({"risk_posture": "Balanced"}, {})
        candidates = [
            watchlist.StockCandidate(1, "A", "A", "A", "X", "US", "Staples", "Beverages", "defensive", ("quality", "dividend"), ("Balanced",), "", ""),
        ]
        prices = {
            "A": {
                "status": "ok",
                "currency": "USD",
                "latest_date": "2026-06-22",
                "latest_price": "105",
                "previous_close": "100",
                "price_change": "5",
                "price_change_pct": "0.05",
                "return_1y": "0.12",
            }
        }

        rows = watchlist.rank_candidates(candidates, context, prices)

        self.assertEqual(rows[0]["latest_price"], "105")
        self.assertEqual(rows[0]["price_change_pct"], "0.05")
        self.assertEqual(rows[0]["return_1y"], "0.12")

    def test_render_html_escapes_card_text_and_json(self) -> None:
        context = watchlist.build_context({"action_level": "Act </script>", "risk_posture": "<Watch>"}, {})

        html = watchlist.render_html(context, [])

        self.assertIn("Act &lt;/script&gt;", html)
        self.assertIn("<\\/script>", html)


if __name__ == "__main__":
    unittest.main()
