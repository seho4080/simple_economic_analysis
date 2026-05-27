#!/usr/bin/env python3
"""Backtest monthly macro allocations with actual listed ETF prices."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from backtest_monthly_allocation import (
    MANWON_TO_KRW,
    PricePoint,
    draw_equity_curve,
    fetch_yahoo_prices,
    money,
    parse_float,
    pct,
    read_csv,
    value_on_or_before,
    write_csv,
    xirr,
)
from date_defaults import latest_report_date_iso, today_iso


@dataclass(frozen=True)
class EtfSpec:
    asset: str
    label: str
    symbol: str
    amount_field: str


@dataclass(frozen=True)
class EtfLot:
    report_date: date
    asset: str
    label: str
    symbol: str
    amount_krw: float
    units: float
    buy_price_krw: float
    final_price_krw: float
    final_value_krw: float


def default_specs(args: argparse.Namespace) -> list[EtfSpec]:
    return [
        EtfSpec("cash", args.cash_label, args.cash_symbol, "cash_amount"),
        EtfSpec("gold", args.gold_label, args.gold_symbol, "gold_amount"),
        EtfSpec("silver", args.silver_label, args.silver_symbol, "silver_amount"),
        EtfSpec("equity", args.equity_label, args.equity_symbol, "equity_amount"),
    ]


def price_at(points: list[PricePoint], target: date, symbol: str) -> PricePoint:
    point = value_on_or_before(points, target)
    if not point:
        raise ValueError(f"No price for {symbol} on or before {target.isoformat()}")
    return point


def build_curve(
    lots: list[EtfLot],
    prices: dict[str, list[PricePoint]],
    contribution_dates: list[date],
    valuation_date: date,
) -> list[dict]:
    curve_dates = sorted(set(contribution_dates + [valuation_date]))
    contributions_by_date: dict[date, float] = {}
    for lot in lots:
        contributions_by_date[lot.report_date] = contributions_by_date.get(lot.report_date, 0.0) + lot.amount_krw

    rows: list[dict] = []
    cumulative_contribution = 0.0
    for curve_date in curve_dates:
        cumulative_contribution += contributions_by_date.get(curve_date, 0.0)
        totals = {"cash": 0.0, "gold": 0.0, "silver": 0.0, "equity": 0.0}
        for lot in lots:
            if lot.report_date > curve_date:
                continue
            price = price_at(prices[lot.asset], curve_date, lot.symbol).value
            totals[lot.asset] += lot.units * price
        total_value = sum(totals.values())
        rows.append(
            {
                "date": curve_date.isoformat(),
                "contribution_krw": round(cumulative_contribution),
                "cash_value_krw": round(totals["cash"]),
                "gold_value_krw": round(totals["gold"]),
                "silver_value_krw": round(totals["silver"]),
                "equity_value_krw": round(totals["equity"]),
                "total_value_krw": round(total_value),
                "profit_krw": round(total_value - cumulative_contribution),
                "simple_return": (total_value / cumulative_contribution - 1.0) if cumulative_contribution else 0.0,
            }
        )
    return rows


def max_drawdown(curve_rows: list[dict]) -> float:
    peak = 0.0
    drawdown = 0.0
    for row in curve_rows:
        value = float(row["total_value_krw"])
        peak = max(peak, value)
        if peak > 0:
            drawdown = min(drawdown, value / peak - 1.0)
    return drawdown


def run_backtest(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    valuation_date = date.fromisoformat(args.valuation_date)
    specs = default_specs(args)

    history_rows = [
        row
        for row in read_csv(Path(args.history))
        if start <= date.fromisoformat(row["report_date"]) <= end
    ]
    if not history_rows:
        raise ValueError("No monthly allocation rows found for the requested period.")
    history_rows.sort(key=lambda row: date.fromisoformat(row["report_date"]))
    actual_start = history_rows[0]["report_date"]
    actual_end = history_rows[-1]["report_date"]

    raw_dir = Path(args.raw_dir)
    price_start = start - timedelta(days=14)
    prices = {
        spec.asset: fetch_yahoo_prices(spec.symbol, price_start, valuation_date, raw_dir, use_adjusted=True)
        for spec in specs
    }

    lots: list[EtfLot] = []
    trade_rows: list[dict] = []
    for row in history_rows:
        report_date = date.fromisoformat(row["report_date"])
        for spec in specs:
            amount_manwon = parse_float(row.get(spec.amount_field)) or 0.0
            amount_krw = amount_manwon * MANWON_TO_KRW
            if amount_krw <= 0:
                continue
            buy_point = price_at(prices[spec.asset], report_date, spec.symbol)
            final_point = price_at(prices[spec.asset], valuation_date, spec.symbol)
            units = amount_krw / buy_point.value
            final_value = units * final_point.value
            lots.append(
                EtfLot(
                    report_date=report_date,
                    asset=spec.asset,
                    label=spec.label,
                    symbol=spec.symbol,
                    amount_krw=amount_krw,
                    units=units,
                    buy_price_krw=buy_point.value,
                    final_price_krw=final_point.value,
                    final_value_krw=final_value,
                )
            )
            trade_rows.append(
                {
                    "report_date": report_date.isoformat(),
                    "asset": spec.asset,
                    "label": spec.label,
                    "symbol": spec.symbol,
                    "amount_krw": round(amount_krw),
                    "buy_date": buy_point.date.isoformat(),
                    "buy_price_krw": round(buy_point.value, 4),
                    "units": units,
                    "final_price_krw": round(final_point.value, 4),
                    "final_value_krw": round(final_value),
                    "profit_krw": round(final_value - amount_krw),
                    "return": (final_value / amount_krw - 1.0) if amount_krw else 0.0,
                }
            )

    contribution_dates = [date.fromisoformat(row["report_date"]) for row in history_rows]
    curve_rows = build_curve(lots, prices, contribution_dates, valuation_date)

    output_dir = Path(args.output_dir)
    trade_path = output_dir / "actual_etf_trades.csv"
    curve_path = output_dir / "actual_etf_equity_curve.csv"
    report_path = Path(args.report)
    chart_path = report_path.parent / "assets" / report_path.stem / "equity_curve.png"

    write_csv(
        trade_path,
        trade_rows,
        [
            "report_date",
            "asset",
            "label",
            "symbol",
            "amount_krw",
            "buy_date",
            "buy_price_krw",
            "units",
            "final_price_krw",
            "final_value_krw",
            "profit_krw",
            "return",
        ],
    )
    write_csv(
        curve_path,
        curve_rows,
        [
            "date",
            "contribution_krw",
            "cash_value_krw",
            "gold_value_krw",
            "silver_value_krw",
            "equity_value_krw",
            "total_value_krw",
            "profit_krw",
            "simple_return",
        ],
    )
    draw_equity_curve(curve_rows, chart_path)

    total_contributed = sum(lot.amount_krw for lot in lots)
    final_by_asset = {
        spec.asset: sum(lot.final_value_krw for lot in lots if lot.asset == spec.asset)
        for spec in specs
    }
    contributed_by_asset = {
        spec.asset: sum(lot.amount_krw for lot in lots if lot.asset == spec.asset)
        for spec in specs
    }
    final_value = sum(final_by_asset.values())
    profit = final_value - total_contributed
    irr = xirr([(lot.report_date, -lot.amount_krw) for lot in lots] + [(valuation_date, final_value)])
    drawdown = max_drawdown(curve_rows)

    labels = {spec.asset: f"{spec.label} `{spec.symbol}`" for spec in specs}
    report_lines = [
        "# 실제 국내 ETF 가격 기반 월별 150만원 백테스트",
        "",
        "## 가정",
        f"- 매수 기간: {actual_start} ~ {actual_end}, 매월 6일 리포트 배분표 기준",
        f"- 평가일: {valuation_date.isoformat()}",
        "- 가격 데이터: Yahoo Finance 국내 ETF 조정종가",
        "- 매수/평가는 해당일 또는 직전 거래일 조정종가 사용",
        "- 세금, 수수료, 슬리피지, 실제 체결가 차이는 반영하지 않음",
        "",
        "## ETF 매핑",
        "| 리포트 자산군 | 실제 ETF |",
        "|---|---|",
    ]
    for spec in specs:
        report_lines.append(f"| {spec.asset} | {spec.label} `{spec.symbol}` |")

    report_lines.extend(
        [
            "",
            "## 결과 요약",
            f"- 누적 투자원금: {money(total_contributed)} ({total_contributed:,.0f}원)",
            f"- 평가금액: {money(final_value)} ({final_value:,.0f}원)",
            f"- 평가손익: {money(profit)} ({profit:,.0f}원)",
            f"- 단순 수익률: {pct(final_value / total_contributed - 1.0)}",
            f"- 연환산 자금가중수익률 XIRR: {pct(irr)}",
            f"- 월별 평가 기준 최대 낙폭: {pct(drawdown)}",
            "",
            "## 자산별 기여",
            "| 자산 | 누적 매수 | 평가금액 | 손익 | 수익률 | 평가 비중 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for spec in specs:
        contributed = contributed_by_asset[spec.asset]
        value = final_by_asset[spec.asset]
        asset_profit = value - contributed
        report_lines.append(
            "| {label} | {contributed} | {value} | {profit} | {return_pct} | {share} |".format(
                label=labels[spec.asset],
                contributed=f"{contributed:,.0f}원",
                value=f"{value:,.0f}원",
                profit=f"{asset_profit:,.0f}원",
                return_pct=pct(value / contributed - 1.0) if contributed else "n/a",
                share=pct(value / final_value) if final_value else "n/a",
            )
        )

    report_lines.extend(
        [
            "",
            "## 포트폴리오 곡선",
            f"![Equity Curve]({chart_path.relative_to(report_path.parent).as_posix()})",
            "",
            "## 출력 파일",
            f"- 거래/로트: `{trade_path.as_posix()}`",
            f"- 월별 평가곡선: `{curve_path.as_posix()}`",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return report_path, trade_path, curve_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest monthly allocations with actual ETF prices.")
    parser.add_argument("--history", default="data/processed/macro/risk_score_history_monthly.csv")
    parser.add_argument("--start", default="2015-06-06")
    parser.add_argument("--end", default=latest_report_date_iso())
    parser.add_argument("--valuation-date", default=today_iso())
    parser.add_argument("--raw-dir", default="data/raw/yahoo_kr_etf_actual")
    parser.add_argument("--output-dir", default="data/processed/backtests/actual_kr_etf_max_hedged_sp500")
    parser.add_argument("--report", default="reports/backtests/actual_kr_etf_max_hedged_sp500.md")
    parser.add_argument("--cash-symbol", default="153130.KS")
    parser.add_argument("--cash-label", default="KODEX 단기채권")
    parser.add_argument("--gold-symbol", default="132030.KS")
    parser.add_argument("--gold-label", default="KODEX 골드선물(H)")
    parser.add_argument("--silver-symbol", default="144600.KS")
    parser.add_argument("--silver-label", default="KODEX 은선물(H)")
    parser.add_argument("--equity-symbol", default="219480.KS")
    parser.add_argument("--equity-label", default="KODEX 미국S&P500선물(H)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report_path, trade_path, curve_path = run_backtest(args)
    print(f"Generated report: {report_path}")
    print(f"Generated trades: {trade_path}")
    print(f"Generated curve: {curve_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
