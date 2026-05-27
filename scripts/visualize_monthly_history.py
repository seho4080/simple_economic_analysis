#!/usr/bin/env python3
"""Generate charts and tables from the monthly macro regime history."""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


RISK_COLUMNS = [
    ("inflation_risk", "Inflation"),
    ("liquidity_bubble_risk", "Liquidity"),
    ("credit_stress_risk", "Credit"),
    ("fx_risk", "FX"),
    ("climate_supply_shock_risk", "Climate"),
    ("growth_slowdown_risk", "Growth"),
]

ALLOCATION_COLUMNS = [
    ("cash_amount", "Cash/short bonds"),
    ("gold_amount", "Gold"),
    ("silver_amount", "Silver/resources"),
    ("equity_amount", "Stocks/ETF"),
]

RISK_COLORS = {
    "Inflation": "#d1495b",
    "Liquidity": "#457b9d",
    "Credit": "#7f8c8d",
    "FX": "#6d597a",
    "Climate": "#edae49",
    "Growth": "#2a9d8f",
}

ALLOCATION_COLORS = ["#457b9d", "#d4a017", "#7f8c8d", "#2a9d8f"]


@dataclass(frozen=True)
class MonthlyRow:
    report_date: date
    current_regime: str
    supporting_regime: str
    scores: dict[str, float]
    allocation: dict[str, float]


def parse_float(value: str | None) -> float:
    if value is None:
        return math.nan
    value = value.strip().replace(",", "")
    if value in {"", ".", "NA", "N/A"}:
        return math.nan
    try:
        return float(value)
    except ValueError:
        return math.nan


def read_history(path: Path) -> list[MonthlyRow]:
    rows: list[MonthlyRow] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_date = row.get("report_date", "")
            if not raw_date:
                continue
            try:
                report_date = date.fromisoformat(raw_date)
            except ValueError:
                continue

            scores = {key: parse_float(row.get(key)) for key, _ in RISK_COLUMNS}
            allocation = {key: parse_float(row.get(key)) for key, _ in ALLOCATION_COLUMNS}
            rows.append(
                MonthlyRow(
                    report_date=report_date,
                    current_regime=row.get("current_regime", ""),
                    supporting_regime=row.get("supporting_regime", ""),
                    scores=scores,
                    allocation=allocation,
                )
            )
    rows.sort(key=lambda item: item.report_date)
    return rows


def finite(values: list[float]) -> list[float]:
    return [value for value in values if not math.isnan(value)]


def mean(values: list[float]) -> float:
    values = finite(values)
    if not values:
        return math.nan
    return sum(values) / len(values)


def fmt_number(value: float, digits: int = 1) -> str:
    if math.isnan(value):
        return "NA"
    return f"{value:.{digits}f}"


def fmt_signed(value: float, digits: int = 1) -> str:
    if math.isnan(value):
        return "NA"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{digits}f}"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def finish_plot(path: Path) -> None:
    ensure_parent(path)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def plot_risk_lines(rows: list[MonthlyRow], path: Path) -> None:
    dates = [row.report_date for row in rows]
    plt.figure(figsize=(13, 6.5))
    for key, label in RISK_COLUMNS:
        values = [row.scores[key] for row in rows]
        plt.plot(dates, values, label=label, linewidth=1.8, color=RISK_COLORS[label])
    plt.title("Monthly Macro Risk Scores", fontsize=15, fontweight="bold")
    plt.ylabel("score out of 10")
    plt.ylim(0, 10)
    plt.grid(True, axis="y", alpha=0.22)
    plt.legend(ncol=3, frameon=False)
    plt.gca().xaxis.set_major_locator(mdates.YearLocator(1))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45, ha="right")
    finish_plot(path)


def plot_risk_heatmap(rows: list[MonthlyRow], path: Path) -> None:
    labels = [label for _, label in RISK_COLUMNS]
    data = [[row.scores[key] for row in rows] for key, _ in RISK_COLUMNS]

    plt.figure(figsize=(14, 4.8))
    image = plt.imshow(data, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=10)
    plt.title("Risk Score Heatmap", fontsize=15, fontweight="bold")
    plt.yticks(range(len(labels)), labels)
    tick_positions = [
        idx for idx, row in enumerate(rows) if idx == 0 or row.report_date.month == 1
    ]
    plt.xticks(
        tick_positions,
        [rows[idx].report_date.strftime("%Y-%m") for idx in tick_positions],
        rotation=45,
        ha="right",
    )
    colorbar = plt.colorbar(image)
    colorbar.set_label("score out of 10")
    finish_plot(path)


def plot_allocation_stack(rows: list[MonthlyRow], path: Path) -> None:
    dates = [row.report_date for row in rows]
    values_by_asset: list[list[float]] = []
    for key, _ in ALLOCATION_COLUMNS:
        values_by_asset.append(
            [
                row.allocation[key] / sum(finite(list(row.allocation.values()))) * 100
                if sum(finite(list(row.allocation.values()))) > 0
                else math.nan
                for row in rows
            ]
        )

    plt.figure(figsize=(13, 6.5))
    plt.stackplot(
        dates,
        values_by_asset,
        labels=[label for _, label in ALLOCATION_COLUMNS],
        colors=ALLOCATION_COLORS,
        alpha=0.9,
    )
    plt.title("Suggested Monthly Allocation", fontsize=15, fontweight="bold")
    plt.ylabel("share of monthly contribution (%)")
    plt.ylim(0, 100)
    plt.grid(True, axis="y", alpha=0.2)
    plt.legend(loc="upper left", ncol=2, frameon=False)
    plt.gca().xaxis.set_major_locator(mdates.YearLocator(1))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45, ha="right")
    finish_plot(path)


def plot_regime_counts(rows: list[MonthlyRow], path: Path, top_n: int = 10) -> None:
    counts = Counter(row.current_regime for row in rows if row.current_regime)
    top_items = counts.most_common(top_n)
    labels = [item[0] for item in top_items]
    values = [item[1] for item in top_items]

    plt.figure(figsize=(12, 6.5))
    bars = plt.barh(labels, values, color="#457b9d")
    plt.title("Most Frequent Monthly Regimes", fontsize=15, fontweight="bold")
    plt.xlabel("months")
    plt.gca().invert_yaxis()
    plt.grid(True, axis="x", alpha=0.2)
    for bar, value in zip(bars, values):
        plt.text(value + 0.5, bar.get_y() + bar.get_height() / 2, str(value), va="center")
    finish_plot(path)


def plot_latest_vs_average(rows: list[MonthlyRow], path: Path) -> None:
    latest = rows[-1]
    labels = [label for _, label in RISK_COLUMNS]
    latest_values = [latest.scores[key] for key, _ in RISK_COLUMNS]
    avg_values = [mean([row.scores[key] for row in rows]) for key, _ in RISK_COLUMNS]

    x_positions = list(range(len(labels)))
    width = 0.36
    plt.figure(figsize=(12, 6.5))
    plt.bar(
        [x - width / 2 for x in x_positions],
        avg_values,
        width=width,
        label="Long-run average",
        color="#9aa0a6",
    )
    plt.bar(
        [x + width / 2 for x in x_positions],
        latest_values,
        width=width,
        label=f"Latest ({latest.report_date.isoformat()})",
        color="#d1495b",
    )
    plt.title("Latest Risk Scores vs History", fontsize=15, fontweight="bold")
    plt.ylabel("score out of 10")
    plt.ylim(0, 10)
    plt.xticks(x_positions, labels, rotation=20, ha="right")
    plt.grid(True, axis="y", alpha=0.2)
    plt.legend(frameon=False)
    finish_plot(path)


def build_risk_summary(rows: list[MonthlyRow]) -> list[dict[str, str]]:
    latest = rows[-1]
    prior_12m = rows[-13] if len(rows) >= 13 else None
    summary: list[dict[str, str]] = []
    for key, label in RISK_COLUMNS:
        values = finite([row.scores[key] for row in rows])
        latest_value = latest.scores[key]
        delta_12m = latest_value - prior_12m.scores[key] if prior_12m else math.nan
        summary.append(
            {
                "risk_bucket": label,
                "latest": fmt_number(latest_value),
                "long_run_avg": fmt_number(mean(values)),
                "min": fmt_number(min(values) if values else math.nan),
                "max": fmt_number(max(values) if values else math.nan),
                "change_12m": fmt_signed(delta_12m),
            }
        )
    return summary


def build_regime_counts(rows: list[MonthlyRow]) -> list[dict[str, str]]:
    counts = Counter(row.current_regime for row in rows if row.current_regime)
    total = sum(counts.values())
    return [
        {
            "regime": regime,
            "months": str(months),
            "share": f"{months / total * 100:.1f}%" if total else "NA",
        }
        for regime, months in counts.most_common()
    ]


def build_monthly_detail(rows: list[MonthlyRow]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        result.append(
            {
                "year": str(row.report_date.year),
                "month": row.report_date.strftime("%Y-%m"),
                "regime": row.current_regime,
                "inflation": fmt_number(row.scores["inflation_risk"]),
                "liquidity": fmt_number(row.scores["liquidity_bubble_risk"]),
                "credit": fmt_number(row.scores["credit_stress_risk"]),
                "fx": fmt_number(row.scores["fx_risk"]),
                "climate": fmt_number(row.scores["climate_supply_shock_risk"]),
                "growth": fmt_number(row.scores["growth_slowdown_risk"]),
                "cash": fmt_number(row.allocation["cash_amount"], 0),
                "gold": fmt_number(row.allocation["gold_amount"], 0),
                "silver": fmt_number(row.allocation["silver_amount"], 0),
                "equity": fmt_number(row.allocation["equity_amount"], 0),
            }
        )
    return result


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    ensure_parent(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, str]], limit: int | None = None) -> list[str]:
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        return []

    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row[header] for header in headers) + " |")
    return lines


def rel_path(report_path: Path, target: Path) -> str:
    return Path(os.path.relpath(target, report_path.parent)).as_posix()


def build_dashboard_notes() -> list[str]:
    return [
        "## 대시보드 읽는 법",
        "",
        "- 이 대시보드는 월별 리포트 생성 결과를 다시 모아 복기하는 화면입니다. 매월 6일 기준으로 당시 보였던 리스크 점수와 신규 150만원 배분 판단을 비교합니다.",
        "- Risk Score는 0~10점입니다. 점수가 높을수록 해당 위험이 강하다는 뜻이고, 모든 점수가 동시에 낮아야 공격적 배분이 자연스러워집니다.",
        "- 배분 그래프는 기존 보유자산 전체 리밸런싱이 아니라, 매월 새로 넣는 150만원을 어디에 배분했는지를 보여줍니다.",
        "- 레짐 빈도는 모델이 어떤 시장 환경을 가장 자주 봤는지 확인하는 용도입니다. 수익률 우열을 직접 뜻하지는 않습니다.",
        "- Latest vs Average는 최근 리스크가 장기 평균보다 높은지 낮은지 빠르게 보는 비교표입니다.",
        "",
        "## 금/은 상품 가정",
        "",
        "- 실전 ISA 기준 금 헤지는 `411060.KS ACE KRX금현물`을 더 자연스러운 기본 후보로 봅니다.",
        "- 긴 과거 구간이 필요한 백테스트에서는 상장 기간 때문에 `132030.KS KODEX 골드선물(H)`을 과거 프록시로 쓸 수 있습니다.",
        "- 은은 국내 상장 은현물 ETF가 마땅치 않아 `144600.KS KODEX 은선물(H)`을 보조 헤지로 유지합니다.",
        "- 따라서 은/원자재 비중은 장기 핵심 방어자산이라기보다, 인플레나 원자재 충격에 대한 작은 선택 옵션으로 해석합니다.",
        "",
    ]


def write_report(
    report_path: Path,
    history_path: Path,
    chart_paths: dict[str, Path],
    risk_summary: list[dict[str, str]],
    regime_counts: list[dict[str, str]],
    monthly_detail: list[dict[str, str]],
    rows: list[MonthlyRow],
) -> None:
    latest = rows[-1]
    latest_total = sum(finite(list(latest.allocation.values())))
    latest_alloc = [
        {
            "asset": label,
            "amount_manwon": fmt_number(latest.allocation[key], 0),
            "share": f"{latest.allocation[key] / latest_total * 100:.1f}%" if latest_total else "NA",
        }
        for key, label in ALLOCATION_COLUMNS
    ]

    lines = [
        "# 월별 매크로 히스토리 대시보드",
        "",
        f"기준 데이터: `{history_path.as_posix()}`",
        f"기간: {rows[0].report_date.isoformat()} ~ {rows[-1].report_date.isoformat()} ({len(rows)}개월)",
        "",
        "## 핵심 Risk Score 요약",
        "",
        *markdown_table(risk_summary),
        "",
        "## 최근 월 배분",
        "",
        f"최근 기준일: {latest.report_date.isoformat()}",
        "",
        *markdown_table(latest_alloc),
        "",
        "## 레짐 빈도",
        "",
        *markdown_table(regime_counts, limit=12),
        "",
        "## 그래프",
        "",
    ]
    lines[5:5] = build_dashboard_notes()

    chart_sections = [
        ("Risk Score Trend", "월별 6개 Risk Score의 장기 흐름입니다.", "risk_lines"),
        ("Risk Score Heatmap", "어느 구간에서 어떤 리스크가 강했는지 한눈에 보는 표입니다.", "risk_heatmap"),
        ("Allocation Trend", "월별 150만원 신규 투자금의 제안 배분 비중 변화입니다.", "allocation_stack"),
        ("Regime Counts", "월별 리포트에서 가장 자주 나온 메인 레짐입니다.", "regime_counts"),
        ("Latest vs Average", "최근 점수가 장기 평균 대비 높은지 낮은지 비교합니다.", "latest_vs_average"),
    ]

    for title, caption, key in chart_sections:
        image_path = chart_paths[key]
        lines.extend(
            [
                f"### {title}",
                "",
                f"![{title}]({rel_path(report_path, image_path)})",
                "",
                caption,
                "",
            ]
        )

    lines.extend(["## 연도별 월별 상세", "", "각 월의 메인 레짐, Risk Score, 신규 150만원 배분액(만원)입니다.", ""])
    monthly_by_year: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in monthly_detail:
        monthly_by_year[row["year"]].append({key: value for key, value in row.items() if key != "year"})

    for year in sorted(monthly_by_year):
        lines.extend([f"### {year}", "", *markdown_table(monthly_by_year[year]), ""])

    ensure_parent(report_path)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def generate_dashboard(
    history_path: Path,
    report_path: Path,
    chart_dir: Path,
    tables_dir: Path,
) -> None:
    rows = read_history(history_path)
    if not rows:
        raise ValueError(f"No monthly history rows found: {history_path}")

    chart_paths = {
        "risk_lines": chart_dir / "risk_scores_over_time.png",
        "risk_heatmap": chart_dir / "risk_score_heatmap.png",
        "allocation_stack": chart_dir / "allocation_over_time.png",
        "regime_counts": chart_dir / "regime_counts.png",
        "latest_vs_average": chart_dir / "latest_vs_average.png",
    }

    plot_risk_lines(rows, chart_paths["risk_lines"])
    plot_risk_heatmap(rows, chart_paths["risk_heatmap"])
    plot_allocation_stack(rows, chart_paths["allocation_stack"])
    plot_regime_counts(rows, chart_paths["regime_counts"])
    plot_latest_vs_average(rows, chart_paths["latest_vs_average"])

    risk_summary = build_risk_summary(rows)
    regime_counts = build_regime_counts(rows)
    monthly_detail = build_monthly_detail(rows)

    write_csv(tables_dir / "risk_score_summary.csv", risk_summary)
    write_csv(tables_dir / "regime_counts.csv", regime_counts)
    write_csv(tables_dir / "monthly_detail.csv", monthly_detail)
    stale_yearly_csv = tables_dir / "yearly_risk_scores.csv"
    if stale_yearly_csv.exists():
        stale_yearly_csv.unlink()
    write_report(
        report_path,
        history_path,
        chart_paths,
        risk_summary,
        regime_counts,
        monthly_detail,
        rows,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a dashboard from monthly regime history.")
    parser.add_argument(
        "--history",
        default="data/processed/macro/risk_score_history_monthly.csv",
        help="Monthly risk-score history CSV.",
    )
    parser.add_argument(
        "--report",
        default="reports/monthly_dashboard.md",
        help="Markdown dashboard output path.",
    )
    parser.add_argument(
        "--chart-dir",
        default="reports/assets/monthly_dashboard",
        help="Directory for generated PNG chart assets.",
    )
    parser.add_argument(
        "--tables-dir",
        default="data/processed/macro/monthly_dashboard",
        help="Directory for generated summary CSV tables.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    generate_dashboard(
        history_path=Path(args.history),
        report_path=Path(args.report),
        chart_dir=Path(args.chart_dir),
        tables_dir=Path(args.tables_dir),
    )
    print(f"Updated dashboard: {args.report}")
    print(f"Chart assets: {args.chart_dir}")
    print(f"Summary tables: {args.tables_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
