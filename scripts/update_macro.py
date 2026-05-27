#!/usr/bin/env python3
"""One-command macro data refresh and report generation."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import analyze_macro_regime
import fetch_macro_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch all macro datasets and generate the regime report."
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Base data directory. Defaults to ./data.",
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory for generated markdown reports. Defaults to ./reports.",
    )
    parser.add_argument(
        "--report-date",
        default=date.today().isoformat(),
        help="Report date used in the output filename and footer.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Only fetch data; do not generate the markdown report.",
    )
    parser.add_argument(
        "--bok-source",
        default="auto",
        choices=["auto", "ecos", "homepage-events"],
        help="BOK policy-rate source. Defaults to auto.",
    )
    parser.add_argument(
        "--bok-key",
        default=None,
        help="Bank of Korea ECOS API key. Defaults to BOK_API_KEY or sample.",
    )
    parser.add_argument(
        "--ecos-page-delay",
        type=float,
        default=0.2,
        help="Delay between ECOS sample-key page calls. Defaults to 0.2 seconds.",
    )
    parser.add_argument(
        "--target-end",
        default=None,
        help="End date for daily-expanded policy-rate series. Defaults to today.",
    )
    parser.add_argument(
        "--yahoo-range",
        default="max",
        help="Yahoo chart range, e.g. 5y, 10y, max. Defaults to max.",
    )
    parser.add_argument("--skip-rates", action="store_true", help="Skip BOK/Fed rate refresh.")
    parser.add_argument("--skip-ecos", action="store_true", help="Skip Bank of Korea ECOS series fetches.")
    parser.add_argument("--skip-bok-key", action="store_true", help="Skip Bank of Korea KeyStatisticList fetch.")
    parser.add_argument("--skip-fred", action="store_true", help="Skip FRED source fetches.")
    parser.add_argument("--skip-yahoo", action="store_true", help="Skip Yahoo Finance source fetches.")
    parser.add_argument("--skip-climate", action="store_true", help="Skip GDACS climate/natural hazard RSS.")
    return parser


def build_fetch_args(args: argparse.Namespace) -> argparse.Namespace:
    fetch_args = [
        "--output-dir",
        args.output_dir,
        "--bok-source",
        args.bok_source,
        "--ecos-page-delay",
        str(args.ecos_page_delay),
        "--yahoo-range",
        args.yahoo_range,
    ]
    optional_pairs = [
        ("--bok-key", args.bok_key),
        ("--target-end", args.target_end),
    ]
    for flag, value in optional_pairs:
        if value:
            fetch_args.extend([flag, value])
    for flag in [
        "skip_rates",
        "skip_ecos",
        "skip_bok_key",
        "skip_fred",
        "skip_yahoo",
        "skip_climate",
    ]:
        if getattr(args, flag):
            fetch_args.append("--" + flag.replace("_", "-"))
    return fetch_macro_pipeline.build_parser().parse_args(fetch_args)


def generate_report(output_dir: Path, report_dir: Path, report_date: str) -> tuple[Path, dict[str, float]]:
    snapshot_path = output_dir / "processed" / "macro" / "latest_snapshot.csv"
    metrics = analyze_macro_regime.load_metrics(snapshot_path)
    scores = analyze_macro_regime.calc_scores(metrics)
    report = analyze_macro_regime.build_report(metrics, scores, report_date)
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"macro_regime_{report_date}.md"
    output_path.write_text(report, encoding="utf-8")
    return output_path, scores


def main() -> int:
    args = build_parser().parse_args()
    try:
        print("[1/2] Fetching macro datasets...")
        counts = fetch_macro_pipeline.run(build_fetch_args(args))
        print(f"  Observations: {counts['observations']}")
        print(f"  Latest snapshot rows: {counts['snapshot']}")
        print(f"  Requested dashboard rows: {counts['dashboard']}")
        print(f"  Fetch status rows: {counts['fetch_status']}")

        if args.no_report:
            print("Done. Report generation skipped.")
            return 0

        print("[2/2] Generating macro regime report...")
        report_path, scores = generate_report(
            Path(args.output_dir),
            Path(args.report_dir),
            args.report_date,
        )
        print(f"  Report: {report_path}")
        for name, score in scores.items():
            print(f"  {name}: {score}/10")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
