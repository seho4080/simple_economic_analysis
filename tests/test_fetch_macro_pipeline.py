from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_macro_pipeline as pipeline  # noqa: E402


class FetchMacroPipelineDerivedTest(unittest.TestCase):
    def spec(self, indicator_id: str, unit: str = "ratio") -> pipeline.SeriesSpec:
        return pipeline.SeriesSpec(
            indicator_id=indicator_id,
            name_ko=indicator_id,
            category="derived",
            country="Global",
            source_type="derived",
            source_series_id=indicator_id,
            unit=unit,
            frequency="daily",
            source="Derived",
        )

    def test_build_ratio_uses_common_dates_and_skips_zero_denominator(self) -> None:
        rows = [
            pipeline.observation(self.spec("left"), "2026-01-01", 10),
            pipeline.observation(self.spec("left"), "2026-01-02", 12),
            pipeline.observation(self.spec("right"), "2026-01-01", 2),
            pipeline.observation(self.spec("right"), "2026-01-02", 0),
        ]

        output = pipeline.build_ratio(rows, "left", "right", self.spec("left_right_ratio"))

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["date"], "2026-01-01")
        self.assertEqual(output[0]["value"], 5.0)

    def test_build_spread_aligned_to_right_uses_prior_left_value(self) -> None:
        rows = [
            pipeline.observation(self.spec("left", "percent"), "2026-01-31", 4.5),
            pipeline.observation(self.spec("left", "percent"), "2026-02-03", 4.7),
            pipeline.observation(self.spec("right", "percent"), "2026-02-01", 2.0),
        ]

        output = pipeline.build_spread_aligned_to_right(
            rows,
            "left",
            "right",
            self.spec("left_right_gap", "percentage_point"),
        )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["date"], "2026-02-01")
        self.assertEqual(output[0]["value"], 2.5)

    def test_build_ratio_aligned_to_numerator_uses_prior_denominator_value(self) -> None:
        rows = [
            pipeline.observation(self.spec("left"), "2026-02-28", 12),
            pipeline.observation(self.spec("right"), "2026-02-01", 3),
            pipeline.observation(self.spec("right"), "2026-03-01", 6),
        ]

        output = pipeline.build_ratio_aligned_to_numerator(
            rows,
            "left",
            "right",
            self.spec("left_right_ratio"),
        )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["date"], "2026-02-28")
        self.assertEqual(output[0]["value"], 4.0)


if __name__ == "__main__":
    unittest.main()
