#!/usr/bin/env python3
"""Backtest monthly purchases from macro-regime allocation history."""

from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


USER_AGENT = "stock-economic-indicators/0.3"
MANWON_TO_KRW = 10_000


@dataclass(frozen=True)
class PricePoint:
    date: date
    value: float


@dataclass(frozen=True)
class Lot:
    report_date: date
    asset: str
    amount_krw: float
    units: float
    buy_price_krw: float | None
    final_price_krw: float | None
    final_value_krw: float


def parse_float(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        if math.isnan(float(value)):
            return None
        return float(value)
    text = value.strip().replace(",", "")
    if text in {"", ".", "NA", "N/A", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def date_to_timestamp(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())


def fetch_yahoo_prices(symbol: str, start: date, end: date, raw_dir: Path, use_adjusted: bool = True) -> list[PricePoint]:
    quoted = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}"
        f"?period1={date_to_timestamp(start)}"
        f"&period2={date_to_timestamp(end + timedelta(days=1))}"
        "&interval=1d&events=history&includeAdjustedClose=true"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()

    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{symbol.replace('=', '_').replace('^', '_')}.json").write_bytes(raw)

    payload = json.loads(raw.decode("utf-8"))
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(chart["error"])
    result = (chart.get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"No Yahoo chart data for {symbol}")

    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    closes = quote.get("close") or []
    adjcloses = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
    values = adjcloses if use_adjusted and len(adjcloses) == len(timestamps) else closes

    points: list[PricePoint] = []
    for ts, value in zip(timestamps, values):
        parsed = parse_float(value)
        if parsed is None:
            continue
        obs_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        points.append(PricePoint(obs_date, parsed))
    return sorted(points, key=lambda point: point.date)


def observations_series(path: Path, indicator_id: str) -> list[PricePoint]:
    points: list[PricePoint] = []
    for row in read_csv(path):
        if row.get("indicator_id") != indicator_id:
            continue
        value = parse_float(row.get("value"))
        if value is None:
            continue
        try:
            obs_date = date.fromisoformat(row["date"])
        except ValueError:
            continue
        points.append(PricePoint(obs_date, value))
    return sorted(points, key=lambda point: point.date)


def value_on_or_before(points: list[PricePoint], target: date) -> PricePoint | None:
    candidate: PricePoint | None = None
    for point in points:
        if point.date <= target:
            candidate = point
        else:
            break
    return candidate


def krw_price(asset_points: list[PricePoint], fx_points: list[PricePoint], target: date) -> tuple[float, date, date]:
    asset = value_on_or_before(asset_points, target)
    fx = value_on_or_before(fx_points, target)
    if not asset or not fx:
        raise ValueError(f"Missing price or FX for {target}")
    return asset.value * fx.value, asset.date, fx.date


def cash_growth_factor(rate_points: list[PricePoint], start: date, end: date) -> float:
    if end <= start:
        return 1.0
    factor = 1.0
    current = start
    while current < end:
        rate_point = value_on_or_before(rate_points, current)
        annual_rate = rate_point.value if rate_point else 0.0
        factor *= (1.0 + annual_rate / 100.0) ** (1.0 / 365.0)
        current += timedelta(days=1)
    return factor


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    if not any(amount > 0 for _, amount in cashflows) or not any(amount < 0 for _, amount in cashflows):
        return None
    start = min(flow_date for flow_date, _ in cashflows)

    def npv(rate: float) -> float:
        total = 0.0
        for flow_date, amount in cashflows:
            years = (flow_date - start).days / 365.0
            total += amount / ((1.0 + rate) ** years)
        return total

    low, high = -0.999, 10.0
    low_value, high_value = npv(low), npv(high)
    if low_value * high_value > 0:
        return None
    for _ in range(120):
        mid = (low + high) / 2.0
        mid_value = npv(mid)
        if abs(mid_value) < 1e-6:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2.0


def money(value: float) -> str:
    return f"{value / 100_000_000:.2f}억원"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def build_equity_curve(
    lots: list[Lot],
    contribution_dates: list[date],
    valuation_date: date,
    prices: dict[str, list[PricePoint]],
    fx_points: list[PricePoint],
    rate_points: list[PricePoint],
) -> list[dict]:
    curve_dates = sorted(set(contribution_dates + [valuation_date]))
    rows: list[dict] = []
    cumulative_contribution = 0.0
    contributions_by_date: dict[date, float] = {}
    for lot in lots:
        contributions_by_date[lot.report_date] = contributions_by_date.get(lot.report_date, 0.0) + lot.amount_krw

    for curve_date in curve_dates:
        cumulative_contribution += contributions_by_date.get(curve_date, 0.0)
        totals = {"cash": 0.0, "gold": 0.0, "silver": 0.0, "equity": 0.0}
        for lot in lots:
            if lot.report_date > curve_date:
                continue
            if lot.asset == "cash":
                totals["cash"] += lot.amount_krw * cash_growth_factor(rate_points, lot.report_date, curve_date)
            else:
                price, _, _ = krw_price(prices[lot.asset], fx_points, curve_date)
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


def draw_equity_curve(curve_rows: list[dict], output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    dates = [date.fromisoformat(row["date"]) for row in curve_rows]
    contributions = [row["contribution_krw"] / 1_000_000 for row in curve_rows]
    values = [row["total_value_krw"] / 1_000_000 for row in curve_rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5), dpi=160)
    ax.plot(dates, values, label="Portfolio value", color="#2563eb", linewidth=2.2)
    ax.plot(dates, contributions, label="Contributions", color="#64748b", linestyle="--", linewidth=1.8)
    ax.fill_between(dates, contributions, values, color="#93c5fd", alpha=0.25)
    ax.set_title("Monthly KRW 1.5M Allocation Backtest")
    ax.set_ylabel("KRW million")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def run_backtest(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    history_path = Path(args.history)
    observations_path = Path(args.observations)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    valuation_date = date.fromisoformat(args.valuation_date)

    history_rows = [
        row
        for row in read_csv(history_path)
        if start <= date.fromisoformat(row["report_date"]) <= end
    ]
    if not history_rows:
        raise ValueError("No monthly allocation rows found for the requested period.")

    price_start = start - timedelta(days=14)
    price_end = valuation_date
    raw_dir = Path(args.raw_dir)
    prices = {
        "gold": fetch_yahoo_prices(args.gold_symbol, price_start, price_end, raw_dir, use_adjusted=False),
        "silver": fetch_yahoo_prices(args.silver_symbol, price_start, price_end, raw_dir, use_adjusted=False),
        "equity": fetch_yahoo_prices(args.equity_symbol, price_start, price_end, raw_dir, use_adjusted=True),
    }
    fx_points = observations_series(observations_path, args.fx_indicator)
    rate_points = observations_series(observations_path, args.cash_rate_indicator)

    lots: list[Lot] = []
    trade_rows: list[dict] = []
    asset_amount_fields = {
        "cash": "cash_amount",
        "gold": "gold_amount",
        "silver": "silver_amount",
        "equity": "equity_amount",
    }
    for row in history_rows:
        report_date = date.fromisoformat(row["report_date"])
        for asset, amount_field in asset_amount_fields.items():
            amount_manwon = parse_float(row.get(amount_field)) or 0.0
            amount_krw = amount_manwon * MANWON_TO_KRW
            if amount_krw <= 0:
                continue
            if asset == "cash":
                final_value = amount_krw * cash_growth_factor(rate_points, report_date, valuation_date)
                lot = Lot(report_date, asset, amount_krw, 0.0, None, None, final_value)
                buy_asset_date = ""
                buy_fx_date = ""
                buy_price_krw = ""
                units = ""
                final_price_krw = ""
            else:
                buy_price, buy_asset_date_obj, buy_fx_date_obj = krw_price(prices[asset], fx_points, report_date)
                final_price, _, _ = krw_price(prices[asset], fx_points, valuation_date)
                units_float = amount_krw / buy_price
                final_value = units_float * final_price
                lot = Lot(report_date, asset, amount_krw, units_float, buy_price, final_price, final_value)
                buy_asset_date = buy_asset_date_obj.isoformat()
                buy_fx_date = buy_fx_date_obj.isoformat()
                buy_price_krw = round(buy_price, 4)
                units = units_float
                final_price_krw = round(final_price, 4)
            lots.append(lot)
            trade_rows.append(
                {
                    "report_date": report_date.isoformat(),
                    "asset": asset,
                    "amount_krw": round(amount_krw),
                    "buy_asset_date": buy_asset_date,
                    "buy_fx_date": buy_fx_date,
                    "buy_price_krw": buy_price_krw,
                    "units": units,
                    "final_price_krw": final_price_krw,
                    "final_value_krw": round(final_value),
                    "profit_krw": round(final_value - amount_krw),
                    "return": (final_value / amount_krw - 1.0) if amount_krw else 0.0,
                }
            )

    contribution_dates = [date.fromisoformat(row["report_date"]) for row in history_rows]
    curve_rows = build_equity_curve(lots, contribution_dates, valuation_date, prices, fx_points, rate_points)

    output_dir = Path(args.output_dir)
    trade_path = output_dir / "monthly_allocation_trades.csv"
    curve_path = output_dir / "monthly_allocation_equity_curve.csv"
    report_path = Path(args.report)
    chart_path = report_path.parent / "assets" / report_path.stem / "equity_curve.png"

    write_csv(
        trade_path,
        trade_rows,
        [
            "report_date",
            "asset",
            "amount_krw",
            "buy_asset_date",
            "buy_fx_date",
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
        asset: sum(lot.final_value_krw for lot in lots if lot.asset == asset)
        for asset in ["cash", "gold", "silver", "equity"]
    }
    contributed_by_asset = {
        asset: sum(lot.amount_krw for lot in lots if lot.asset == asset)
        for asset in ["cash", "gold", "silver", "equity"]
    }
    final_value = sum(final_by_asset.values())
    profit = final_value - total_contributed
    irr = xirr([(lot.report_date, -lot.amount_krw) for lot in lots] + [(valuation_date, final_value)])
    peak = 0.0
    max_drawdown = 0.0
    for row in curve_rows:
        value = float(row["total_value_krw"])
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1.0)

    report_lines = [
        "# 월별 150만원 매수 백테스트",
        "",
        "## 가정",
        f"- 매수 기간: {start.isoformat()} ~ {end.isoformat()}, 매월 6일 리포트 배분표 기준",
        f"- 평가일: {valuation_date.isoformat()}",
        "- 금: Yahoo Finance `GC=F` 종가를 USD/KRW로 원화 환산",
        "- 은/원자재: Yahoo Finance `SI=F` 종가를 USD/KRW로 원화 환산",
        f"- 주식/ETF: Yahoo Finance `{args.equity_symbol}` 조정종가를 USD/KRW로 원화 환산",
        f"- 현금성/단기채: `{args.cash_rate_indicator}` 연율을 일복리로 적용",
        "- 세금, 수수료, 슬리피지, 실제 ETF 추적오차는 반영하지 않음",
        "",
        "## 결과 요약",
        f"- 누적 투자원금: {money(total_contributed)} ({total_contributed:,.0f}원)",
        f"- 평가금액: {money(final_value)} ({final_value:,.0f}원)",
        f"- 평가손익: {money(profit)} ({profit:,.0f}원)",
        f"- 단순 수익률: {pct(final_value / total_contributed - 1.0)}",
        f"- 연환산 자금가중수익률 XIRR: {pct(irr)}",
        f"- 월별 평가 기준 최대 낙폭: {pct(max_drawdown)}",
        "",
        "## 자산별 기여",
        "| 자산 | 누적 매수 | 평가금액 | 손익 | 수익률 | 평가 비중 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "cash": "현금성/단기채",
        "gold": "금",
        "silver": "은/원자재",
        "equity": "주식/ETF",
    }
    for asset in ["cash", "gold", "silver", "equity"]:
        contributed = contributed_by_asset[asset]
        value = final_by_asset[asset]
        asset_profit = value - contributed
        report_lines.append(
            "| {label} | {contributed} | {value} | {profit} | {return_pct} | {share} |".format(
                label=labels[asset],
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
    parser = argparse.ArgumentParser(description="Backtest monthly macro-regime allocation purchases.")
    parser.add_argument("--history", default="data/processed/macro/risk_score_history_monthly.csv")
    parser.add_argument("--observations", default="data/processed/macro/observations_long.csv")
    parser.add_argument("--start", default="2012-03-06")
    parser.add_argument("--end", default="2026-04-06")
    parser.add_argument("--valuation-date", default="2026-05-27")
    parser.add_argument("--equity-symbol", default="SPY")
    parser.add_argument("--gold-symbol", default="GC=F")
    parser.add_argument("--silver-symbol", default="SI=F")
    parser.add_argument("--fx-indicator", default="usd_krw")
    parser.add_argument("--cash-rate-indicator", default="korea_short_rate_3m")
    parser.add_argument("--raw-dir", default="data/raw/yahoo_proxy_backtest")
    parser.add_argument("--output-dir", default="data/processed/backtests/proxy_monthly_allocation_max")
    parser.add_argument(
        "--report",
        default="reports/backtests/proxy_monthly_allocation_max.md",
    )
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
