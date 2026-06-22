from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from variant_config import read_variant_config  # noqa: E402


@dataclass(frozen=True)
class Variant:
    slug: str
    title: str
    start: str
    end: str
    cash_symbol: str
    cash_label: str
    gold_symbol: str
    gold_label: str
    silver_symbol: str
    silver_label: str
    equity_symbol: str
    equity_label: str
    note: str


HEADER = (
    "slug,title,start,end,cash_symbol,cash_label,gold_symbol,gold_label,"
    "silver_symbol,silver_label,equity_symbol,equity_label,note\n"
)


class VariantConfigTest(unittest.TestCase):
    def write_config(self, text: str) -> Path:
        path = Path(self.tmpdir.name) / "variants.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_reads_variants_and_defaults_latest_end(self) -> None:
        path = self.write_config(
            HEADER
            + "demo,Demo,2022-01-06,latest,153130.KS,Cash,411060.KS,Gold,"
            + "144600.KS,Silver,360750.KS,Equity,Example\n"
        )

        variants = read_variant_config(path, Variant, "2026-06-06")

        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].slug, "demo")
        self.assertEqual(variants[0].end, "2026-06-06")

    def test_rejects_missing_required_field(self) -> None:
        path = self.write_config(
            HEADER
            + "demo,Demo,2022-01-06,latest,153130.KS,Cash,411060.KS,Gold,"
            + "144600.KS,Silver,,Equity,Example\n"
        )

        with self.assertRaisesRegex(ValueError, "missing required fields: equity_symbol"):
            read_variant_config(path, Variant, "2026-06-06")

    def test_rejects_duplicate_slug(self) -> None:
        row = (
            "demo,Demo,2022-01-06,latest,153130.KS,Cash,411060.KS,Gold,"
            "144600.KS,Silver,360750.KS,Equity,Example\n"
        )
        path = self.write_config(HEADER + row + row)

        with self.assertRaisesRegex(ValueError, "duplicate slug: demo"):
            read_variant_config(path, Variant, "2026-06-06")

    def test_rejects_invalid_slug(self) -> None:
        path = self.write_config(
            HEADER
            + "../demo,Demo,2022-01-06,latest,153130.KS,Cash,411060.KS,Gold,"
            + "144600.KS,Silver,360750.KS,Equity,Example\n"
        )

        with self.assertRaisesRegex(ValueError, "slug must use"):
            read_variant_config(path, Variant, "2026-06-06")


if __name__ == "__main__":
    unittest.main()
