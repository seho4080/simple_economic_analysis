#!/usr/bin/env python3
"""Run longest-available ISA-compatible ETF backtest variants."""

from __future__ import annotations

import argparse
from pathlib import Path

import backtest_actual_etfs
from backtest_monthly_allocation import pct, write_csv
from date_defaults import latest_report_date_iso, today_iso
from run_actual_etf_variants import Variant, build_variant_args, summarize_variant


DEFAULT_END_DATE = latest_report_date_iso()


ISA_MAX_VARIANTS = [
    Variant(
        slug="isa_max_hedged_sp500",
        title="ISA 장기 환헤지 S&P500",
        start="2015-06-06",
        end=DEFAULT_END_DATE,
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="132030.KS",
        gold_label="KODEX 골드선물(H)",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="219480.KS",
        equity_label="KODEX 미국S&P500선물(H)",
        note="2015년 상장된 S&P500 환헤지 ETF를 쓰는 최장 공통 구간",
    ),
    Variant(
        slug="isa_max_unhedged_sp500",
        title="ISA 장기 환노출 S&P500",
        start="2020-09-06",
        end=DEFAULT_END_DATE,
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="132030.KS",
        gold_label="KODEX 골드선물(H)",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="360750.KS",
        equity_label="TIGER 미국S&P500",
        note="환노출 S&P500 ETF 상장 이후 최장 구간. 금은 장기 데이터 확보를 위해 골드선물(H) 유지",
    ),
    Variant(
        slug="isa_max_unhedged_nasdaq100",
        title="ISA 장기 환노출 나스닥100",
        start="2012-03-06",
        end=DEFAULT_END_DATE,
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="132030.KS",
        gold_label="KODEX 골드선물(H)",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="133690.KS",
        equity_label="TIGER 미국나스닥100",
        note="현금성 ETF 상장 이후 나스닥100 환노출 ETF를 쓰는 최장 공통 구간",
    ),
    Variant(
        slug="isa_unhedged_gold_sp500",
        title="ISA 금+S&P500 환노출",
        start="2022-01-06",
        end=DEFAULT_END_DATE,
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="411060.KS",
        gold_label="ACE KRX금현물",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="360750.KS",
        equity_label="TIGER 미국S&P500",
        note="금과 S&P500을 환노출형으로 맞춘 구간. ACE KRX금현물 상장 이후부터 가능",
    ),
    Variant(
        slug="isa_unhedged_gold_nasdaq100",
        title="ISA 금+나스닥100 환노출",
        start="2022-01-06",
        end=DEFAULT_END_DATE,
        cash_symbol="153130.KS",
        cash_label="KODEX 단기채권",
        gold_symbol="411060.KS",
        gold_label="ACE KRX금현물",
        silver_symbol="144600.KS",
        silver_label="KODEX 은선물(H)",
        equity_symbol="133690.KS",
        equity_label="TIGER 미국나스닥100",
        note="금과 나스닥100을 환노출형으로 맞춘 구간. ACE KRX금현물 상장 이후부터 가능",
    ),
]


def write_summary_report(path: Path, summary_rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ISA 가능 국내 ETF 최장 구간 백테스트",
        "",
        "## 기준",
        "- 중개형 ISA에서 매수 가능한 국내 상장 ETF만 사용",
        "- 각 프로필은 해당 ETF 조합이 모두 거래 가능한 가장 이른 6일 기준부터 시작",
        "- 가격 데이터는 Yahoo Finance 국내 ETF 조정종가",
        "- 매수/평가는 해당일 또는 직전 거래일 조정종가 사용",
        "- 세금, 수수료, 슬리피지, 실제 체결가 차이는 반영하지 않음",
        "",
        "## 결과 요약",
        "| 프로필 | 기간 | ETF 조합 | 원금 | 평가액 | 손익 | 수익률 | XIRR | 최대 낙폭 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        combo = f"{row['cash_symbol']} / {row['gold_symbol']} / {row['silver_symbol']} / {row['equity_symbol']}"
        lines.append(
            "| {title} | {start}~{end} | {combo} | {contribution:,.0f}원 | {final:,.0f}원 | {profit:,.0f}원 | {simple} | {xirr} | {mdd} |".format(
                title=row["title"],
                start=row["start"],
                end=row["end"],
                combo=combo,
                contribution=row["contribution_krw"],
                final=row["final_value_krw"],
                profit=row["profit_krw"],
                simple=pct(float(row["simple_return"])),
                xirr=pct(float(row["xirr"])) if row["xirr"] != "" else "n/a",
                mdd=pct(float(row["max_drawdown"])),
            )
        )
    lines.extend(["", "## 개별 리포트"])
    for row in summary_rows:
        lines.append(f"- {row['title']}: `{row['report']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run longest ISA-compatible ETF backtests.")
    parser.add_argument("--history", default="data/processed/macro/risk_score_history_monthly.csv")
    parser.add_argument("--valuation-date", default=today_iso())
    parser.add_argument("--raw-dir", default="data/raw/yahoo_isa_etf_max")
    parser.add_argument("--output-dir", default="data/processed/backtests/isa_etf_max")
    parser.add_argument("--report-dir", default="reports/backtests/isa_etf_max")
    parser.add_argument("--summary-report", default="reports/backtests/isa_etf_max_summary.md")
    parser.add_argument("--summary-csv", default="data/processed/backtests/isa_etf_max/variant_summary.csv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary_rows: list[dict] = []
    for variant in ISA_MAX_VARIANTS:
        variant_args = build_variant_args(args, variant)
        report_path, _, _ = backtest_actual_etfs.run_backtest(variant_args)
        summary_rows.append(summarize_variant(variant, Path(variant_args.output_dir), report_path))

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
    print(f"Generated ISA ETF max variants: {len(summary_rows)}")
    print(f"Generated summary: {args.summary_report}")
    print(f"Generated summary CSV: {args.summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
