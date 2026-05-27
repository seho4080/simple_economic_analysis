#!/usr/bin/env python3
"""Run comparable actual-ETF backtests for hedged/unhedged equity choices."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import backtest_actual_etfs
from backtest_monthly_allocation import pct, read_csv, write_csv, xirr


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


DEFAULT_VARIANTS = [
    Variant(
        slug="hedged_sp500_2022",
        title="환헤지 S&P500",
        start="2022-01-06",
        end="2026-04-06",
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="132030.KS",
        gold_label="KODEX 골드선물(H)",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="219480.KS",
        equity_label="KODEX 미국S&P500선물(H)",
        note="기존 실제 ETF 매핑과 유사한 환헤지형 비교군",
    ),
    Variant(
        slug="unhedged_sp500_2022",
        title="환노출 S&P500",
        start="2022-01-06",
        end="2026-04-06",
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="411060.KS",
        gold_label="ACE KRX금현물",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="360750.KS",
        equity_label="TIGER 미국S&P500",
        note="금과 주식은 환노출형, 은은 장기 국내 비헤지 대체재 부족으로 기존 은선물(H) 유지",
    ),
    Variant(
        slug="unhedged_nasdaq_2022",
        title="환노출 나스닥100",
        start="2022-01-06",
        end="2026-04-06",
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="411060.KS",
        gold_label="ACE KRX금현물",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="133690.KS",
        equity_label="TIGER 미국나스닥100",
        note="주식 버킷을 환노출 나스닥100으로 대체한 성장주 민감도 비교군",
    ),
]


def build_variant_args(args: argparse.Namespace, variant: Variant) -> SimpleNamespace:
    return SimpleNamespace(
        history=args.history,
        start=variant.start,
        end=variant.end,
        valuation_date=args.valuation_date,
        raw_dir=str(Path(args.raw_dir) / variant.slug),
        output_dir=str(Path(args.output_dir) / variant.slug),
        report=str(Path(args.report_dir) / f"{variant.slug}.md"),
        cash_symbol=variant.cash_symbol,
        cash_label=variant.cash_label,
        gold_symbol=variant.gold_symbol,
        gold_label=variant.gold_label,
        silver_symbol=variant.silver_symbol,
        silver_label=variant.silver_label,
        equity_symbol=variant.equity_symbol,
        equity_label=variant.equity_label,
    )


def max_drawdown(curve_rows: list[dict]) -> float:
    peak = 0.0
    drawdown = 0.0
    for row in curve_rows:
        value = float(row["total_value_krw"])
        peak = max(peak, value)
        if peak > 0:
            drawdown = min(drawdown, value / peak - 1.0)
    return drawdown


def summarize_variant(variant: Variant, output_dir: Path, report_path: Path) -> dict:
    trades = read_csv(output_dir / "actual_etf_trades.csv")
    curve = read_csv(output_dir / "actual_etf_equity_curve.csv")
    final = curve[-1]
    cashflows = [(row["report_date"], -float(row["amount_krw"])) for row in trades]
    cashflows.append((final["date"], float(final["total_value_krw"])))
    irr = xirr([(date.fromisoformat(day), amount) for day, amount in cashflows])
    contribution = float(final["contribution_krw"])
    total_value = float(final["total_value_krw"])
    return {
        "variant": variant.slug,
        "title": variant.title,
        "start": variant.start,
        "end": variant.end,
        "valuation_date": final["date"],
        "cash_symbol": variant.cash_symbol,
        "gold_symbol": variant.gold_symbol,
        "silver_symbol": variant.silver_symbol,
        "equity_symbol": variant.equity_symbol,
        "contribution_krw": round(contribution),
        "final_value_krw": round(total_value),
        "profit_krw": round(total_value - contribution),
        "simple_return": total_value / contribution - 1.0,
        "xirr": irr if irr is not None else "",
        "max_drawdown": max_drawdown(curve),
        "report": report_path.as_posix(),
        "note": variant.note,
    }


def write_summary_report(path: Path, summary_rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 실제 ETF 환헤지/환노출/나스닥 비교 백테스트",
        "",
        "## 비교 기준",
        "- 매수 기간: 2022-01-06 ~ 2026-04-06, 매월 150만원 리포트 배분",
        "- 평가일: 2026-05-27",
        "- 가격 데이터: Yahoo Finance 국내 ETF 조정종가",
        "- 2022년부터 비교한 이유: ACE KRX금현물(411060)이 2021년 12월 상장이라 금 환노출형 비교가 이 시점부터 가능",
        "- 은은 장기 국내 환노출 ETF 대체재가 제한적이라 KODEX 은선물(H)을 공통 사용",
        "",
        "## 결과 요약",
        "| 프로필 | ETF 조합 | 원금 | 평가액 | 손익 | 수익률 | XIRR | 최대 낙폭 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        combo = f"{row['cash_symbol']} / {row['gold_symbol']} / {row['silver_symbol']} / {row['equity_symbol']}"
        lines.append(
            "| {title} | {combo} | {contribution:,.0f}원 | {final:,.0f}원 | {profit:,.0f}원 | {simple} | {xirr} | {mdd} |".format(
                title=row["title"],
                combo=combo,
                contribution=row["contribution_krw"],
                final=row["final_value_krw"],
                profit=row["profit_krw"],
                simple=pct(float(row["simple_return"])),
                xirr=pct(float(row["xirr"])) if row["xirr"] != "" else "n/a",
                mdd=pct(float(row["max_drawdown"])),
            )
        )
    lines.extend(
        [
            "",
            "## 개별 리포트",
        ]
    )
    for row in summary_rows:
        lines.append(f"- {row['title']}: `{row['report']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run actual ETF variant backtests.")
    parser.add_argument("--history", default="data/processed/macro/risk_score_history_monthly.csv")
    parser.add_argument("--valuation-date", default="2026-05-27")
    parser.add_argument("--raw-dir", default="data/raw/yahoo_kr_etf_variants")
    parser.add_argument("--output-dir", default="data/processed/backtests/actual_kr_etf_variants")
    parser.add_argument("--report-dir", default="reports/backtests/actual_kr_etf_variants")
    parser.add_argument("--summary-report", default="reports/backtests/actual_kr_etf_variants_2022-01_to_2026-04.md")
    parser.add_argument("--summary-csv", default="data/processed/backtests/actual_kr_etf_variants/variant_summary.csv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary_rows: list[dict] = []
    for variant in DEFAULT_VARIANTS:
        variant_args = build_variant_args(args, variant)
        report_path, _, _ = backtest_actual_etfs.run_backtest(variant_args)
        summary_rows.append(
            summarize_variant(
                variant,
                Path(variant_args.output_dir),
                report_path,
            )
        )

    write_csv(
        Path(args.summary_csv),
        summary_rows,
        [
            "variant",
            "title",
            "start",
            "end",
            "valuation_date",
            "cash_symbol",
            "gold_symbol",
            "silver_symbol",
            "equity_symbol",
            "contribution_krw",
            "final_value_krw",
            "profit_krw",
            "simple_return",
            "xirr",
            "max_drawdown",
            "report",
            "note",
        ],
    )
    write_summary_report(Path(args.summary_report), summary_rows)
    print(f"Generated variants: {len(summary_rows)}")
    print(f"Generated summary: {args.summary_report}")
    print(f"Generated summary CSV: {args.summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
