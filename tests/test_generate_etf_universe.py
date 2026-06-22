from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_etf_universe as universe  # noqa: E402


class GenerateEtfUniverseTest(unittest.TestCase):
    def test_load_universe_parses_tags_and_hedge_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.csv"
            path.write_text(
                "sleeve,role,symbol,label,provider,asset_class,region,currency_exposure,hedged,core_rank,risk_tags,regime_fit,notes,source_url\n"
                "equity,core,000000.KS,ETF,Provider,equity,US,USD,yes,2,equity;core;usd,Balanced,Note,https://example.com\n",
                encoding="utf-8",
            )

            candidates = universe.load_universe(path)

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].hedged)
        self.assertEqual(candidates[0].risk_tags, ("equity", "core", "usd"))

    def test_score_candidate_boosts_defensive_assets_in_watch_context(self) -> None:
        context = universe.build_context(
            {
                "action_level": "Confirm before adding risk",
                "risk_posture": "Watch",
                "cash_amount": "40",
                "gold_amount": "30",
                "silver_amount": "10",
                "equity_amount": "70",
            },
            {"credit_stress_risk": "7", "market_stress_risk": "7"},
        )
        cash = universe.EtfCandidate(
            sleeve="cash",
            role="cash",
            symbol="CASH",
            label="Cash ETF",
            provider="Provider",
            asset_class="bond",
            region="Korea",
            currency_exposure="KRW",
            hedged=False,
            core_rank=1,
            risk_tags=("defensive", "cash", "low_vol"),
            regime_fit=("Watch", "Defensive"),
            notes="",
            source_url="",
        )
        high_beta = universe.EtfCandidate(
            sleeve="equity",
            role="growth",
            symbol="BETA",
            label="Beta ETF",
            provider="Provider",
            asset_class="equity",
            region="US",
            currency_exposure="USD",
            hedged=False,
            core_rank=1,
            risk_tags=("equity", "growth", "high_beta", "semiconductor"),
            regime_fit=("Growth",),
            notes="",
            source_url="",
        )

        cash_score, _ = universe.score_candidate(cash, context)
        beta_score, _ = universe.score_candidate(high_beta, context)

        self.assertGreater(cash_score, beta_score)

    def test_rank_candidates_assigns_global_and_sleeve_ranks(self) -> None:
        context = universe.build_context(
            {"risk_posture": "Balanced", "cash_amount": "25", "gold_amount": "40", "silver_amount": "20", "equity_amount": "65"},
            {},
        )
        candidates = [
            universe.EtfCandidate("equity", "core", "A", "A", "P", "equity", "US", "USD", False, 1, ("equity", "core"), ("Balanced",), "", ""),
            universe.EtfCandidate("gold", "gold", "B", "B", "P", "commodity", "Korea", "KRW", False, 1, ("gold",), ("Balanced",), "", ""),
        ]

        rows = universe.rank_candidates(candidates, context)

        self.assertEqual(rows[0]["global_rank"], 1)
        self.assertEqual(rows[0]["sleeve_rank"], 1)
        self.assertEqual(rows[1]["sleeve_rank"], 1)

    def test_render_html_escapes_payload_context(self) -> None:
        context = universe.build_context(
            {"action_level": "Act </script>", "risk_posture": "<Watch>", "cash_amount": "1"},
            {},
        )

        html = universe.render_html(context, [])

        self.assertIn("Act &lt;/script&gt;", html)
        self.assertIn("<\\/script>", html)


if __name__ == "__main__":
    unittest.main()
