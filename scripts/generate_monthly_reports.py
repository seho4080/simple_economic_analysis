#!/usr/bin/env python3
"""Generate one macro regime report per month from historical observations."""

from __future__ import annotations

import argparse
import calendar
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

import analyze_macro_regime
from date_defaults import latest_report_month
from fetch_macro_pipeline import SNAPSHOT_FIELDS, add_months, delta, find_on_or_before, pct_change


FRESHNESS_THRESHOLDS_DAYS = {
    "daily": 14,
    "weekly": 35,
    "monthly": 120,
    "quarterly": 210,
    "annual": 550,
    "snapshot": 7,
    "event": 365,
    "daily_or_monthly": 120,
}


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Month must use YYYY-MM format.") from exc
    if month < 1 or month > 12:
        raise argparse.ArgumentTypeError("Month must be between 01 and 12.")
    return year, month


def report_day_for_month(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def iter_report_dates(start: str, end: str, day: int) -> list[date]:
    start_year, start_month = parse_month(start)
    end_year, end_month = parse_month(end)
    current_year, current_month = start_year, start_month
    dates: list[date] = []
    while (current_year, current_month) <= (end_year, end_month):
        dates.append(report_day_for_month(current_year, current_month, day))
        current_month += 1
        if current_month == 13:
            current_year += 1
            current_month = 1
    return dates


def read_observations(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            value = analyze_macro_regime.parse_float(row.get("value"))
            if value is None:
                continue
            try:
                obs_date = date.fromisoformat(row.get("date", ""))
            except ValueError:
                continue
            row["_date"] = obs_date
            row["_value"] = value
            rows.append(row)
    return rows


def freshness_status(latest_date: date, frequency: str, as_of: date) -> tuple[int, str]:
    age_days = max((as_of - latest_date).days, 0)
    threshold = FRESHNESS_THRESHOLDS_DAYS.get(frequency, 120)
    return age_days, "ok" if age_days <= threshold else "stale"


def build_snapshot_as_of(rows: list[dict], as_of: date) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["_date"] <= as_of:
            grouped[row["indicator_id"]].append(row)

    snapshot: list[dict] = []
    for indicator_id, group in sorted(grouped.items()):
        points = sorted((row["_date"], row["_value"], row) for row in group)
        if not points:
            continue
        latest_date, latest_value, latest_row = points[-1]
        previous = points[-2] if len(points) >= 2 else None
        compact_points = [(obs_date, value) for obs_date, value, _ in points]
        age_days, fresh_status = freshness_status(
            latest_date,
            latest_row.get("frequency", ""),
            as_of,
        )

        output = {
            "indicator_id": indicator_id,
            "name_ko": latest_row.get("name_ko", ""),
            "category": latest_row.get("category", ""),
            "country": latest_row.get("country", ""),
            "latest_date": latest_date.isoformat(),
            "latest_value": latest_value,
            "age_days": age_days,
            "freshness_status": fresh_status,
            "unit": latest_row.get("unit", ""),
            "frequency": latest_row.get("frequency", ""),
            "previous_date": previous[0].isoformat() if previous else "",
            "previous_value": previous[1] if previous else "",
            "change_1_obs": delta(latest_value, previous[1] if previous else None),
            "pct_change_1_obs": pct_change(latest_value, previous[1] if previous else None),
            "source": latest_row.get("source", ""),
            "source_series_id": latest_row.get("source_series_id", ""),
            "source_url": latest_row.get("source_url", ""),
            "notes": latest_row.get("notes", ""),
        }
        for months in (1, 3, 6, 12):
            prior = find_on_or_before(compact_points, add_months(latest_date, -months))
            prior_date = prior[0].isoformat() if prior else ""
            prior_value = prior[1] if prior else None
            output[f"date_{months}m"] = prior_date
            output[f"value_{months}m"] = prior_value if prior is not None else ""
            output[f"change_{months}m"] = delta(latest_value, prior_value)
            output[f"pct_change_{months}m"] = pct_change(latest_value, prior_value)
        snapshot.append({field: output.get(field, "") for field in SNAPSHOT_FIELDS})
    return snapshot


def metrics_from_snapshot(snapshot: list[dict]) -> dict[str, analyze_macro_regime.Metric]:
    metrics: dict[str, analyze_macro_regime.Metric] = {}
    for row in snapshot:
        indicator_id = row.get("indicator_id", "")
        if not indicator_id:
            continue
        metrics[indicator_id] = analyze_macro_regime.Metric(
            indicator_id=indicator_id,
            latest_value=analyze_macro_regime.parse_float(str(row.get("latest_value", ""))),
            latest_date=str(row.get("latest_date", "")),
            age_days=analyze_macro_regime.parse_int(str(row.get("age_days", ""))),
            unit=str(row.get("unit", "")),
            change_1_obs=analyze_macro_regime.parse_float(str(row.get("change_1_obs", ""))),
            pct_change_3m=analyze_macro_regime.parse_float(str(row.get("pct_change_3m", ""))),
            pct_change_6m=analyze_macro_regime.parse_float(str(row.get("pct_change_6m", ""))),
            pct_change_12m=analyze_macro_regime.parse_float(str(row.get("pct_change_12m", ""))),
            freshness_status=str(row.get("freshness_status", "")),
            source=str(row.get("source", "")),
        )
    return metrics


def generate_monthly_reports(
    observations_path: Path,
    output_dir: Path,
    history_path: Path,
    start: str,
    end: str,
    report_day: int,
    history_only: bool = False,
) -> list[Path]:
    rows = read_observations(observations_path)
    output_paths: list[Path] = []
    for report_date in iter_report_dates(start, end, report_day):
        report_date_text = report_date.isoformat()
        snapshot = build_snapshot_as_of(rows, report_date)
        metrics = metrics_from_snapshot(snapshot)
        scores = analyze_macro_regime.calc_scores(metrics)
        previous_scores = analyze_macro_regime.load_previous_scores(history_path, report_date_text)
        report = analyze_macro_regime.build_report(metrics, scores, report_date_text, previous_scores)

        output_path = output_dir / report_date_text[:7] / f"macro_regime_{report_date_text}.md"
        if not history_only:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report, encoding="utf-8")

        allocation = analyze_macro_regime.build_allocation(scores)
        analyze_macro_regime.upsert_report_history(history_path, report_date_text, scores, allocation)
        if not history_only:
            output_paths.append(output_path)
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate monthly historical macro regime reports.")
    parser.add_argument(
        "--observations",
        default="data/processed/macro/observations_long.csv",
        help="Historical long-format observations CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/monthly",
        help="Directory for generated monthly markdown reports.",
    )
    parser.add_argument(
        "--history",
        default="data/processed/macro/risk_score_history_monthly.csv",
        help="Score/allocation history CSV for monthly reports.",
    )
    parser.add_argument("--start", default="2012-03", help="Start month in YYYY-MM format.")
    parser.add_argument(
        "--end",
        default=latest_report_month(),
        help="End month in YYYY-MM format. Defaults to the latest report month whose report day has passed.",
    )
    parser.add_argument(
        "--report-day",
        type=int,
        default=6,
        help="Day of month used as the as-of report date. Defaults to 6.",
    )
    parser.add_argument(
        "--history-only",
        action="store_true",
        help="Only update the monthly score/allocation history CSV; do not write markdown reports.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_paths = generate_monthly_reports(
        Path(args.observations),
        Path(args.output_dir),
        Path(args.history),
        args.start,
        args.end,
        args.report_day,
        args.history_only,
    )
    if args.history_only:
        print("Generated monthly reports: 0 (history-only mode)")
    else:
        print(f"Generated monthly reports: {len(output_paths)}")
    if output_paths:
        print(f"First report: {output_paths[0]}")
        print(f"Last report: {output_paths[-1]}")
    print(f"Updated monthly history: {args.history}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
