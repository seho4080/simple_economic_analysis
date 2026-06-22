#!/usr/bin/env python3
"""Generate data-quality and confidence reports for macro outputs."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_SNAPSHOT = Path("data/processed/macro/latest_snapshot.csv")
DEFAULT_FETCH_STATUS = Path("data/processed/macro/fetch_status.csv")
DEFAULT_ATTRIBUTION = Path("data/processed/macro/risk_attribution_latest.csv")
DEFAULT_OUTPUT_CSV = Path("data/processed/macro/data_quality_latest.csv")
DEFAULT_REPORT_DIR = Path("reports")
DEFAULT_LATEST_REPORT = Path("reports/data_quality_latest.md")

OUTPUT_FIELDS = [
    "scope_type",
    "scope",
    "indicator_count",
    "ok_count",
    "stale_count",
    "problem_count",
    "freshness_score",
    "fetch_score",
    "coverage_score",
    "overall_score",
    "grade",
    "notes",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if text in {"", ".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def freshness_score(rows: list[dict[str, str]]) -> float:
    if not rows:
        return 0.0
    points = []
    for row in rows:
        status = row.get("freshness_status", "") or "ok"
        if status == "ok":
            points.append(1.0)
        elif status == "stale":
            points.append(0.35)
        else:
            points.append(0.0)
    return round(sum(points) / len(points) * 100, 1)


def fetch_score(rows: list[dict[str, str]]) -> float:
    if not rows:
        return 0.0
    ok = sum(1 for row in rows if row.get("status") in {"", "ok"})
    return round(ok / len(rows) * 100, 1)


def coverage_score(attribution_rows: list[dict[str, str]]) -> float:
    if not attribution_rows:
        return 0.0
    by_risk: dict[str, list[dict[str, str]]] = {}
    for row in attribution_rows:
        by_risk.setdefault(row.get("risk_name", "unknown"), []).append(row)
    risk_scores = []
    for rows in by_risk.values():
        count_score = min(len(rows) / 5, 1.0)
        ok_share = sum(1 for row in rows if row.get("freshness_status") in {"", "ok"}) / len(rows)
        risk_scores.append((0.55 * count_score + 0.45 * ok_share) * 100)
    return round(sum(risk_scores) / len(risk_scores), 1)


def overall_score(freshness: float, fetch: float, coverage: float) -> float:
    return round(0.50 * freshness + 0.30 * fetch + 0.20 * coverage, 1)


def count_snapshot(rows: list[dict[str, str]]) -> tuple[int, int, int]:
    ok = sum(1 for row in rows if row.get("freshness_status") in {"", "ok"})
    stale = sum(1 for row in rows if row.get("freshness_status") == "stale")
    problem = len(rows) - ok - stale
    return ok, stale, problem


def build_scope_row(
    scope_type: str,
    scope: str,
    snapshot_rows: list[dict[str, str]],
    fetch_rows: list[dict[str, str]],
    attribution_rows: list[dict[str, str]],
    notes: str = "",
) -> dict[str, Any]:
    fresh = freshness_score(snapshot_rows)
    fetch = fetch_score(fetch_rows)
    if scope_type != "overall" and not fetch_rows:
        fetch = 100.0
    coverage = coverage_score(attribution_rows)
    if scope_type == "category" and not attribution_rows:
        coverage = 100.0
    overall = overall_score(fresh, fetch, coverage)
    ok, stale, problem = count_snapshot(snapshot_rows)
    return {
        "scope_type": scope_type,
        "scope": scope,
        "indicator_count": len(snapshot_rows),
        "ok_count": ok,
        "stale_count": stale,
        "problem_count": problem,
        "freshness_score": fresh,
        "fetch_score": fetch,
        "coverage_score": coverage,
        "overall_score": overall,
        "grade": grade(overall),
        "notes": notes,
    }


def group_by(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get(key, "") or "unknown", []).append(row)
    return grouped


def build_quality_rows(
    snapshot_rows: list[dict[str, str]],
    fetch_rows: list[dict[str, str]],
    attribution_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    rows = [
        build_scope_row("overall", "macro_pipeline", snapshot_rows, fetch_rows, attribution_rows),
    ]
    fetch_by_indicator = group_by(fetch_rows, "indicator_id")
    for category, cat_rows in sorted(group_by(snapshot_rows, "category").items()):
        cat_fetch = []
        for row in cat_rows:
            cat_fetch.extend(fetch_by_indicator.get(row.get("indicator_id", ""), []))
        rows.append(
            build_scope_row(
                "category",
                category,
                cat_rows,
                cat_fetch,
                [],
                notes="Category score excludes attribution coverage.",
            )
        )
    attribution_by_risk = group_by(attribution_rows, "risk_name")
    snapshot_by_id = {row.get("indicator_id", ""): row for row in snapshot_rows}
    for risk_name, risk_rows in sorted(attribution_by_risk.items()):
        risk_snapshot = [snapshot_by_id[row.get("indicator_id", "")] for row in risk_rows if row.get("indicator_id", "") in snapshot_by_id]
        risk_fetch = []
        for row in risk_snapshot:
            risk_fetch.extend(fetch_by_indicator.get(row.get("indicator_id", ""), []))
        rows.append(
            build_scope_row(
                "risk",
                risk_name,
                risk_snapshot,
                risk_fetch,
                risk_rows,
                notes="Risk coverage uses mapped attribution drivers.",
            )
        )
    return rows


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")
    return lines


def build_report(
    quality_rows: list[dict[str, Any]],
    snapshot_rows: list[dict[str, str]],
    fetch_rows: list[dict[str, str]],
) -> tuple[str, str]:
    report_date = date.today().isoformat()
    latest_dates = [row.get("latest_date", "") for row in snapshot_rows if row.get("latest_date")]
    if latest_dates:
        report_date = max(latest_dates)
    overall = quality_rows[0] if quality_rows else {}
    stale = sorted(
        [row for row in snapshot_rows if row.get("freshness_status") == "stale"],
        key=lambda row: parse_float(row.get("age_days")) or 0,
        reverse=True,
    )[:12]
    fetch_problems = [row for row in fetch_rows if row.get("status") not in {"", "ok"}][:12]
    lines = [
        "# Data Quality Report",
        "",
        f"Generated at: {datetime.now().replace(microsecond=0).isoformat()}",
        f"Report date: {report_date}",
        "",
        "## Summary",
        f"- Overall confidence score: {overall.get('overall_score', 0)} / 100 ({overall.get('grade', 'NA')})",
        f"- Freshness score: {overall.get('freshness_score', 0)} / 100",
        f"- Fetch score: {overall.get('fetch_score', 0)} / 100",
        f"- Risk coverage score: {overall.get('coverage_score', 0)} / 100",
        "",
        "## Scores By Category",
        *markdown_table(
            ["Category", "Indicators", "Stale", "Freshness", "Grade"],
            [
                [
                    row["scope"],
                    str(row["indicator_count"]),
                    str(row["stale_count"]),
                    str(row["freshness_score"]),
                    row["grade"],
                ]
                for row in quality_rows
                if row["scope_type"] == "category"
            ],
        ),
        "",
        "## Scores By Risk",
        *markdown_table(
            ["Risk", "Drivers", "Stale", "Coverage", "Overall", "Grade"],
            [
                [
                    row["scope"],
                    str(row["indicator_count"]),
                    str(row["stale_count"]),
                    str(row["coverage_score"]),
                    str(row["overall_score"]),
                    row["grade"],
                ]
                for row in quality_rows
                if row["scope_type"] == "risk"
            ],
        ),
        "",
        "## Stale Indicators",
    ]
    if stale:
        lines.extend(
            markdown_table(
                ["Indicator", "Category", "Latest date", "Age days", "Source"],
                [
                    [
                        row.get("indicator_id", ""),
                        row.get("category", ""),
                        row.get("latest_date", ""),
                        row.get("age_days", ""),
                        row.get("source", ""),
                    ]
                    for row in stale
                ],
            )
        )
    else:
        lines.append("No stale indicators.")
    lines.extend(["", "## Fetch Problems"])
    if fetch_problems:
        lines.extend(
            markdown_table(
                ["Indicator", "Source type", "Status", "Message"],
                [
                    [
                        row.get("indicator_id", ""),
                        row.get("source_type", ""),
                        row.get("status", ""),
                        (row.get("message", "") or "")[:160],
                    ]
                    for row in fetch_problems
                ],
            )
        )
    else:
        lines.append("No fetch problems in the latest status table.")
    lines.extend(
        [
            "",
            "## Method",
            "- Overall = 50% freshness + 30% fetch health + 20% risk-driver coverage.",
            "- Stale indicators receive partial freshness credit rather than zero, because fallback series can still be useful with caution.",
            "- Risk coverage is based on mapped drivers in `risk_attribution_latest.csv`.",
            f"- Raw status counts: {json.dumps({'snapshot_rows': len(snapshot_rows), 'fetch_rows': len(fetch_rows)}, ensure_ascii=False)}",
        ]
    )
    return "\n".join(lines) + "\n", report_date


def write_outputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    snapshot_rows = read_csv(Path(args.snapshot))
    fetch_rows = read_csv(Path(args.fetch_status))
    attribution_rows = read_csv(Path(args.attribution))
    quality_rows = build_quality_rows(snapshot_rows, fetch_rows, attribution_rows)
    output_csv = Path(args.output_csv)
    write_csv(output_csv, quality_rows, OUTPUT_FIELDS)
    report, report_date = build_report(quality_rows, snapshot_rows, fetch_rows)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.output) if args.output else report_dir / f"data_quality_{report_date}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    latest_report = Path(args.latest_output)
    latest_report.parent.mkdir(parents=True, exist_ok=True)
    latest_report.write_text(report, encoding="utf-8")
    return report_path, latest_report, output_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate macro data-quality confidence report.")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--fetch-status", default=str(DEFAULT_FETCH_STATUS))
    parser.add_argument("--attribution", default=str(DEFAULT_ATTRIBUTION))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_REPORT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report_path, latest_report, output_csv = write_outputs(args)
    print(f"Generated data-quality report: {report_path}")
    print(f"Updated latest data-quality report: {latest_report}")
    print(f"Wrote data-quality CSV: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
