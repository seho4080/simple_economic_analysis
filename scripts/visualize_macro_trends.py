#!/usr/bin/env python3
"""Generate macro trend charts and attach them to the markdown report."""

from __future__ import annotations

import argparse
import bisect
import csv
import math
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analyze_macro_regime


VISUAL_START = "<!-- macro-visual-dashboard:start -->"
VISUAL_END = "<!-- macro-visual-dashboard:end -->"


@dataclass(frozen=True)
class Point:
    date: date
    value: float


@dataclass(frozen=True)
class ChartResult:
    title: str
    path: Path
    caption: str


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value in {"", ".", "NA", "N/A"}:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def read_observations(path: Path, indicator_ids: set[str]) -> dict[str, list[Point]]:
    series = {indicator_id: [] for indicator_id in indicator_ids}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            indicator_id = row.get("indicator_id", "")
            if indicator_id not in series:
                continue
            value = parse_float(row.get("value"))
            raw_date = row.get("date", "")
            if value is None or not raw_date:
                continue
            try:
                point_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            series[indicator_id].append(Point(point_date, value))

    for points in series.values():
        points.sort(key=lambda point: point.date)
    return series


def trim_since(points: list[Point], years: int) -> list[Point]:
    if not points:
        return []
    cutoff = points[-1].date - timedelta(days=365 * years)
    return [point for point in points if point.date >= cutoff]


def downsample(points: list[Point], max_points: int = 900) -> list[Point]:
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def normalize_to_100(points: list[Point]) -> list[Point]:
    clean = [point for point in points if point.value != 0]
    if not clean:
        return []
    base = clean[0].value
    return [Point(point.date, point.value / base * 100) for point in points]


def same_day_last_year(point_date: date) -> date:
    try:
        return point_date.replace(year=point_date.year - 1)
    except ValueError:
        return point_date.replace(year=point_date.year - 1, day=28)


def year_over_year(points: list[Point], tolerance_days: int = 45) -> list[Point]:
    if not points:
        return []

    dates = [point.date for point in points]
    result: list[Point] = []
    for point in points:
        target = same_day_last_year(point.date)
        idx = bisect.bisect_right(dates, target) - 1
        if idx < 0:
            continue
        prior = points[idx]
        if abs((prior.date - target).days) > tolerance_days or prior.value == 0:
            continue
        result.append(Point(point.date, (point.value / prior.value - 1) * 100))
    return result


def prepare_points(points: list[Point], transform: str, years: int) -> list[Point]:
    if transform == "yoy":
        points = year_over_year(points)
    elif transform == "normalized":
        points = normalize_to_100(points)
    return downsample(trim_since(points, years))


def finish_plot(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.grid(True, axis="y", alpha=0.2)
    plt.legend(loc="best", frameon=False)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def plot_lines(
    series: dict[str, list[Point]],
    specs: list[tuple[str, str]],
    output_path: Path,
    title: str,
    ylabel: str,
    transform: str = "raw",
    years: int = 5,
) -> bool:
    plt.figure(figsize=(11, 6))
    plotted = False
    for indicator_id, label in specs:
        points = prepare_points(series.get(indicator_id, []), transform, years)
        if not points:
            continue
        plt.plot(
            [point.date for point in points],
            [point.value for point in points],
            linewidth=2,
            label=label,
        )
        plotted = True

    if not plotted:
        plt.close()
        return False

    plt.title(title, fontsize=15, fontweight="bold")
    plt.ylabel(ylabel)
    plt.xlabel("")
    finish_plot(output_path)
    return True


def score_color(score: float) -> str:
    if score >= 7:
        return "#d1495b"
    if score >= 5:
        return "#edae49"
    if score >= 3:
        return "#4d908e"
    return "#2a9d8f"


def plot_risk_scores(scores: dict[str, float], output_path: Path) -> bool:
    labels = list(scores.keys())
    values = [scores[label] for label in labels]
    colors = [score_color(value) for value in values]

    plt.figure(figsize=(11, 6))
    bars = plt.barh(labels, values, color=colors)
    plt.xlim(0, 10)
    plt.title("Macro Risk Scores", fontsize=15, fontweight="bold")
    plt.xlabel("score out of 10")
    plt.gca().invert_yaxis()
    for bar, value in zip(bars, values):
        plt.text(value + 0.15, bar.get_y() + bar.get_height() / 2, f"{value:.1f}", va="center")
    plt.grid(True, axis="x", alpha=0.2)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160)
    plt.close()
    return True


def plot_allocation(scores: dict[str, float], output_path: Path) -> bool:
    allocation = analyze_macro_regime.build_allocation(scores)
    labels = ["Cash/short bonds", "Gold", "Silver/resources", "Stocks/ETF"]
    values = [
        allocation["cash"],
        allocation["gold"],
        allocation["silver"],
        allocation["equity"],
    ]
    colors = ["#457b9d", "#d4a017", "#7f8c8d", "#2a9d8f"]

    plt.figure(figsize=(8, 8))
    wedges, texts, autotexts = plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        pctdistance=0.78,
    )
    for text in texts + autotexts:
        text.set_fontsize(10)
    plt.title("Suggested New Allocation", fontsize=15, fontweight="bold")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160)
    plt.close()
    return True


def build_chart_specs() -> list[tuple[str, str, str, str, str, list[tuple[str, str]]]]:
    return [
        (
            "inflation_yoy.png",
            "Inflation Trend",
            "YoY change (%)",
            "yoy",
            "Consumer inflation momentum across US and Korea.",
            [
                ("us_cpi_all_items", "US CPI"),
                ("us_core_cpi", "US Core CPI"),
                ("us_core_pce_price_index", "US Core PCE"),
                ("korea_cpi_all_items", "Korea CPI"),
            ],
        ),
        (
            "policy_rates.png",
            "Rates and Yield Trend",
            "percent / percentage points",
            "raw",
            "Policy rates and US Treasury yields show how restrictive conditions remain.",
            [
                ("fed_policy_rate_mid", "Fed target midpoint"),
                ("bok_base_rate", "BOK base rate"),
                ("us_treasury_10y", "US 10Y Treasury"),
                ("us_treasury_2y", "US 2Y Treasury"),
            ],
        ),
        (
            "fx_trend.png",
            "Dollar and USD/KRW Trend",
            "index, first visible point = 100",
            "normalized",
            "USD/KRW and DXY are normalized so direction and slope are easy to compare.",
            [
                ("usd_krw", "USD/KRW"),
                ("dxy", "DXY"),
                ("us_broad_dollar_index", "Broad dollar index"),
            ],
        ),
        (
            "liquidity_trend.png",
            "Liquidity Trend",
            "index, first visible point = 100",
            "normalized",
            "Money supply and Fed balance-sheet indicators are normalized to compare liquidity pressure.",
            [
                ("us_m2", "US M2"),
                ("korea_m2", "Korea M2"),
                ("fed_balance_sheet_assets", "Fed assets"),
                ("fed_reserve_balances", "Fed reserve balances"),
            ],
        ),
        (
            "credit_stress.png",
            "Credit Stress Trend",
            "spread pct points / index",
            "raw",
            "Credit spreads and financial-stress indexes flag whether risk appetite is cracking.",
            [
                ("us_high_yield_spread", "US HY spread"),
                ("us_bbb_spread", "US BBB spread"),
                ("us_financial_stress", "St. Louis Fed stress"),
                ("us_chicago_fed_nfci", "Chicago Fed NFCI"),
            ],
        ),
        (
            "commodity_trend.png",
            "Commodity Shock Trend",
            "index, first visible point = 100",
            "normalized",
            "Energy, metals, and agricultural prices are normalized to make supply-shock pressure visible.",
            [
                ("wti_spot", "WTI"),
                ("gold_futures", "Gold"),
                ("silver_futures", "Silver"),
                ("wheat_futures", "Wheat"),
                ("fertilizer_ppi", "Fertilizer PPI"),
            ],
        ),
    ]


def all_indicator_ids() -> set[str]:
    ids: set[str] = set()
    for _, _, _, _, _, specs in build_chart_specs():
        ids.update(indicator_id for indicator_id, _ in specs)
    return ids


def markdown_path(report_path: Path, image_path: Path) -> str:
    return Path(os.path.relpath(image_path, report_path.parent)).as_posix()


def build_visual_section(report_path: Path, charts: list[ChartResult]) -> str:
    lines = [
        "",
        VISUAL_START,
        "## Visual Dashboard",
        "",
        "Charts are generated from `data/processed/macro/observations_long.csv` and the latest risk-score snapshot.",
        "",
    ]
    for chart in charts:
        rel_path = markdown_path(report_path, chart.path)
        lines.extend(
            [
                f"### {chart.title}",
                "",
                f"![{chart.title}]({rel_path})",
                "",
                chart.caption,
                "",
            ]
        )
    lines.append(VISUAL_END)
    lines.append("")
    return "\n".join(lines)


def update_report_with_charts(report_path: Path, charts: list[ChartResult]) -> None:
    if not report_path.exists():
        return
    text = report_path.read_text(encoding="utf-8")
    section = build_visual_section(report_path, charts)
    if VISUAL_START in text and VISUAL_END in text:
        before = text.split(VISUAL_START, 1)[0].rstrip()
        after = text.split(VISUAL_END, 1)[1].lstrip()
        text = before + section + after
    else:
        text = text.rstrip() + section
    report_path.write_text(text, encoding="utf-8")


def generate_visual_dashboard(
    observations_path: Path,
    snapshot_path: Path,
    report_date: str,
    chart_root: Path,
    report_path: Path | None = None,
    update_report: bool = True,
    years: int = 5,
) -> list[ChartResult]:
    chart_dir = chart_root / f"macro_regime_{report_date}"
    series = read_observations(observations_path, all_indicator_ids())
    metrics = analyze_macro_regime.load_metrics(snapshot_path)
    scores = analyze_macro_regime.calc_scores(metrics)

    charts: list[ChartResult] = []

    risk_path = chart_dir / "risk_scores.png"
    plot_risk_scores(scores, risk_path)
    charts.append(
        ChartResult(
            "Macro Risk Scores",
            risk_path,
            "A compact view of the regime model's six risk buckets.",
        )
    )

    allocation_path = chart_dir / "suggested_allocation.png"
    plot_allocation(scores, allocation_path)
    charts.append(
        ChartResult(
            "Suggested Allocation",
            allocation_path,
            "Fresh 150만원 allocation output from the same score rules used in the report.",
        )
    )

    for filename, title, ylabel, transform, caption, specs in build_chart_specs():
        output_path = chart_dir / filename
        if plot_lines(series, specs, output_path, title, ylabel, transform, years):
            charts.append(ChartResult(title, output_path, caption))

    if report_path and update_report:
        update_report_with_charts(report_path, charts)

    return charts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate macro trend chart images.")
    parser.add_argument(
        "--observations",
        default="data/processed/macro/observations_long.csv",
        help="Long-format observations CSV.",
    )
    parser.add_argument(
        "--snapshot",
        default="data/processed/macro/latest_snapshot.csv",
        help="Latest snapshot CSV used for risk scores.",
    )
    parser.add_argument(
        "--report-date",
        default=date.today().isoformat(),
        help="Report date used for chart asset directory naming.",
    )
    parser.add_argument(
        "--chart-dir",
        default="reports/assets",
        help="Root directory for generated chart assets.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Markdown report to update with chart image links.",
    )
    parser.add_argument(
        "--no-report-update",
        action="store_true",
        help="Generate chart images without editing the markdown report.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Trailing number of years to show in trend charts.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report_path = Path(args.report) if args.report else None
    charts = generate_visual_dashboard(
        Path(args.observations),
        Path(args.snapshot),
        args.report_date,
        Path(args.chart_dir),
        report_path=report_path,
        update_report=not args.no_report_update,
        years=args.years,
    )
    print(f"Generated {len(charts)} charts:")
    for chart in charts:
        print(f"  {chart.path}")
    if report_path and not args.no_report_update:
        print(f"Updated report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
